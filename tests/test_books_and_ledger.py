"""Books stay separate, permissions hold, and the ledger balances.

The rules under test are the ones a user would notice being broken: team income
never showing up as personal income, a viewer never being able to spend, and
totals that still add up a year later.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from kasbbook.modules.books.models import BookType, Permission, Role
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, RateMode, Scope
from kasbbook.modules.ledger.service import CASH, INCOME, LedgerService
from kasbbook.shared.errors import BalanceError, NotFound, PermissionDenied, ValidationError

pytestmark = pytest.mark.asyncio


async def setup_owner(session, name="عماد"):
    identity = IdentityService(session)
    user = await identity.create_user(name)
    books = BookService(session)
    return books, user


# ------------------------------------------------------------------- money
async def test_money_survives_the_round_trip_exactly(session):
    """A float would quietly turn 0.1 + 0.2 into 0.30000000000000004."""
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "شخصی", BookType.PERSONAL)
    ledger = LedgerService(session)

    for amount in ("0.1", "0.2", "12345678.9999"):
        tx = await ledger.record(
            book.id, user.id, Flow.INCOME, Scope.PERSONAL, "فروش", amount
        )
        assert tx.original_amount == Decimal(amount)
        assert isinstance(tx.original_amount, Decimal)


# ------------------------------------------------------------- book scoping
async def test_a_user_only_sees_books_they_belong_to(session):
    identity = IdentityService(session)
    mine = await identity.create_user("من")
    stranger = await identity.create_user("غریبه")
    books = BookService(session)

    await books.create_book(mine.id, "شخصی", BookType.PERSONAL)
    await books.create_book(stranger.id, "مال او", BookType.PERSONAL)

    assert [b.name for b in await books.books_for_user(mine.id)] == ["شخصی"]
    assert [b.name for b in await books.books_for_user(stranger.id)] == ["مال او"]


async def test_personal_business_and_team_money_never_mix(session):
    books, user = await setup_owner(session)
    personal = await books.create_book(user.id, "شخصی", BookType.PERSONAL)
    business = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS)
    team = await books.create_book(user.id, "تیم", BookType.TEAM)
    ledger = LedgerService(session)

    await ledger.record(personal.id, user.id, Flow.INCOME, Scope.PERSONAL, "هدیه", 100)
    await ledger.record(business.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 500)
    await ledger.record(team.id, user.id, Flow.INCOME, Scope.TEAM, "پروژه", 900)

    assert (await ledger.totals(personal.id, user.id))["income"] == Decimal("100")
    assert (await ledger.totals(business.id, user.id))["income"] == Decimal("500")
    assert (await ledger.totals(team.id, user.id))["income"] == Decimal("900")


async def test_a_stranger_cannot_read_another_books_transactions(session):
    identity = IdentityService(session)
    owner = await identity.create_user("مالک")
    stranger = await identity.create_user("غریبه")
    books = BookService(session)
    ledger = LedgerService(session)

    book = await books.create_book(owner.id, "تیم", BookType.TEAM)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.TEAM, "پروژه", 100)

    # Reported as "not found", not "forbidden", so book ids cannot be probed.
    with pytest.raises(NotFound):
        await ledger.transactions(book.id, stranger.id)


# -------------------------------------------------------------- permissions
async def test_each_role_gets_exactly_the_permissions_it_should(session):
    books, owner = await setup_owner(session)
    identity = IdentityService(session)
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)

    expectations = {
        Role.VIEWER: {Permission.VIEW_REPORTS, Permission.VIEW_TRANSACTIONS},
        Role.MEMBER: {Permission.RECORD_INCOME, Permission.RECORD_EXPENSE},
        Role.ACCOUNTANT: {Permission.MANAGE_PAYROLL, Permission.APPROVE_EXPENSE},
    }
    for role, granted in expectations.items():
        member = await identity.create_user(f"عضو {role.value}")
        await books.add_member(owner.id, book.id, member.id, role)
        perms = await books.permissions_for(book.id, member.id)
        assert granted <= perms, f"{role} is missing {granted - perms}"

    viewer = await identity.create_user("بیننده")
    await books.add_member(owner.id, book.id, viewer.id, Role.VIEWER)
    assert not await books.can(book.id, viewer.id, Permission.RECORD_EXPENSE)
    assert not await books.can(book.id, viewer.id, Permission.MANAGE_MEMBERS)


async def test_a_viewer_cannot_record_a_transaction(session):
    books, owner = await setup_owner(session)
    identity = IdentityService(session)
    ledger = LedgerService(session)

    book = await books.create_book(owner.id, "تیم", BookType.TEAM)
    viewer = await identity.create_user("بیننده")
    await books.add_member(owner.id, book.id, viewer.id, Role.VIEWER)

    with pytest.raises(PermissionDenied):
        await ledger.record(book.id, viewer.id, Flow.EXPENSE, Scope.TEAM, "خرید", 50)


async def test_a_member_cannot_manage_members(session):
    books, owner = await setup_owner(session)
    identity = IdentityService(session)
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)

    member = await identity.create_user("عضو")
    outsider = await identity.create_user("تازه‌وارد")
    await books.add_member(owner.id, book.id, member.id, Role.MEMBER)

    with pytest.raises(PermissionDenied):
        await books.add_member(member.id, book.id, outsider.id, Role.MEMBER)


async def test_a_deactivated_member_loses_every_permission(session):
    books, owner = await setup_owner(session)
    identity = IdentityService(session)
    ledger = LedgerService(session)

    book = await books.create_book(owner.id, "تیم", BookType.TEAM)
    member = await identity.create_user("عضو")
    await books.add_member(owner.id, book.id, member.id, Role.MEMBER)
    await ledger.record(book.id, member.id, Flow.INCOME, Scope.TEAM, "پروژه", 10)

    await books.deactivate_member(owner.id, book.id, member.id)
    with pytest.raises(NotFound):
        await ledger.record(book.id, member.id, Flow.INCOME, Scope.TEAM, "پروژه", 10)


async def test_the_owner_cannot_be_removed_or_demoted(session):
    books, owner = await setup_owner(session)
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)

    with pytest.raises(ValidationError):
        await books.deactivate_member(owner.id, book.id, owner.id)
    with pytest.raises(ValidationError):
        await books.change_role(owner.id, book.id, owner.id, Role.VIEWER)


async def test_ownership_transfer_swaps_both_sides(session):
    books, owner = await setup_owner(session)
    identity = IdentityService(session)
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)

    successor = await identity.create_user("جانشین")
    await books.add_member(owner.id, book.id, successor.id, Role.ADMIN)
    await books.transfer_ownership(owner.id, book.id, successor.id)

    assert (await books.get_book(book.id)).owner_user_id == successor.id
    assert (await books.membership(book.id, successor.id)).role is Role.OWNER
    assert (await books.membership(book.id, owner.id)).role is Role.ADMIN


async def test_only_the_owner_may_transfer_a_book(session):
    books, owner = await setup_owner(session)
    identity = IdentityService(session)
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)

    admin = await identity.create_user("ادمین")
    await books.add_member(owner.id, book.id, admin.id, Role.ADMIN)

    with pytest.raises(PermissionDenied):
        await books.transfer_ownership(admin.id, book.id, admin.id)


# ------------------------------------------------------------------ ledger
async def test_every_transaction_writes_a_balanced_entry(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS)
    ledger = LedgerService(session)

    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", "250000")
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", "120000")

    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit == Decimal("370000")


async def test_the_ledger_stays_balanced_over_many_transactions(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS)
    ledger = LedgerService(session)

    for i in range(40):
        flow = Flow.INCOME if i % 3 else Flow.EXPENSE
        await ledger.record(book.id, user.id, flow, Scope.WORK, f"ردیف {i}", 1000 + i)

    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit


async def test_cash_and_income_accounts_move_the_right_way(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS)
    ledger = LedgerService(session)

    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", "500")
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "خرید", "200")

    cash = await ledger.account(book.id, CASH)
    income = await ledger.account(book.id, INCOME)

    assert await ledger.account_balance(cash.id) == Decimal("300")
    assert await ledger.account_balance(income.id) == Decimal("500")


async def test_an_unbalanced_entry_is_refused(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS)
    ledger = LedgerService(session)
    await ledger.ensure_chart_of_accounts(book.id)

    cash = await ledger.account(book.id, CASH)
    income = await ledger.account(book.id, INCOME)

    with pytest.raises(BalanceError):
        await ledger.post_entry(
            book.id,
            date.today(),
            [(cash.id, 100, 0), (income.id, 0, 90)],
        )


async def test_a_line_cannot_be_both_a_debit_and_a_credit(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS)
    ledger = LedgerService(session)
    await ledger.ensure_chart_of_accounts(book.id)
    cash = await ledger.account(book.id, CASH)

    with pytest.raises(BalanceError):
        await ledger.post_entry(book.id, date.today(), [(cash.id, 50, 50), (cash.id, 0, 0)])


async def test_a_negative_amount_is_refused(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "شخصی", BookType.PERSONAL)
    ledger = LedgerService(session)

    with pytest.raises(ValidationError):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.PERSONAL, "خرید", -5)


# ------------------------------------------------------------- multi-currency
async def test_a_foreign_amount_keeps_both_sides_and_its_rate(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS, "IRT")
    ledger = LedgerService(session)

    tx = await ledger.record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "پروژه خارجی",
        amount="100", currency="USDT", conversion_rate="90000",
        rate_source="swapwallet", rate_mode=RateMode.AUTOMATIC,
    )

    assert tx.original_amount == Decimal("100")
    assert tx.original_currency == "USDT"
    assert tx.conversion_rate == Decimal("90000")
    assert tx.converted_amount == Decimal("9000000")
    assert tx.base_currency == "IRT"
    assert tx.rate_source == "swapwallet"
    assert tx.rate_mode is RateMode.AUTOMATIC


async def test_a_foreign_amount_without_a_rate_is_refused(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS, "IRT")
    ledger = LedgerService(session)

    with pytest.raises(ValidationError):
        await ledger.record(
            book.id, user.id, Flow.INCOME, Scope.WORK, "پروژه", 100, currency="TON"
        )


async def test_a_past_report_does_not_move_when_the_rate_moves(session):
    """The whole point of storing the rate: history is not rewritten."""
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS, "IRT")
    ledger = LedgerService(session)

    old = await ledger.record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروردین",
        amount="10", currency="USDT", conversion_rate="60000",
        occurred_on=date(2025, 4, 10),
    )
    await ledger.record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "مرداد",
        amount="10", currency="USDT", conversion_rate="90000",
        occurred_on=date(2025, 8, 10),
    )

    assert old.converted_amount == Decimal("600000")
    totals = await ledger.totals(book.id, user.id)
    assert totals["income"] == Decimal("1500000")  # 600k + 900k, not 2 x 900k


async def test_the_ledger_balances_with_mixed_currencies(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS, "IRT")
    ledger = LedgerService(session)

    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "ریالی", "500000")
    await ledger.record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "تتری",
        amount="12.5", currency="USDT", conversion_rate="88888.8888",
    )

    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit


# ------------------------------------------------------------------- dates
async def test_a_date_range_narrows_the_totals(session):
    books, user = await setup_owner(session)
    book = await books.create_book(user.id, "کسب‌وکار", BookType.BUSINESS)
    ledger = LedgerService(session)

    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "الف", 100,
                        occurred_on=date(2025, 1, 5))
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "ب", 200,
                        occurred_on=date(2025, 6, 5))

    scoped = await ledger.totals(
        book.id, user.id, since=date(2025, 6, 1), until=date(2025, 6, 30)
    )
    assert scoped["income"] == Decimal("200")
