"""Treasury, shares, adjustments and pay.

The arithmetic here is what people argue about at the end of a month, so each
step is pinned to an exact figure rather than a range.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from kasbbook.modules.books.models import BookType, Role
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.payroll.models import (
    AdjustmentKind,
    AdjustmentMode,
    PeriodStatus,
    PerformanceRecord,
    ShareBasis,
    ShareRule,
)
from kasbbook.modules.payroll.service import PayrollService
from kasbbook.modules.treasury.models import FundKind, RuleBasis, TreasuryFund, TreasuryRule
from kasbbook.shared.errors import PermissionDenied, ValidationError

pytestmark = pytest.mark.asyncio

START = date(2025, 4, 1)
END = date(2025, 4, 31 if False else 30)


async def team_with_income(session, income="10000000", costs="2000000"):
    """A team book with one period and some money in it."""
    identity = IdentityService(session)
    books = BookService(session)
    ledger = LedgerService(session)
    payroll = PayrollService(session)

    owner = await identity.create_user("مالک")
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)

    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.TEAM, "پروژه", income,
                        occurred_on=START)
    if costs:
        await ledger.record(book.id, owner.id, Flow.EXPENSE, Scope.TEAM, "سرور", costs,
                            occurred_on=START)

    period = await payroll.open_period(owner.id, book.id, "فروردین ۱۴۰۴", START, END)
    return identity, books, payroll, owner, book, period


async def add_member(session, books, identity, book, owner, name, role=Role.MEMBER):
    member = await identity.create_user(name)
    await books.add_member(owner.id, book.id, member.id, role)
    return member


def share(session, book, user, basis, value, start=START, end=None):
    rule = ShareRule(
        book_id=book.id, user_id=user.id, basis=basis,
        value=Decimal(str(value)), effective_from=start, effective_to=end,
    )
    session.add(rule)
    return rule


# ------------------------------------------------------------------ treasury
async def test_distribution_is_income_minus_costs_minus_treasury(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)

    fund = TreasuryFund(book_id=book.id, kind=FundKind.MAIN, name="خزانه اصلی")
    session.add(fund)
    await session.flush()
    session.add(
        TreasuryRule(
            book_id=book.id, fund_id=fund.id, basis=RuleBasis.NET_PERCENT,
            value=Decimal("20"), effective_from=START,
        )
    )
    await session.flush()

    d = await payroll.compute_distribution(period.id)
    assert d.gross_income == Decimal("10000000")
    assert d.direct_costs == Decimal("2000000")
    assert d.net_profit == Decimal("8000000")
    assert d.treasury_total == Decimal("1600000")     # 20% of net
    assert d.distributable == Decimal("6400000")


async def test_a_gross_percent_rule_takes_from_income_not_profit(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)

    fund = TreasuryFund(book_id=book.id, kind=FundKind.TAX, name="مالیات")
    session.add(fund)
    await session.flush()
    session.add(
        TreasuryRule(book_id=book.id, fund_id=fund.id, basis=RuleBasis.GROSS_PERCENT,
                     value=Decimal("9"), effective_from=START)
    )
    await session.flush()

    d = await payroll.compute_distribution(period.id)
    assert d.treasury_total == Decimal("900000")      # 9% of gross, not of net


async def test_several_funds_each_take_their_own_cut(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)

    for kind, name, pct in (
        (FundKind.MAIN, "اصلی", "10"),
        (FundKind.EMERGENCY, "اضطراری", "5"),
        (FundKind.EQUIPMENT, "تجهیزات", "5"),
    ):
        fund = TreasuryFund(book_id=book.id, kind=kind, name=name)
        session.add(fund)
        await session.flush()
        session.add(
            TreasuryRule(book_id=book.id, fund_id=fund.id, basis=RuleBasis.NET_PERCENT,
                         value=Decimal(pct), effective_from=START)
        )
    await session.flush()

    d = await payroll.compute_distribution(period.id)
    assert len(d.treasury_by_fund) == 3
    assert d.treasury_total == Decimal("1600000")     # 20% of 8,000,000


async def test_a_rule_that_has_not_started_takes_nothing(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)

    fund = TreasuryFund(book_id=book.id, kind=FundKind.MAIN, name="اصلی")
    session.add(fund)
    await session.flush()
    session.add(
        TreasuryRule(book_id=book.id, fund_id=fund.id, basis=RuleBasis.NET_PERCENT,
                     value=Decimal("50"), effective_from=date(2026, 1, 1))
    )
    await session.flush()

    d = await payroll.compute_distribution(period.id)
    assert d.treasury_total == Decimal("0")
    assert d.distributable == Decimal("8000000")


# -------------------------------------------------------------------- shares
async def test_percentage_shares_split_the_distributable_amount(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    a = await add_member(session, books, identity, book, owner, "الف")
    b = await add_member(session, books, identity, book, owner, "ب")

    share(session, book, a, ShareBasis.PERCENT, 60)
    share(session, book, b, ShareBasis.PERCENT, 40)
    await session.flush()

    slips = {s.user_id: s for s in await payroll.calculate(owner.id, period.id)}
    assert slips[a.id].base_share == Decimal("6000000")
    assert slips[b.id].base_share == Decimal("4000000")


async def test_a_fixed_share_is_taken_before_the_rest_is_split(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    salaried = await add_member(session, books, identity, book, owner, "حقوق‌بگیر")
    partner = await add_member(session, books, identity, book, owner, "شریک")

    share(session, book, salaried, ShareBasis.FIXED, 3000000)
    share(session, book, partner, ShareBasis.HOURS, 1)
    session.add(
        PerformanceRecord(book_id=book.id, period_id=period.id, user_id=partner.id,
                          hours_worked=Decimal("100"))
    )
    await session.flush()

    slips = {s.user_id: s for s in await payroll.calculate(owner.id, period.id)}
    assert slips[salaried.id].base_share == Decimal("3000000")
    assert slips[partner.id].base_share == Decimal("7000000")   # whatever is left


async def test_hour_based_shares_split_in_proportion_to_hours(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="9000000", costs=None
    )
    a = await add_member(session, books, identity, book, owner, "الف")
    b = await add_member(session, books, identity, book, owner, "ب")

    share(session, book, a, ShareBasis.HOURS, 1)
    share(session, book, b, ShareBasis.HOURS, 1)
    session.add_all([
        PerformanceRecord(book_id=book.id, period_id=period.id, user_id=a.id,
                          hours_worked=Decimal("120")),
        PerformanceRecord(book_id=book.id, period_id=period.id, user_id=b.id,
                          hours_worked=Decimal("60")),
    ])
    await session.flush()

    slips = {s.user_id: s for s in await payroll.calculate(owner.id, period.id)}
    assert slips[a.id].base_share == Decimal("6000000")   # 2/3
    assert slips[b.id].base_share == Decimal("3000000")   # 1/3


async def test_a_later_share_rule_wins_without_rewriting_the_past(session):
    """The reason share rules are effective-dated at all."""
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    member = await add_member(session, books, identity, book, owner, "عضو")

    share(session, book, member, ShareBasis.PERCENT, 30, start=date(2025, 1, 1),
          end=date(2025, 3, 31))
    share(session, book, member, ShareBasis.PERCENT, 50, start=date(2025, 4, 1))
    await session.flush()

    rules = await payroll.share_rules_for(book.id, date(2025, 2, 15))
    assert rules[member.id].value == Decimal("30")

    rules = await payroll.share_rules_for(book.id, date(2025, 4, 15))
    assert rules[member.id].value == Decimal("50")


# --------------------------------------------------------------- adjustments
async def test_a_bonus_and_a_penalty_move_pay_the_right_way(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    member = await add_member(session, books, identity, book, owner, "عضو")
    share(session, book, member, ShareBasis.PERCENT, 100)
    await session.flush()

    await payroll.add_adjustment(owner.id, period.id, member.id, AdjustmentKind.BONUS,
                                 AdjustmentMode.AMOUNT, "500000", "پروژه اضافه")
    await payroll.add_adjustment(owner.id, period.id, member.id, AdjustmentKind.PENALTY,
                                 AdjustmentMode.AMOUNT, "-200000", "تأخیر")
    await session.flush()

    slip = (await payroll.calculate(owner.id, period.id))[0]
    assert slip.base_share == Decimal("10000000")
    assert slip.adjustments_total == Decimal("300000")
    assert slip.net_pay == Decimal("10300000")


async def test_a_percentage_adjustment_is_taken_off_the_base_share(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    member = await add_member(session, books, identity, book, owner, "عضو")
    share(session, book, member, ShareBasis.PERCENT, 100)
    await session.flush()

    await payroll.add_adjustment(owner.id, period.id, member.id, AdjustmentKind.SHORTFALL,
                                 AdjustmentMode.PERCENT, "-10", "کسری کارکرد")
    await session.flush()

    slip = (await payroll.calculate(owner.id, period.id))[0]
    assert slip.adjustments_total == Decimal("-1000000")
    assert slip.net_pay == Decimal("9000000")


async def test_nobody_approves_their_own_adjustment(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    member = await add_member(session, books, identity, book, owner, "عضو")

    adjustment = await payroll.add_adjustment(
        owner.id, period.id, member.id, AdjustmentKind.BONUS, AdjustmentMode.AMOUNT, "1000"
    )
    await session.flush()

    with pytest.raises(PermissionDenied):
        await payroll.approve_adjustment(owner.id, adjustment.id)


# -------------------------------------------------------------------- period
async def test_a_period_only_moves_along_the_allowed_path(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)

    # Cannot jump straight from open to paid.
    with pytest.raises(ValidationError):
        await payroll.advance_period(owner.id, period.id, PeriodStatus.PAID)

    for step in (
        PeriodStatus.CALCULATING,
        PeriodStatus.AWAITING_APPROVAL,
        PeriodStatus.APPROVED,
        PeriodStatus.PAID,
        PeriodStatus.LOCKED,
    ):
        await payroll.advance_period(owner.id, period.id, step)

    assert (await payroll.get_period(period.id)).status is PeriodStatus.LOCKED


async def test_a_locked_period_refuses_new_adjustments(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    member = await add_member(session, books, identity, book, owner, "عضو")

    for step in (
        PeriodStatus.CALCULATING, PeriodStatus.AWAITING_APPROVAL,
        PeriodStatus.APPROVED, PeriodStatus.PAID, PeriodStatus.LOCKED,
    ):
        await payroll.advance_period(owner.id, period.id, step)

    with pytest.raises(PermissionDenied):
        await payroll.add_adjustment(
            owner.id, period.id, member.id, AdjustmentKind.BONUS,
            AdjustmentMode.AMOUNT, "1000",
        )


async def test_a_locked_period_is_the_end_of_the_line(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    for step in (
        PeriodStatus.CALCULATING, PeriodStatus.AWAITING_APPROVAL,
        PeriodStatus.APPROVED, PeriodStatus.PAID, PeriodStatus.LOCKED,
    ):
        await payroll.advance_period(owner.id, period.id, step)

    with pytest.raises(ValidationError):
        await payroll.advance_period(owner.id, period.id, PeriodStatus.OPEN)


# ------------------------------------------------------------------ payment
async def test_pay_can_be_handed_over_in_instalments(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    member = await add_member(session, books, identity, book, owner, "عضو")
    share(session, book, member, ShareBasis.PERCENT, 100)
    await session.flush()

    slip = (await payroll.calculate(owner.id, period.id))[0]
    assert slip.remaining == Decimal("10000000")

    await payroll.pay(owner.id, slip.id, "4000000", reference="اول")
    await session.refresh(slip, attribute_names=["payments"])
    assert slip.paid_total == Decimal("4000000")
    assert slip.remaining == Decimal("6000000")
    assert not slip.is_settled

    await payroll.pay(owner.id, slip.id, "6000000", reference="دوم")
    await session.refresh(slip, attribute_names=["payments"])
    assert slip.is_settled


async def test_paying_more_than_is_owed_is_refused(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="1000000", costs=None
    )
    member = await add_member(session, books, identity, book, owner, "عضو")
    share(session, book, member, ShareBasis.PERCENT, 100)
    await session.flush()

    slip = (await payroll.calculate(owner.id, period.id))[0]
    with pytest.raises(ValidationError):
        await payroll.pay(owner.id, slip.id, "2000000")


# ------------------------------------------------------------------ privacy
async def test_a_member_sees_only_their_own_payslip(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    a = await add_member(session, books, identity, book, owner, "الف")
    b = await add_member(session, books, identity, book, owner, "ب")
    share(session, book, a, ShareBasis.PERCENT, 50)
    share(session, book, b, ShareBasis.PERCENT, 50)
    await session.flush()

    await payroll.calculate(owner.id, period.id)

    mine = await payroll.payslips(a.id, period.id)
    assert [s.user_id for s in mine] == [a.id]

    # The owner holds VIEW_OTHERS_PAY and sees the whole run.
    everyones = await payroll.payslips(owner.id, period.id)
    assert len(everyones) == 2


async def test_recalculating_replaces_the_run_rather_than_doubling_it(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    member = await add_member(session, books, identity, book, owner, "عضو")
    share(session, book, member, ShareBasis.PERCENT, 100)
    await session.flush()

    await payroll.calculate(owner.id, period.id)
    second = await payroll.calculate(owner.id, period.id)

    assert len(second) == 1
    assert len(await payroll.payslips(owner.id, period.id)) == 1


async def test_the_payslip_freezes_the_inputs_it_was_built_from(session):
    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=None
    )
    member = await add_member(session, books, identity, book, owner, "عضو")
    share(session, book, member, ShareBasis.PERCENT, 40)
    await session.flush()

    slip = (await payroll.calculate(owner.id, period.id))[0]
    assert slip.distributable_snapshot == Decimal("10000000")
    assert slip.share_basis_snapshot is ShareBasis.PERCENT
    assert slip.share_value_snapshot == Decimal("40")
    assert slip.currency == "IRT"
