"""Budgets, debts and loans.

Three small domains with one rule each that matters more than the rest:
a budget informs but never blocks, a debt never touches the ledger, and a
deleted loan keeps its payments.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from kasbbook.modules.books.models import BookType, Permission, Role
from kasbbook.modules.books.service import BookService
from kasbbook.modules.budgets.models import BudgetKind
from kasbbook.modules.budgets.service import BudgetService
from kasbbook.modules.debts.models import Direction
from kasbbook.modules.debts.service import DebtService
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.loans.service import INSTALLMENT_CATEGORY, LoanService
from kasbbook.shared import jalali
from kasbbook.shared.errors import PermissionDenied, NotFound, ValidationError

pytestmark = pytest.mark.asyncio


async def setup(session):
    user = await IdentityService(session).create_user("عماد")
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    return user, book


# ------------------------------------------------------------------ budgets
async def test_a_budget_is_raised_rather_than_duplicated(session):
    user, book = await setup(session)
    service = BudgetService(session)

    await service.set_budget(book.id, user.id, BudgetKind.CATEGORY, "اجاره", 100_000)
    await service.set_budget(book.id, user.id, BudgetKind.CATEGORY, "اجاره", 200_000)

    budgets = await service.list_budgets(book.id, user.id)
    assert len(budgets) == 1
    assert budgets[0].amount == Decimal("200000")


async def test_a_budget_must_be_a_positive_amount(session):
    user, book = await setup(session)
    with pytest.raises(ValidationError):
        await BudgetService(session).set_budget(
            book.id, user.id, BudgetKind.CATEGORY, "اجاره", 0
        )


async def test_spending_is_counted_only_inside_the_month(session):
    user, book = await setup(session)
    ledger = LedgerService(session)
    service = BudgetService(session)

    await service.set_budget(book.id, user.id, BudgetKind.CATEGORY, "اجاره", 1_000_000)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 400_000,
                        occurred_on=jalali.from_parts(1404, 5, 10))
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 900_000,
                        occurred_on=jalali.from_parts(1404, 6, 10))

    status = (await service.status(book.id, user.id, 1404, 5))[0]
    assert status.spent == Decimal("400000")
    assert status.remaining == Decimal("600000")
    assert status.percent == 40
    assert not status.over


async def test_a_flow_budget_covers_everything_going_that_way(session):
    user, book = await setup(session)
    ledger = LedgerService(session)
    service = BudgetService(session)

    await service.set_budget(book.id, user.id, BudgetKind.FLOW, Flow.EXPENSE.value, 500)
    for category in ("اجاره", "قبض", "حقوق"):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, category, 100)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 900)

    status = (await service.status(book.id, user.id))[0]
    assert status.spent == Decimal("300")  # income is not counted against it


async def test_crossing_a_budget_warns_but_never_blocks(session):
    """The money already moved. Refusing to record it would be a lie."""
    user, book = await setup(session)
    ledger = LedgerService(session)
    service = BudgetService(session)

    await service.set_budget(book.id, user.id, BudgetKind.CATEGORY, "اجاره", 1_000)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 1_500)

    warning = await service.warning_for(
        book.id, user.id, "اجاره", Flow.EXPENSE, date.today()
    )
    assert warning is not None and "رد شد" in warning

    # And the transaction is there regardless.
    assert len(await ledger.transactions(book.id, user.id)) == 1


async def test_approaching_a_budget_is_mentioned_before_it_is_crossed(session):
    user, book = await setup(session)
    await BudgetService(session).set_budget(
        book.id, user.id, BudgetKind.CATEGORY, "اجاره", 1_000
    )
    await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 850
    )

    warning = await BudgetService(session).warning_for(
        book.id, user.id, "اجاره", Flow.EXPENSE, date.today()
    )
    assert warning is not None and "%" in warning


async def test_a_category_with_no_budget_says_nothing(session):
    user, book = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "چای", 999_999
    )
    assert await BudgetService(session).warning_for(
        book.id, user.id, "چای", Flow.EXPENSE, date.today()
    ) is None


async def test_a_plain_member_cannot_set_a_budget(session):
    owner, book = await setup(session)
    member = await IdentityService(session).create_user("عضو")
    await BookService(session).add_member(owner.id, book.id, member.id, Role.MEMBER)

    with pytest.raises(PermissionDenied):
        await BudgetService(session).set_budget(
            book.id, member.id, BudgetKind.CATEGORY, "اجاره", 100
        )


# -------------------------------------------------------------------- debts
async def test_a_debt_never_writes_to_the_ledger(session):
    """A credit sale is already income; the debt is the other half, not a repeat."""
    user, book = await setup(session)
    ledger = LedgerService(session)

    await DebtService(session).create(
        book.id, user.id, "علی", Direction.OWED_TO_ME, 500_000
    )

    assert await ledger.transactions(book.id, user.id) == []
    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit == Decimal("0")


async def test_totals_net_the_two_directions(session):
    user, book = await setup(session)
    service = DebtService(session)

    await service.create(book.id, user.id, "علی", Direction.OWED_TO_ME, 500_000)
    await service.create(book.id, user.id, "بانک", Direction.I_OWE, 300_000)

    totals = await service.totals(book.id, user.id)
    assert totals.owed_to_me == Decimal("500000")
    assert totals.i_owe == Decimal("300000")
    assert totals.net == Decimal("200000")


async def test_settling_leaves_the_totals_but_keeps_the_history(session):
    user, book = await setup(session)
    service = DebtService(session)

    debt = await service.create(book.id, user.id, "علی", Direction.OWED_TO_ME, 500_000)
    await service.settle(book.id, user.id, debt.id)

    assert (await service.totals(book.id, user.id)).owed_to_me == Decimal("0")
    assert await service.list_debts(book.id, user.id) == []
    assert len(await service.list_debts(book.id, user.id, include_settled=True)) == 1


async def test_a_debt_needs_a_person(session):
    user, book = await setup(session)
    with pytest.raises(ValidationError):
        await DebtService(session).create(
            book.id, user.id, "   ", Direction.I_OWE, 100
        )


async def test_debts_are_scoped_to_their_book(session):
    user, book = await setup(session)
    other = await BookService(session).create_book(user.id, "دیگر", BookType.PERSONAL)
    debt = await DebtService(session).create(
        book.id, user.id, "علی", Direction.OWED_TO_ME, 100
    )

    with pytest.raises(NotFound):
        await DebtService(session).settle(other.id, user.id, debt.id)


# -------------------------------------------------------------------- loans
async def test_a_new_loan_owes_every_installment(session):
    user, book = await setup(session)
    service = LoanService(session)

    loan = await service.create(
        book.id, user.id, "وام مسکن", 2_000_000, 24, date(2025, 4, 10)
    )
    progress = await service.progress(book.id, user.id, loan)

    assert progress.paid_count == 0
    assert progress.remaining_count == 24
    assert progress.remaining_amount == Decimal("48000000")
    assert progress.total_amount == Decimal("48000000")
    assert progress.percent == 0


async def test_a_payment_is_a_real_expense_in_the_ledger(session):
    user, book = await setup(session)
    service = LoanService(session)
    loan = await service.create(book.id, user.id, "وام", 1_000, 6, date(2025, 4, 10))

    transaction = await service.record_payment(book.id, user.id, loan.id)

    assert transaction.flow is Flow.EXPENSE
    assert transaction.category == INSTALLMENT_CATEGORY
    assert transaction.description == "وام"
    assert transaction.converted_amount == Decimal("1000")

    debit, credit = await LedgerService(session).trial_balance(book.id)
    assert debit == credit


async def test_paying_advances_what_is_left(session):
    user, book = await setup(session)
    service = LoanService(session)
    loan = await service.create(book.id, user.id, "وام", 1_000, 6, date(2025, 4, 10))

    await service.record_payment(book.id, user.id, loan.id)
    await service.record_payment(book.id, user.id, loan.id)

    progress = await service.progress(book.id, user.id, loan)
    assert progress.paid_count == 2
    assert progress.remaining_count == 4
    assert progress.paid_amount == Decimal("2000")
    assert progress.percent == 33


async def test_the_due_dates_step_a_jalali_month_at_a_time(session):
    user, book = await setup(session)
    service = LoanService(session)
    start = jalali.from_parts(1404, 1, 15)
    loan = await service.create(book.id, user.id, "وام", 1_000, 6, start)

    progress = await service.progress(book.id, user.id, loan)
    dates = progress.due_dates

    assert len(dates) == 6
    assert dates[0] == start
    assert dates == sorted(dates)
    assert jalali.to_parts(dates[1])[1] == 2  # ordibehesht


async def test_the_next_due_date_moves_after_a_payment(session):
    user, book = await setup(session)
    service = LoanService(session)
    loan = await service.create(book.id, user.id, "وام", 1_000, 3, date(2025, 4, 10))

    before = (await service.progress(book.id, user.id, loan)).next_due
    await service.record_payment(book.id, user.id, loan.id)
    after = (await service.progress(book.id, user.id, loan)).next_due

    assert after > before


async def test_a_fully_paid_loan_has_nothing_due(session):
    user, book = await setup(session)
    service = LoanService(session)
    loan = await service.create(book.id, user.id, "وام", 1_000, 2, date(2025, 4, 10))

    await service.record_payment(book.id, user.id, loan.id)
    await service.record_payment(book.id, user.id, loan.id)

    progress = await service.progress(book.id, user.id, loan)
    assert progress.next_due is None
    assert progress.remaining_amount == Decimal("0")
    assert progress.percent == 100


async def test_deleting_a_loan_keeps_the_money_that_moved(session):
    user, book = await setup(session)
    service = LoanService(session)
    loan = await service.create(book.id, user.id, "وام", 1_000, 6, date(2025, 4, 10))
    await service.record_payment(book.id, user.id, loan.id)

    await service.delete(book.id, user.id, loan.id)

    with pytest.raises(NotFound):
        await service.get(book.id, user.id, loan.id)

    # The expense is still on the books.
    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].category == INSTALLMENT_CATEGORY

    debit, credit = await LedgerService(session).trial_balance(book.id)
    assert debit == credit


async def test_a_loan_needs_a_positive_amount_and_count(session):
    user, book = await setup(session)
    service = LoanService(session)

    with pytest.raises(ValidationError):
        await service.create(book.id, user.id, "وام", 0, 6, date(2025, 4, 10))
    with pytest.raises(ValidationError):
        await service.create(book.id, user.id, "وام", 100, 0, date(2025, 4, 10))
    with pytest.raises(ValidationError):
        await service.create(book.id, user.id, "  ", 100, 6, date(2025, 4, 10))


async def test_a_stranger_cannot_see_another_books_loans(session):
    """A non-member is told the book does not exist, so ids cannot be probed."""
    owner, book = await setup(session)
    stranger = await IdentityService(session).create_user("غریبه")

    with pytest.raises(NotFound):
        await LoanService(session).list_loans(book.id, stranger.id)
