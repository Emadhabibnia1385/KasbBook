"""Treasury, shares, adjustments and pay.

The arithmetic here is what people argue about at the end of a month, so each
step is pinned to an exact figure rather than a range.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from kasbbook.modules.books.models import BookType, CostPolicy, Role
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
from kasbbook.shared.errors import NotFound, PermissionDenied, ValidationError
from kasbbook.shared.money import ZERO as ZERO_INCOME

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


# --------------------------------------------------------------- cost policy
async def gross_rule(session, book, percent="50"):
    """A treasury that takes a flat percentage of gross income."""
    fund = TreasuryFund(book_id=book.id, kind=FundKind.MAIN, name="خزانه")
    session.add(fund)
    await session.flush()
    session.add(
        TreasuryRule(book_id=book.id, fund_id=fund.id, basis=RuleBasis.GROSS_PERCENT,
                     value=Decimal(percent), effective_from=START)
    )
    await session.flush()
    return fund


async def test_a_new_book_still_takes_costs_before_the_split(session):
    """The default must not move: existing teams are paid by this arithmetic."""
    identity, books, payroll, owner, book, period = await team_with_income(session)
    assert book.cost_policy is CostPolicy.BEFORE_SPLIT

    await gross_rule(session, book)
    d = await payroll.compute_distribution(period.id)
    # 10,000,000 income − 2,000,000 costs − 5,000,000 treasury
    assert d.distributable == Decimal("3000000")
    assert d.treasury_net == Decimal("5000000")


async def test_a_treasury_bearing_book_pays_members_off_gross_income(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    await books.set_cost_policy(owner.id, book.id, CostPolicy.FROM_TREASURY)
    await gross_rule(session, book)

    d = await payroll.compute_distribution(period.id)
    assert d.gross_income == Decimal("10000000")
    assert d.direct_costs == Decimal("2000000")
    # The members divide gross minus the cut; the costs never touch it.
    assert d.distributable == Decimal("5000000")
    # The treasury's own cut is what paid for them.
    assert d.treasury_net == Decimal("3000000")


async def test_a_treasury_that_cannot_cover_its_costs_is_reported_negative(session):
    """Clamping this to zero would hide the month the team actually lost money."""
    identity, books, payroll, owner, book, period = await team_with_income(
        session, costs="6000000"
    )
    await books.set_cost_policy(owner.id, book.id, CostPolicy.FROM_TREASURY)
    await gross_rule(session, book)

    d = await payroll.compute_distribution(period.id)
    assert d.distributable == Decimal("5000000")
    assert d.treasury_net == Decimal("-1000000")


async def test_the_cost_policy_reaches_the_payslips(session):
    """The policy is worth nothing if it stops at the report."""
    identity, books, payroll, owner, book, period = await team_with_income(session)
    await gross_rule(session, book)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()

    before = await payroll.calculate(owner.id, period.id)
    assert before[0].base_share == Decimal("3000000")

    await books.set_cost_policy(owner.id, book.id, CostPolicy.FROM_TREASURY)
    after = await payroll.calculate(owner.id, period.id)
    assert after[0].base_share == Decimal("5000000")


async def test_a_plain_member_cannot_change_the_cost_policy(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    member = await add_member(session, books, identity, book, owner, "عضو")

    with pytest.raises(PermissionDenied):
        await books.set_cost_policy(member.id, book.id, CostPolicy.FROM_TREASURY)

    await session.refresh(book)
    assert book.cost_policy is CostPolicy.BEFORE_SPLIT


async def test_the_cost_policy_of_another_teams_book_cannot_be_reached(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    stranger = await identity.create_user("غریبه")

    # NotFound rather than PermissionDenied, so book ids cannot be probed.
    with pytest.raises(NotFound):
        await books.set_cost_policy(stranger.id, book.id, CostPolicy.FROM_TREASURY)

async def test_recalculating_a_period_does_not_double_the_treasury(session):
    """A second run replaces the first one's allocation instead of adding to it.

    This was silent: the payslips were replaced and the allocations were not,
    so a book recalculated twice reported twice the treasury it ever held.
    """
    from sqlalchemy import select as _select
    from kasbbook.modules.treasury.models import TreasuryAllocation

    identity, books, payroll, owner, book, period = await team_with_income(session)
    await gross_rule(session, book)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()

    await payroll.calculate(owner.id, period.id)
    await payroll.calculate(owner.id, period.id)

    rows = (await session.execute(
        _select(TreasuryAllocation).where(TreasuryAllocation.period_id == period.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].amount == Decimal("5000000")


# ------------------------------------------------------- treasury rule dates
async def test_a_treasury_cut_can_change_between_periods(session):
    """The bug this closes: a cut could be set and never changed.

    applies_on() read effective_to and nothing ever wrote it, so a new
    percentage stacked on the old one and the treasury took both.
    """
    from kasbbook.modules.treasury.service import TreasuryService

    identity, books, payroll, owner, book, first = await team_with_income(
        session, income="10000000", costs=""
    )
    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "خزانه", FundKind.MAIN)

    await treasury.add_rule(book.id, owner.id, fund.id, RuleBasis.GROSS_PERCENT,
                            Decimal("50"), effective_from=START,
                            effective_to=date(2025, 4, 15))
    await treasury.add_rule(book.id, owner.id, fund.id, RuleBasis.GROSS_PERCENT,
                            Decimal("45"), effective_from=date(2025, 4, 16))
    await session.flush()

    # The fixture's period covers the whole month, and two periods may not
    # cover the same day. Here the month is split in two so each half ends
    # inside the window of the cut it should pay - a rule is judged on the
    # period's END date, not across its range.
    await payroll.delete_period(owner.id, first.id)
    early = await payroll.open_period(owner.id, book.id, "نیمهٔ اول",
                                      START, date(2025, 4, 15))
    late = await payroll.open_period(owner.id, book.id, "نیمهٔ دوم",
                                     date(2025, 4, 16), date(2025, 4, 30))

    # All the income is dated START, so only the first half sees it. Stacked,
    # the two rules would have taken 95% of it; they take 50%.
    assert (await payroll.compute_distribution(early.id)).treasury_total == Decimal("5000000")
    assert (await payroll.compute_distribution(late.id)).treasury_total == ZERO_INCOME


async def test_closing_a_rule_leaves_what_it_already_took(session):
    from kasbbook.modules.treasury.service import TreasuryService

    identity, books, payroll, owner, book, period = await team_with_income(session)
    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "خزانه", FundKind.MAIN)
    rule = await treasury.add_rule(book.id, owner.id, fund.id,
                                   RuleBasis.GROSS_PERCENT, Decimal("50"),
                                   effective_from=START)
    await session.flush()
    assert (await payroll.compute_distribution(period.id)).treasury_total == Decimal("5000000")

    await treasury.close_rule(book.id, owner.id, rule.id, date(2025, 4, 15))
    await session.flush()
    # The period ends after the rule closed, so it takes nothing more.
    assert (await payroll.compute_distribution(period.id)).treasury_total == ZERO_INCOME
    assert rule.is_active is True


async def test_a_rule_cannot_end_before_it_starts(session):
    from kasbbook.modules.treasury.service import TreasuryService

    identity, books, payroll, owner, book, period = await team_with_income(session)
    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "خزانه", FundKind.MAIN)
    with pytest.raises(ValidationError):
        await treasury.add_rule(book.id, owner.id, fund.id, RuleBasis.GROSS_PERCENT,
                                Decimal("50"), effective_from=START,
                                effective_to=date(2025, 3, 1))


# ---------------------------------------------------------- removing a period
async def test_a_period_that_paid_nobody_can_be_removed(session):
    """Two periods covering the same day divide that day's income twice."""
    identity, books, payroll, owner, book, period = await team_with_income(session)
    await payroll.delete_period(owner.id, period.id)
    await session.flush()
    assert await payroll.periods(book.id, owner.id) == []


async def test_a_period_that_produced_a_payslip_stays(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    await payroll.calculate(owner.id, period.id)

    with pytest.raises(ValidationError):
        await payroll.delete_period(owner.id, period.id)
    assert len(await payroll.periods(book.id, owner.id)) == 1


async def test_a_locked_period_is_never_removed(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    for to in (PeriodStatus.CALCULATING, PeriodStatus.AWAITING_APPROVAL,
               PeriodStatus.APPROVED, PeriodStatus.PAID, PeriodStatus.LOCKED):
        await payroll.advance_period(owner.id, period.id, to)
    with pytest.raises(PermissionDenied):
        await payroll.delete_period(owner.id, period.id)


async def test_a_member_cannot_remove_a_period(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    member = await add_member(session, books, identity, book, owner, "عضو")
    with pytest.raises(PermissionDenied):
        await payroll.delete_period(member.id, period.id)
    assert len(await payroll.periods(book.id, owner.id)) == 1


async def test_another_accounts_period_cannot_be_removed(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    stranger = await identity.create_user("غریبه")
    with pytest.raises(NotFound):
        await payroll.delete_period(stranger.id, period.id)
    assert len(await payroll.periods(book.id, owner.id)) == 1


async def test_setting_a_share_a_third_time_leaves_the_first_window_alone(session):
    """Closing every active rule widened the ones that had already ended.

    Three changes in a row left the first rule claiming to have been in force
    through the second period — history rewritten by a later decision, which
    is the one thing effective dating exists to prevent.
    """
    identity, books, payroll, owner, book, period = await team_with_income(session)

    await payroll.set_share(book.id, owner.id, owner.id, ShareBasis.PERCENT,
                            Decimal("8"), effective_from=date(2026, 6, 15))
    await payroll.set_share(book.id, owner.id, owner.id, ShareBasis.PERCENT,
                            Decimal("40"), effective_from=date(2026, 7, 7))
    await payroll.set_share(book.id, owner.id, owner.id, ShareBasis.PERCENT,
                            Decimal("33"), effective_from=date(2026, 8, 1))
    await session.flush()

    rules = sorted(
        (await session.execute(
            select(ShareRule).where(ShareRule.book_id == book.id,
                                    ShareRule.is_active.is_(True))
        )).scalars().all(),
        key=lambda r: r.effective_from,
    )
    assert [r.value for r in rules] == [Decimal("8"), Decimal("40"), Decimal("33")]
    assert rules[0].effective_to == date(2026, 7, 6)
    assert rules[1].effective_to == date(2026, 7, 31)
    assert rules[2].effective_to is None


async def test_a_period_can_be_renamed_without_touching_its_payslips(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    slips = await payroll.calculate(owner.id, period.id)

    renamed = await payroll.rename_period(owner.id, period.id, "۱۰ مرداد تا ۹ شهریور ۱۴۰۵")
    await session.flush()

    assert renamed.label == "۱۰ مرداد تا ۹ شهریور ۱۴۰۵"
    assert renamed.starts_on == START and renamed.ends_on == END
    assert (await payroll.payslips(owner.id, period.id))[0].net_pay == slips[0].net_pay


async def test_two_periods_in_one_book_cannot_share_a_name(session):
    identity, books, payroll, owner, book, first = await team_with_income(session)
    second = await payroll.open_period(owner.id, book.id, "اردیبهشت",
                                       date(2025, 5, 1), date(2025, 5, 31))
    with pytest.raises(ValidationError):
        await payroll.rename_period(owner.id, second.id, first.label)


async def test_a_member_cannot_rename_a_period(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    member = await add_member(session, books, identity, book, owner, "عضو")
    with pytest.raises(PermissionDenied):
        await payroll.rename_period(member.id, period.id, "هرچی")


# --------------------------------------------------- moving a period's window
async def test_two_periods_may_not_cover_the_same_day(session):
    """Overlap means one day's income divided twice, and two people paid for it."""
    identity, books, payroll, owner, book, period = await team_with_income(session)

    with pytest.raises(ValidationError) as refused:
        await payroll.open_period(owner.id, book.id, "دوم",
                                  date(2025, 4, 15), date(2025, 5, 15))
    assert "هم‌پوشانی" in str(refused.value)
    assert len(await payroll.periods(book.id, owner.id)) == 1


async def test_a_period_next_to_another_is_allowed(session):
    """Touching is not overlapping: one ends the day before the next starts."""
    identity, books, payroll, owner, book, period = await team_with_income(session)
    nxt = await payroll.open_period(owner.id, book.id, "اردیبهشت",
                                    date(2025, 5, 1), date(2025, 5, 31))
    assert nxt.starts_on == date(2025, 5, 1)


async def test_moving_a_window_changes_what_the_period_divides(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    assert (await payroll.compute_distribution(period.id)).gross_income == Decimal("10000000")

    # The income is dated START; end the period the day before it.
    await payroll.reschedule_period(owner.id, period.id, ends_on=START - timedelta(days=1),
                                    starts_on=START - timedelta(days=10))
    await session.flush()
    assert (await payroll.compute_distribution(period.id)).gross_income == ZERO_INCOME


async def test_moving_a_window_recalculates_the_payslips(session):
    """A payslip is a snapshot of a window. Move the window and it is stale."""
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    before = (await payroll.calculate(owner.id, period.id))[0]
    assert before.net_pay == Decimal("8000000")      # 10m income − 2m costs

    # A window after the income, but still inside the share rule's life, so
    # the member keeps a share and it is worth nothing.
    await payroll.reschedule_period(owner.id, period.id,
                                    starts_on=END + timedelta(days=1),
                                    ends_on=END + timedelta(days=10))
    await session.flush()

    after = (await payroll.payslips(owner.id, period.id))[0]
    assert after.net_pay == ZERO_INCOME
    # Updated in place rather than replaced, so a payment made against it
    # would have stayed with it.
    assert after.id == before.id


async def test_a_window_cannot_move_onto_another_period(session):
    identity, books, payroll, owner, book, first = await team_with_income(session)
    second = await payroll.open_period(owner.id, book.id, "اردیبهشت",
                                       date(2025, 5, 1), date(2025, 5, 31))
    with pytest.raises(ValidationError):
        await payroll.reschedule_period(owner.id, second.id, starts_on=date(2025, 4, 20))
    await session.refresh(second)
    assert second.starts_on == date(2025, 5, 1)


async def test_a_window_cannot_end_before_it_starts(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    with pytest.raises(ValidationError):
        await payroll.reschedule_period(owner.id, period.id, ends_on=START - timedelta(days=1))


async def test_a_period_that_paid_somebody_can_still_move_its_window(session):
    """Moving the window recalculates, and recalculating keeps the payments.

    It used to be refused, because recalculating replaced the payslips and the
    payments went with them. Here the window moves off the income entirely, so
    the member has been paid for a period that now produced nothing — and the
    payslip says exactly that rather than forgetting the money went out.
    """
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    slip = (await payroll.calculate(owner.id, period.id))[0]
    await payroll.pay(owner.id, slip.id, "1000000", paid_on=START)
    await session.flush()

    await payroll.reschedule_period(owner.id, period.id,
                                    starts_on=END + timedelta(days=1),
                                    ends_on=END + timedelta(days=10))
    await session.flush()

    after = (await payroll.payslips(owner.id, period.id))[0]
    assert after.id == slip.id
    assert after.net_pay == ZERO_INCOME
    assert after.paid_total == Decimal("1000000")
    assert after.overpaid == Decimal("1000000")


async def test_a_member_cannot_move_a_period(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    member = await add_member(session, books, identity, book, owner, "عضو")
    with pytest.raises(PermissionDenied):
        await payroll.reschedule_period(member.id, period.id, ends_on=END + timedelta(days=1))


async def test_another_accounts_period_cannot_be_moved(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    stranger = await identity.create_user("غریبه")
    with pytest.raises(NotFound):
        await payroll.reschedule_period(stranger.id, period.id, ends_on=END)


# ------------------------------------------------- undoing a period's payroll
async def test_a_calculated_period_still_takes_entries(session):
    """A live book cannot stop taking entries because a payslip was issued.

    Calculating a period that is still running used to refuse everything dated
    inside it — including today. A payslip is a snapshot; when the numbers move
    under it, it is recalculated.
    """
    from kasbbook.modules.ledger.models import Flow, Scope
    from kasbbook.modules.ledger.service import LedgerService

    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    await payroll.calculate(owner.id, period.id)

    ledger = LedgerService(session)
    tx = await ledger.record(book.id, owner.id, Flow.EXPENSE, Scope.TEAM, "سرور",
                             "5000", occurred_on=START)
    assert tx.converted_amount == Decimal("5000.0000")
    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit

    # And recalculating picks the new cost up.
    again = await payroll.calculate(owner.id, period.id)
    assert again[0].net_pay == Decimal("7995000")      # 10m − 2m − 5k


async def test_a_paid_period_still_takes_entries(session):
    """Paying the members does not close the month.

    Income that arrives a day late had nowhere to go but the wrong month. It
    goes in its own period now, and once recalculated the difference is simply
    what the member is still owed — the payment already made stays where it is.
    """
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    slip = (await payroll.calculate(owner.id, period.id))[0]
    await payroll.pay(owner.id, slip.id, slip.net_pay, paid_on=START)     # 8m, in full
    await session.flush()

    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.TEAM, "پروژه",
                        "3000000", occurred_on=END)
    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit

    again = (await payroll.calculate(owner.id, period.id))[0]
    assert again.id == slip.id
    assert again.net_pay == Decimal("11000000")         # 13m income − 2m costs
    assert again.paid_total == Decimal("8000000")
    assert again.remaining == Decimal("3000000")
    assert again.overpaid == ZERO_INCOME


async def test_discarding_a_calculation_removes_its_payslips(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    await payroll.calculate(owner.id, period.id)

    assert await payroll.discard_calculation(owner.id, period.id) == 1
    await session.flush()
    assert await payroll.payslips(owner.id, period.id) == []


async def test_discarding_also_releases_the_treasury_allocation(session):
    from kasbbook.modules.treasury.service import TreasuryService

    identity, books, payroll, owner, book, period = await team_with_income(session)
    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "خزانه", FundKind.MAIN)
    await treasury.add_rule(book.id, owner.id, fund.id, RuleBasis.GROSS_PERCENT,
                            Decimal("50"), effective_from=START)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    await payroll.calculate(owner.id, period.id)
    assert await treasury.balance(book.id, owner.id, fund.id) == Decimal("5000000")

    await payroll.discard_calculation(owner.id, period.id)
    await session.flush()
    assert await treasury.balance(book.id, owner.id, fund.id) == ZERO_INCOME


async def test_a_period_that_paid_somebody_keeps_its_payslips(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    slip = (await payroll.calculate(owner.id, period.id))[0]
    await payroll.pay(owner.id, slip.id, "1000000", paid_on=START)
    await session.flush()

    with pytest.raises(PermissionDenied):
        await payroll.discard_calculation(owner.id, period.id)
    assert len(await payroll.payslips(owner.id, period.id)) == 1


async def test_a_payslip_recalculated_below_what_was_paid_says_so(session):
    """A cost that arrives after payment leaves the member paid beyond their share.

    That is real money and must be seen. Folded into "settled", the payslip
    would have said all was well.
    """
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    slip = (await payroll.calculate(owner.id, period.id))[0]
    await payroll.pay(owner.id, slip.id, slip.net_pay, paid_on=START)     # 8m
    await LedgerService(session).record(book.id, owner.id, Flow.EXPENSE, Scope.TEAM,
                                        "سرور", "1000000", occurred_on=END)
    await session.flush()

    again = (await payroll.calculate(owner.id, period.id))[0]
    assert again.net_pay == Decimal("7000000")
    assert again.is_settled
    assert again.overpaid == Decimal("1000000")

    # Nothing is owed, so nothing more can be paid — and the refusal is Persian.
    with pytest.raises(ValidationError) as refused:
        await payroll.pay(owner.id, again.id, "1000", paid_on=END)
    assert "مانده نیست" in str(refused.value)


async def test_paying_more_than_is_left_says_what_is_left_in_persian(session):
    """This message reached a person in English: "only 2.4959 is still owed"."""
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    slip = (await payroll.calculate(owner.id, period.id))[0]
    await payroll.pay(owner.id, slip.id, "6500000", paid_on=START)

    with pytest.raises(ValidationError) as refused:
        await payroll.pay(owner.id, slip.id, "2000000", paid_on=START)
    assert "1,500,000" in str(refused.value)
    assert "owed" not in str(refused.value)


async def test_a_member_whose_share_ended_keeps_what_they_were_paid(session):
    """No share on the period's last day means no payslip — unless they were paid.

    Deleting that payslip would delete the payments with it. It stays at
    nothing, and what they were given reads as paid beyond their share.
    """
    from kasbbook.shared import jalali

    identity = IdentityService(session)
    books = BookService(session)
    payroll = PayrollService(session)
    owner = await identity.create_user("مالک")
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)
    paid_one = await add_member(session, books, identity, book, owner, "پرداخت‌شده")
    unpaid_one = await add_member(session, books, identity, book, owner, "پرداخت‌نشده")

    today = jalali.today_in(book.timezone)
    await LedgerService(session).record(book.id, owner.id, Flow.INCOME, Scope.TEAM,
                                        "پروژه", "9000000", occurred_on=today)
    for person in (owner, paid_one, unpaid_one):
        share(session, book, person, ShareBasis.PROJECT, 1, start=START)
    period = await payroll.open_period(owner.id, book.id, "جاری",
                                       today - timedelta(days=3), today + timedelta(days=3))
    await session.flush()

    slips = {s.user_id: s for s in await payroll.calculate(owner.id, period.id)}
    await payroll.pay(owner.id, slips[paid_one.id].id, "1000000", paid_on=today)
    for person in (paid_one, unpaid_one):
        await payroll.clear_share(book.id, owner.id, person.id)
    await session.flush()

    again = {s.user_id: s for s in await payroll.calculate(owner.id, period.id)}
    await session.flush()

    assert unpaid_one.id not in again
    assert again[paid_one.id].id == slips[paid_one.id].id
    assert again[paid_one.id].net_pay == ZERO_INCOME
    assert again[paid_one.id].overpaid == Decimal("1000000")
    assert again[owner.id].net_pay == Decimal("9000000")      # the only share left


async def test_clearing_a_share_keeps_the_past(session):
    """Clearing used to switch the rule off for every day, history included.

    A past period recalculated afterwards then found no share for the member,
    and now that a period which has paid out can be recalculated, that would
    have turned every payment to them into an overpayment.
    """
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    slip = (await payroll.calculate(owner.id, period.id))[0]
    await payroll.pay(owner.id, slip.id, slip.net_pay, paid_on=START)

    await payroll.clear_share(book.id, owner.id, owner.id)
    await session.flush()

    assert await payroll.shares(book.id, owner.id) == {}         # none from today
    again = (await payroll.calculate(owner.id, period.id))[0]    # last April's
    assert again.net_pay == Decimal("8000000")
    assert again.overpaid == ZERO_INCOME


async def test_clearing_a_share_that_had_not_started_withdraws_it(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    future = share(session, book, owner, ShareBasis.PERCENT, 100,
                   start=date.today() + timedelta(days=30))
    await session.flush()

    await payroll.clear_share(book.id, owner.id, owner.id)
    await session.flush()
    assert future.is_active is False


async def test_a_member_cannot_clear_a_share(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    rule = share(session, book, owner, ShareBasis.PERCENT, 100)
    member = await add_member(session, books, identity, book, owner, "عضو")
    await session.flush()

    with pytest.raises(PermissionDenied):
        await payroll.clear_share(book.id, member.id, owner.id)
    assert rule.effective_to is None and rule.is_active


async def test_another_account_cannot_clear_a_share(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    rule = share(session, book, owner, ShareBasis.PERCENT, 100)
    stranger = await identity.create_user("غریبه")
    await session.flush()

    with pytest.raises(NotFound):
        await payroll.clear_share(book.id, stranger.id, owner.id)
    assert rule.effective_to is None and rule.is_active


async def test_a_member_cannot_discard_a_calculation(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    await payroll.calculate(owner.id, period.id)
    member = await add_member(session, books, identity, book, owner, "عضو")

    with pytest.raises(PermissionDenied):
        await payroll.discard_calculation(member.id, period.id)
    assert len(await payroll.payslips(owner.id, period.id)) == 1


async def test_another_accounts_calculation_cannot_be_discarded(session):
    identity, books, payroll, owner, book, period = await team_with_income(session)
    share(session, book, owner, ShareBasis.PERCENT, 100)
    await session.flush()
    await payroll.calculate(owner.id, period.id)
    stranger = await identity.create_user("غریبه")

    with pytest.raises(NotFound):
        await payroll.discard_calculation(stranger.id, period.id)
    assert len(await payroll.payslips(owner.id, period.id)) == 1


# ------------------------------------------- a treasury rule for one category
async def test_a_rule_named_for_a_category_takes_only_that_category(session):
    """The column said so from the start and nothing read it.

    A rule meant for one kind of income quietly took a cut of all of it.
    """
    from kasbbook.modules.ledger.models import Flow, Scope
    from kasbbook.modules.ledger.service import LedgerService
    from kasbbook.modules.treasury.service import TreasuryService

    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=""
    )
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.TEAM, "مشاوره",
                        "4000000", occurred_on=START)

    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "خزانه", FundKind.MAIN)
    await treasury.add_rule(book.id, owner.id, fund.id, RuleBasis.GROSS_PERCENT,
                            Decimal("100"), effective_from=START, category="مشاوره")
    await session.flush()

    d = await payroll.compute_distribution(period.id)
    assert d.gross_income == Decimal("14000000")
    # The whole of the consultancy income, and none of the project income.
    assert d.treasury_total == Decimal("4000000")
    assert d.distributable == Decimal("10000000")


async def test_a_category_rule_takes_nothing_when_that_income_is_absent(session):
    from kasbbook.modules.treasury.service import TreasuryService

    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=""
    )
    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "خزانه", FundKind.MAIN)
    await treasury.add_rule(book.id, owner.id, fund.id, RuleBasis.GROSS_PERCENT,
                            Decimal("50"), effective_from=START, category="چیزی که نیست")
    await session.flush()

    assert (await payroll.compute_distribution(period.id)).treasury_total == ZERO_INCOME


async def test_a_category_rule_charges_that_income_whichever_basis(session):
    """A category carries one flow, so it has no costs of its own to net off.

    Gross and net therefore agree for a category rule, and both charge that
    category's income rather than the whole book's.
    """
    from kasbbook.modules.ledger.models import Flow, Scope
    from kasbbook.modules.ledger.service import LedgerService
    from kasbbook.modules.treasury.service import TreasuryService

    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs="2000000"
    )
    await LedgerService(session).record(book.id, owner.id, Flow.INCOME, Scope.TEAM,
                                        "مشاوره", "4000000", occurred_on=START)

    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "خزانه", FundKind.MAIN)
    await treasury.add_rule(book.id, owner.id, fund.id, RuleBasis.NET_PERCENT,
                            Decimal("50"), effective_from=START, category="مشاوره")
    await session.flush()

    # Half of the consultancy income; the book's other 10m and its costs are
    # not this rule's business.
    assert (await payroll.compute_distribution(period.id)).treasury_total == Decimal("2000000")


async def test_a_rule_with_no_category_still_takes_everything(session):
    """The behaviour every existing book depends on must not move."""
    from kasbbook.modules.treasury.service import TreasuryService

    identity, books, payroll, owner, book, period = await team_with_income(
        session, income="10000000", costs=""
    )
    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "خزانه", FundKind.MAIN)
    await treasury.add_rule(book.id, owner.id, fund.id, RuleBasis.GROSS_PERCENT,
                            Decimal("50"), effective_from=START)
    await session.flush()
    assert (await payroll.compute_distribution(period.id)).treasury_total == Decimal("5000000")
