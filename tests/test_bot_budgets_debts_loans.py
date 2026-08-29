"""Budgets, debts and loans as a person meets them: through the bot.

The services are tested elsewhere. What is pinned here is the path a user
actually walks — every screen reachable, every flow completing, and the
domain rules still holding when they are driven from a keyboard.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.budgets.service import BudgetService
from kasbbook.modules.debts.service import DebtService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.loans.service import LoanService
from kasbbook.shared import jalali

pytestmark = pytest.mark.asyncio
TG = Provider.TELEGRAM


def press(data, external_id="555001"):
    return IncomingEvent(
        kind=EventKind.CALLBACK,
        identity=ChannelIdentity(TG, external_id, "emad", "عماد"),
        chat_id=external_id, message_id="10", callback_data=data, callback_id="cb",
    )


def says(text, external_id="555001"):
    return IncomingEvent(
        kind=EventKind.MESSAGE,
        identity=ChannelIdentity(TG, external_id, "emad", "عماد"),
        chat_id=external_id, message_id="10", text=text,
    )


async def setup(session):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    return user, book, Conversation(session, MemoryStateStore(), TG)


def labels(reply):
    return [b.text for row in reply.buttons for b in row]


# ------------------------------------------------------------- book menu
async def test_opening_a_book_shows_its_workspace(session):
    user, book, convo = await setup(session)

    reply = await convo.handle(press(f"book:open:{book.id}"))
    text = " ".join(labels(reply))

    assert "بودجه" in text
    assert "طلب" in text
    assert "وام" in text
    assert "گزارش" in text


# ------------------------------------------------------------------ budgets
async def test_a_category_budget_can_be_set_from_the_bot(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"bg:add:{book.id}"))
    await convo.handle(press("bg:kind:category"))
    await convo.handle(says("اجاره"))
    reply = await convo.handle(says("۱م"))

    budgets = await BudgetService(session).list_budgets(book.id, user.id)
    assert len(budgets) == 1
    assert budgets[0].target == "اجاره"
    assert budgets[0].amount == Decimal("1000000")
    assert "اجاره" in reply.text


async def test_a_whole_direction_can_be_capped_without_naming_a_category(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"bg:add:{book.id}"))
    reply = await convo.handle(press("bg:kind:expense"))
    assert "هزینه" in reply.text

    await convo.handle(says("500000"))
    budgets = await BudgetService(session).list_budgets(book.id, user.id)
    assert budgets[0].target == Flow.EXPENSE.value


async def test_the_budget_screen_shows_how_much_is_used(session):
    user, book, convo = await setup(session)
    await BudgetService(session).set_budget(
        book.id, user.id, __import__(
            "kasbbook.modules.budgets.models", fromlist=["BudgetKind"]
        ).BudgetKind.CATEGORY, "اجاره", 1_000,
    )
    await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 400
    )

    reply = await convo.handle(press(f"bg:list:{book.id}"))
    assert "40%" in reply.text


async def test_an_unreadable_budget_amount_asks_again(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"bg:add:{book.id}"))
    await convo.handle(press("bg:kind:category"))
    await convo.handle(says("اجاره"))
    reply = await convo.handle(says("یه عددی"))

    assert "سقف" in reply.text
    assert await BudgetService(session).list_budgets(book.id, user.id) == []


async def test_a_budget_can_be_removed_from_its_list(session):
    user, book, convo = await setup(session)
    from kasbbook.modules.budgets.models import BudgetKind

    budget = await BudgetService(session).set_budget(
        book.id, user.id, BudgetKind.CATEGORY, "اجاره", 1_000
    )
    await convo.handle(press(f"bg:del:{budget.id}"))

    assert await BudgetService(session).list_budgets(book.id, user.id) == []


# -------------------------------------------------------------------- debts
async def test_a_debt_can_be_recorded_end_to_end(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"dt:add:{book.id}"))
    await convo.handle(says("علی"))
    await convo.handle(press("dt:dir:owed_to_me"))
    await convo.handle(says("۵۰۰ک"))
    reply = await convo.handle(press("dt:nodue"))

    debts = await DebtService(session).list_debts(book.id, user.id)
    assert len(debts) == 1
    assert debts[0].person == "علی"
    assert debts[0].amount == Decimal("500000")
    assert debts[0].due_on is None
    assert "علی" in reply.text


async def test_a_due_date_is_kept_when_one_is_given(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"dt:add:{book.id}"))
    await convo.handle(says("رضا"))
    await convo.handle(press("dt:dir:i_owe"))
    await convo.handle(says("100000"))
    await convo.handle(says("1405/06/15"))

    debt = (await DebtService(session).list_debts(book.id, user.id))[0]
    assert debt.due_on == jalali.from_parts(1405, 6, 15)


async def test_recording_a_debt_leaves_the_ledger_alone(session):
    """The rule that matters most, checked from the user's side too."""
    user, book, convo = await setup(session)

    await convo.handle(press(f"dt:add:{book.id}"))
    await convo.handle(says("علی"))
    await convo.handle(press("dt:dir:owed_to_me"))
    await convo.handle(says("500000"))
    await convo.handle(press("dt:nodue"))

    assert await LedgerService(session).transactions(book.id, user.id) == []
    debit, credit = await LedgerService(session).trial_balance(book.id)
    assert debit == credit == Decimal("0")


async def test_settling_from_the_list_clears_the_totals(session):
    user, book, convo = await setup(session)
    from kasbbook.modules.debts.models import Direction

    debt = await DebtService(session).create(
        book.id, user.id, "علی", Direction.OWED_TO_ME, 500_000
    )
    reply = await convo.handle(press(f"dt:settle:{debt.id}"))

    totals = await DebtService(session).totals(book.id, user.id)
    assert totals.owed_to_me == Decimal("0")
    assert "0" in reply.text


# -------------------------------------------------------------------- loans
async def test_a_loan_can_be_created_from_the_bot(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"ln:add:{book.id}"))
    await convo.handle(says("وام مسکن"))
    await convo.handle(says("۲م"))
    await convo.handle(says("24"))
    reply = await convo.handle(says("1404/01/15"))

    loans = await LoanService(session).list_loans(book.id, user.id)
    assert len(loans) == 1
    assert loans[0].title == "وام مسکن"
    assert loans[0].installment_amount == Decimal("2000000")
    assert loans[0].installment_count == 24
    assert loans[0].starts_on == jalali.from_parts(1404, 1, 15)
    assert "وام مسکن" in reply.text


async def test_today_is_offered_as_a_start_date(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"ln:add:{book.id}"))
    await convo.handle(says("وام"))
    await convo.handle(says("1000"))
    await convo.handle(says("6"))
    await convo.handle(press("ln:today"))

    loan = (await LoanService(session).list_loans(book.id, user.id))[0]
    assert loan.starts_on == date.today()


async def test_a_non_numeric_installment_count_asks_again(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"ln:add:{book.id}"))
    await convo.handle(says("وام"))
    await convo.handle(says("1000"))
    reply = await convo.handle(says("چند تا"))

    assert "تعداد" in reply.text
    assert await LoanService(session).list_loans(book.id, user.id) == []


async def test_paying_an_installment_from_the_bot_moves_the_progress(session):
    user, book, convo = await setup(session)
    loan = await LoanService(session).create(
        book.id, user.id, "وام", 1_000, 6, date(2025, 4, 10)
    )

    reply = await convo.handle(press(f"ln:pay:{loan.id}"))
    # What matters is that the screen now reflects one paid and five left.
    assert "5 قسط" in reply.text
    assert "17%" in reply.text

    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].flow is Flow.EXPENSE

    debit, credit = await LedgerService(session).trial_balance(book.id)
    assert debit == credit


async def test_a_finished_loan_stops_offering_a_payment_button(session):
    user, book, convo = await setup(session)
    service = LoanService(session)
    loan = await service.create(book.id, user.id, "وام", 1_000, 2, date(2025, 4, 10))

    await convo.handle(press(f"ln:pay:{loan.id}"))
    reply = await convo.handle(press(f"ln:pay:{loan.id}"))

    assert not any("ثبت پرداخت" in label for label in labels(reply))
    assert "تمام شد" in reply.text


async def test_deleting_a_loan_asks_first_and_then_keeps_the_payments(session):
    user, book, convo = await setup(session)
    service = LoanService(session)
    loan = await service.create(book.id, user.id, "وام", 1_000, 6, date(2025, 4, 10))
    await convo.handle(press(f"ln:pay:{loan.id}"))

    asked = await convo.handle(press(f"ln:del:{loan.id}"))
    assert "مطمئنی" in asked.text
    assert len(await service.list_loans(book.id, user.id)) == 1

    await convo.handle(press(f"ln:delok:{loan.id}"))
    assert await service.list_loans(book.id, user.id) == []
    # The expense stayed on the books.
    assert len(await LedgerService(session).transactions(book.id, user.id)) == 1


# ------------------------------------------------------------- isolation
async def test_one_account_cannot_reach_another_accounts_loan(session):
    owner, book, _ = await setup(session)
    loan = await LoanService(session).create(
        book.id, owner.id, "خصوصی", 1_000, 6, date(2025, 4, 10)
    )

    identity = IdentityService(session)
    stranger = await identity.create_user("غریبه")
    issued = await identity.start_link_from_web(stranger.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "999")

    convo = Conversation(session, MemoryStateStore(), TG)
    reply = await convo.handle(press(f"ln:open:{loan.id}", external_id="999"))

    assert "پیدا نشد" in reply.text
    assert "خصوصی" not in reply.text
