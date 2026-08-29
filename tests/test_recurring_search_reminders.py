"""Recurring rules, receipts, search and reminders.

The four things the first-generation bot did that the new one did not yet.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.debts.models import Direction
from kasbbook.modules.debts.service import DebtService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.loans.service import LoanService
from kasbbook.modules.recurring.models import Period
from kasbbook.modules.recurring.service import RecurringService, next_run_after
from kasbbook.modules.reminders.service import ReminderService
from kasbbook.modules.reports.service import ReportService
from kasbbook.shared import jalali
from kasbbook.shared.errors import NotFound, ValidationError

pytestmark = pytest.mark.asyncio


async def setup(session, book_type=BookType.BUSINESS):
    user = await IdentityService(session).create_user("عماد")
    book = await BookService(session).create_book(user.id, "مغازه", book_type)
    return user, book


# --------------------------------------------------------------- recurring
async def test_a_daily_rule_steps_one_day():
    assert next_run_after(Period.DAILY, date(2026, 8, 24)) == date(2026, 8, 25)


async def test_a_weekly_rule_steps_seven_days():
    assert next_run_after(Period.WEEKLY, date(2026, 8, 24)) == date(2026, 8, 31)


async def test_a_monthly_rule_keeps_the_same_jalali_day():
    """The fifth of every month should stay the fifth, not drift by 30 days."""
    start = jalali.from_parts(1405, 5, 5)
    nxt = next_run_after(Period.MONTHLY, start)

    year, month, day = jalali.to_parts(nxt)
    assert (month, day) == (6, 5)


async def test_a_monthly_rule_clamps_onto_a_shorter_month():
    """Starting on Esfand 30 must not fall off a 29-day Esfand."""
    start = jalali.from_parts(1404, 6, 31)
    nxt = next_run_after(Period.MONTHLY, start)

    _, month, day = jalali.to_parts(nxt)
    assert month == 7
    assert day <= 31


async def test_a_due_rule_books_a_transaction(session):
    user, book = await setup(session)
    service = RecurringService(session)

    await service.create(
        book.id, user.id, Flow.EXPENSE, "اجاره", 500_000,
        Period.MONTHLY, date.today(),
    )
    created = await service.run_due()

    assert created == 1
    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].category == "اجاره"
    assert rows[0].converted_amount == Decimal("500000")


async def test_running_twice_does_not_book_twice(session):
    user, book = await setup(session)
    service = RecurringService(session)

    await service.create(
        book.id, user.id, Flow.EXPENSE, "اجاره", 500, Period.MONTHLY, date.today()
    )
    assert await service.run_due() == 1
    assert await service.run_due() == 0

    assert len(await LedgerService(session).transactions(book.id, user.id)) == 1


async def test_downtime_is_caught_up_rather_than_skipped(session):
    """If the bot was off for a week, a daily rule owes seven transactions."""
    user, book = await setup(session)
    service = RecurringService(session)

    start = date.today() - timedelta(days=6)
    await service.create(
        book.id, user.id, Flow.EXPENSE, "قهوه", 100, Period.DAILY, start
    )

    assert await service.run_due() == 7
    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 7
    assert {row.occurred_on for row in rows} == {
        start + timedelta(days=offset) for offset in range(7)
    }


async def test_a_future_rule_waits(session):
    user, book = await setup(session)
    service = RecurringService(session)

    await service.create(
        book.id, user.id, Flow.EXPENSE, "اجاره", 500, Period.MONTHLY,
        date.today() + timedelta(days=10),
    )
    assert await service.run_due() == 0


async def test_a_paused_rule_never_fires(session):
    user, book = await setup(session)
    service = RecurringService(session)

    rule = await service.create(
        book.id, user.id, Flow.EXPENSE, "اجاره", 500, Period.MONTHLY, date.today()
    )
    await service.toggle(book.id, user.id, rule.id)

    assert await service.run_due() == 0
    assert await LedgerService(session).transactions(book.id, user.id) == []


async def test_deleting_a_rule_keeps_what_it_already_booked(session):
    user, book = await setup(session)
    service = RecurringService(session)

    rule = await service.create(
        book.id, user.id, Flow.EXPENSE, "اجاره", 500, Period.MONTHLY, date.today()
    )
    await service.run_due()
    await service.delete(book.id, user.id, rule.id)

    assert await service.list_rules(book.id, user.id) == []
    assert len(await LedgerService(session).transactions(book.id, user.id)) == 1


async def test_a_rule_needs_a_category_and_a_positive_amount(session):
    user, book = await setup(session)
    service = RecurringService(session)

    with pytest.raises(ValidationError):
        await service.create(book.id, user.id, Flow.EXPENSE, "  ", 500,
                             Period.MONTHLY, date.today())
    with pytest.raises(ValidationError):
        await service.create(book.id, user.id, Flow.EXPENSE, "اجاره", 0,
                             Period.MONTHLY, date.today())


async def test_a_recurring_transaction_still_balances_the_ledger(session):
    user, book = await setup(session)
    service = RecurringService(session)

    await service.create(
        book.id, user.id, Flow.INCOME, "حقوق", 9_000, Period.MONTHLY, date.today()
    )
    await service.run_due()

    debit, credit = await LedgerService(session).trial_balance(book.id)
    assert debit == credit == Decimal("9000")


# ---------------------------------------------------------------- receipts
async def test_a_receipt_can_be_attached_and_removed(session):
    user, book = await setup(session)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)

    await ledger.attach_receipt(book.id, user.id, tx.id, "FILE-123", "telegram")
    again = await ledger.get_transaction(book.id, user.id, tx.id)
    assert again.receipt_file_id == "FILE-123"
    assert again.receipt_provider == "telegram"

    await ledger.attach_receipt(book.id, user.id, tx.id, None, None)
    cleared = await ledger.get_transaction(book.id, user.id, tx.id)
    assert cleared.receipt_file_id is None
    assert cleared.receipt_provider is None


async def test_the_provider_is_stored_with_the_file_id(session):
    """A file id is opaque and only means something to the provider that issued it."""
    user, book = await setup(session)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)

    await ledger.attach_receipt(book.id, user.id, tx.id, "BALE-9", "bale")
    stored = await ledger.get_transaction(book.id, user.id, tx.id)
    assert (stored.receipt_file_id, stored.receipt_provider) == ("BALE-9", "bale")


async def test_a_receipt_cannot_be_attached_to_another_books_transaction(session):
    user, book = await setup(session)
    other = await BookService(session).create_book(user.id, "دیگر", BookType.PERSONAL)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)

    with pytest.raises(NotFound):
        await ledger.attach_receipt(other.id, user.id, tx.id, "X", "telegram")


# ------------------------------------------------------------------ search
async def test_search_matches_category_and_note(session):
    user, book = await setup(session)
    ledger = LedgerService(session)
    service = ReportService(session)

    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 900,
                        description="اجاره‌نامه")
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "قبض", 100)

    rows, total, amount = await service.search(book.id, user.id, "اجاره")
    assert total == 2
    assert amount == Decimal("1400")
    assert {row.category for row in rows} == {"اجاره", "فروش"}


async def test_the_search_total_covers_every_match_not_just_the_page(session):
    """"How much did I spend on this" is the real question behind a search."""
    user, book = await setup(session)
    ledger = LedgerService(session)

    for _ in range(15):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "قبض", 100)

    rows, total, amount = await ReportService(session).search(
        book.id, user.id, "قبض", page=0, per_page=10
    )
    assert len(rows) == 10
    assert total == 15
    assert amount == Decimal("1500")


async def test_search_pages(session):
    user, book = await setup(session)
    ledger = LedgerService(session)
    for index in range(15):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, f"قبض {index}", 100)

    first, _, _ = await ReportService(session).search(book.id, user.id, "قبض", 0, 10)
    second, _, _ = await ReportService(session).search(book.id, user.id, "قبض", 1, 10)

    assert len(second) == 5
    assert {row.id for row in first}.isdisjoint({row.id for row in second})


async def test_a_one_character_search_is_refused(session):
    user, book = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500
    )

    rows, total, amount = await ReportService(session).search(book.id, user.id, "ا")
    assert (rows, total, amount) == ([], 0, Decimal("0"))


async def test_search_does_not_cross_books(session):
    user, book = await setup(session)
    other = await BookService(session).create_book(user.id, "دیگر", BookType.PERSONAL)
    ledger = LedgerService(session)

    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)
    await ledger.record(other.id, user.id, Flow.EXPENSE, Scope.PERSONAL, "اجاره", 900)

    _, total, amount = await ReportService(session).search(book.id, user.id, "اجاره")
    assert total == 1
    assert amount == Decimal("500")


# --------------------------------------------------------------- reminders
async def test_a_quiet_day_produces_no_digest(session):
    user, book = await setup(session)
    assert await ReminderService(session).daily_digest(user.id) is None


async def test_a_day_with_activity_produces_a_digest(session):
    user, book = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 250_000
    )

    reminder = await ReminderService(session).daily_digest(user.id)
    assert reminder is not None
    assert reminder.kind == "digest"
    assert "مغازه" in reminder.text
    assert "250,000" in reminder.text


async def test_the_digest_covers_every_book_the_person_has(session):
    user, book = await setup(session)
    second = await BookService(session).create_book(user.id, "فریلنس", BookType.BUSINESS)
    ledger = LedgerService(session)

    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100)
    await ledger.record(second.id, user.id, Flow.INCOME, Scope.WORK, "پروژه", 200)

    reminder = await ReminderService(session).daily_digest(user.id)
    assert "مغازه" in reminder.text and "فریلنس" in reminder.text


async def test_an_installment_due_soon_is_flagged(session):
    user, book = await setup(session)
    await LoanService(session).create(
        book.id, user.id, "وام مسکن", 2_000_000, 24, date.today()
    )

    reminder = await ReminderService(session).due_installments(user.id, days_ahead=1)
    assert reminder is not None
    assert "وام مسکن" in reminder.text


async def test_a_distant_installment_is_not_flagged(session):
    user, book = await setup(session)
    await LoanService(session).create(
        book.id, user.id, "وام", 1_000, 6, date.today() + timedelta(days=90)
    )

    assert await ReminderService(session).due_installments(user.id, days_ahead=3) is None


async def test_a_finished_loan_stops_reminding(session):
    user, book = await setup(session)
    service = LoanService(session)
    loan = await service.create(book.id, user.id, "وام", 1_000, 1, date.today())
    await service.record_payment(book.id, user.id, loan.id)

    assert await ReminderService(session).due_installments(user.id, days_ahead=30) is None


async def test_a_debt_falling_due_is_flagged(session):
    user, book = await setup(session)
    await DebtService(session).create(
        book.id, user.id, "علی", Direction.OWED_TO_ME, 500_000,
        due_on=date.today() + timedelta(days=1),
    )

    reminder = await ReminderService(session).due_debts(user.id, days_ahead=3)
    assert reminder is not None and "علی" in reminder.text


async def test_a_settled_debt_stops_reminding(session):
    user, book = await setup(session)
    service = DebtService(session)
    debt = await service.create(
        book.id, user.id, "علی", Direction.OWED_TO_ME, 500,
        due_on=date.today(),
    )
    await service.settle(book.id, user.id, debt.id)

    assert await ReminderService(session).due_debts(user.id) is None


async def test_reminders_only_reach_people_linked_to_that_messenger(session):
    identity = IdentityService(session)
    on_telegram = await identity.create_user("تلگرامی")
    issued = await identity.start_link_from_web(on_telegram.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "tg-1")

    await identity.create_user("بی‌پیام‌رسان")

    recipients = await ReminderService(session).recipients(Provider.TELEGRAM)
    assert [uid for uid, _ in recipients] == [on_telegram.id]
    assert await ReminderService(session).recipients(Provider.BALE) == []


async def test_one_persons_reminders_never_mention_another_persons_book(session):
    owner, book = await setup(session)
    await LedgerService(session).record(
        book.id, owner.id, Flow.INCOME, Scope.WORK, "خصوصی", 999
    )
    stranger = await IdentityService(session).create_user("غریبه")

    assert await ReminderService(session).for_user(stranger.id) == []
