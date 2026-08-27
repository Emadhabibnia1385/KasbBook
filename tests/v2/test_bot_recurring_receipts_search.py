"""Transactions, receipts, search, recurring rules and reminders, from the bot."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from kasbbook.adapters.base import (
    Attachment,
    ChannelIdentity,
    EventKind,
    IncomingEvent,
)
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.recurring.service import RecurringService

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


def sends_photo(file_id="PHOTO-1", external_id="555001"):
    return IncomingEvent(
        kind=EventKind.ATTACHMENT,
        identity=ChannelIdentity(TG, external_id, "emad", "عماد"),
        chat_id=external_id, message_id="11",
        attachment=Attachment(kind="photo", file_id=file_id),
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


# ----------------------------------------------------------- book workspace
async def test_the_workspace_reaches_every_feature(session):
    user, book, convo = await setup(session)
    text = " ".join(labels(await convo.handle(press(f"book:open:{book.id}"))))

    for expected in ("تراکنش", "جست‌وجو", "گزارش", "بودجه", "طلب", "وام", "تکرارشونده"):
        assert expected in text, expected


# ------------------------------------------------------- transaction detail
async def test_transactions_can_be_listed_and_opened(session):
    user, book, convo = await setup(session)
    tx = await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500_000
    )

    listing = await convo.handle(press(f"td:list:{book.id}"))
    assert "اجاره" in listing.text

    detail = await convo.handle(press(f"td:open:{tx.id}"))
    assert "جزئیات" in detail.text
    assert "500,000" in detail.text
    assert "ندارد" in detail.text  # no receipt yet


async def test_a_long_list_pages(session):
    user, book, convo = await setup(session)
    ledger = LedgerService(session)
    for index in range(20):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, f"ق{index}", 100)

    first = await convo.handle(press(f"td:list:{book.id}"))
    assert any("بعدی" in label for label in labels(first))

    second = await convo.handle(press(f"td:page:{book.id}:1"))
    assert first.text != second.text


async def test_deleting_a_transaction_asks_first_and_keeps_the_book_balanced(session):
    user, book, convo = await setup(session)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اشتباه", 500)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 900)

    asked = await convo.handle(press(f"td:del:{tx.id}"))
    assert "مطمئنی" in asked.text
    assert len(await ledger.transactions(book.id, user.id)) == 2

    await convo.handle(press(f"td:delok:{tx.id}"))
    rows = await ledger.transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].category == "فروش"

    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit == Decimal("900")


# ---------------------------------------------------------------- receipts
async def test_a_photo_becomes_the_receipt_for_a_transaction(session):
    user, book, convo = await setup(session)
    tx = await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500
    )

    await convo.handle(press(f"td:rcp:{tx.id}"))
    reply = await convo.handle(sends_photo("PHOTO-XYZ"))

    stored = await LedgerService(session).get_transaction(book.id, user.id, tx.id)
    assert stored.receipt_file_id == "PHOTO-XYZ"
    assert stored.receipt_provider == "telegram"
    assert stored.receipt_kind == "photo"
    # The screen names what it is rather than only that it exists.
    assert "عکس" in reply.text


async def test_a_photo_sent_out_of_the_blue_is_not_a_receipt(session):
    """Only a transaction that asked for one should swallow a photo."""
    user, book, convo = await setup(session)
    tx = await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500
    )

    await convo.handle(sends_photo("STRAY"))

    stored = await LedgerService(session).get_transaction(book.id, user.id, tx.id)
    assert stored.receipt_file_id is None


async def test_viewing_a_receipt_forwards_the_id_rather_than_the_bytes(session):
    user, book, convo = await setup(session)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)
    await ledger.attach_receipt(book.id, user.id, tx.id, "PHOTO-1", "telegram")

    reply = await convo.handle(press(f"td:rcpv:{tx.id}"))
    assert reply.forward_file_id == "PHOTO-1"
    assert reply.document is None  # nothing was downloaded or re-uploaded


async def test_a_receipt_can_be_removed(session):
    user, book, convo = await setup(session)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)
    await ledger.attach_receipt(book.id, user.id, tx.id, "PHOTO-1", "telegram")

    reply = await convo.handle(press(f"td:rcpd:{tx.id}"))
    stored = await ledger.get_transaction(book.id, user.id, tx.id)
    assert stored.receipt_file_id is None
    assert "ندارد" in reply.text


# ------------------------------------------------------------------ search
async def test_searching_from_the_bot_finds_and_totals(session):
    user, book, convo = await setup(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 700)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "قبض", 100)

    await convo.handle(press(f"sr:new:{book.id}"))
    reply = await convo.handle(says("اجاره"))

    assert "2 نتیجه" in reply.text
    assert "1,200" in reply.text
    assert "قبض" not in reply.text


async def test_a_search_with_no_hits_says_so(session):
    user, book, convo = await setup(session)
    await convo.handle(press(f"sr:new:{book.id}"))
    reply = await convo.handle(says("چیزی‌که‌نیست"))
    assert "پیدا نشد" in reply.text


async def test_a_one_letter_search_asks_again(session):
    user, book, convo = await setup(session)
    await convo.handle(press(f"sr:new:{book.id}"))
    reply = await convo.handle(says("ا"))
    assert "جست‌وجو" in reply.text


# --------------------------------------------------------------- recurring
async def test_a_recurring_rule_can_be_defined_from_the_bot(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"rr:add:{book.id}"))
    await convo.handle(press("rr:flow:expense"))
    await convo.handle(says("اجاره"))
    await convo.handle(says("۵م"))
    await convo.handle(press("rr:period:monthly"))
    reply = await convo.handle(press("rr:today"))

    rules = await RecurringService(session).list_rules(book.id, user.id)
    assert len(rules) == 1
    assert rules[0].category == "اجاره"
    assert rules[0].amount == Decimal("5000000")
    assert rules[0].flow is Flow.EXPENSE
    assert rules[0].next_run_on == date.today()
    assert "اجاره" in reply.text


async def test_a_rule_can_be_paused_and_deleted_from_its_list(session):
    user, book, convo = await setup(session)
    from kasbbook.modules.recurring.models import Period

    rule = await RecurringService(session).create(
        book.id, user.id, Flow.EXPENSE, "اجاره", 500, Period.MONTHLY, date.today()
    )

    await convo.handle(press(f"rr:tog:{rule.id}"))
    rules = await RecurringService(session).list_rules(book.id, user.id)
    assert rules[0].is_active is False

    await convo.handle(press(f"rr:del:{rule.id}"))
    assert await RecurringService(session).list_rules(book.id, user.id) == []


async def test_an_unreadable_recurring_amount_asks_again(session):
    user, book, convo = await setup(session)

    await convo.handle(press(f"rr:add:{book.id}"))
    await convo.handle(press("rr:flow:expense"))
    await convo.handle(says("اجاره"))
    reply = await convo.handle(says("یه چیزی"))

    assert "مبلغ" in reply.text
    assert await RecurringService(session).list_rules(book.id, user.id) == []


# --------------------------------------------------------------- reminders
async def test_reminder_settings_are_reachable_and_default_on(session):
    user, book, convo = await setup(session)

    reply = await convo.handle(press("rm:panel"))
    assert "یادآور" in reply.text
    assert any("روشن" in label for label in labels(reply))


async def test_the_digest_can_be_switched_off(session):
    user, book, convo = await setup(session)

    reply = await convo.handle(press("rm:toggle"))
    assert user.digest_enabled is False
    assert any("خاموش" in label for label in labels(reply))


async def test_the_digest_hour_can_be_changed(session):
    user, book, convo = await setup(session)

    await convo.handle(press("rm:hour"))
    reply = await convo.handle(says("۹"))

    assert user.digest_hour == 9
    assert any("9" in label for label in labels(reply))


async def test_an_impossible_hour_is_refused(session):
    user, book, convo = await setup(session)

    await convo.handle(press("rm:hour"))
    await convo.handle(says("99"))

    assert user.digest_hour == 21  # unchanged


async def test_the_warning_window_can_be_changed(session):
    user, book, convo = await setup(session)

    await convo.handle(press("rm:days"))
    await convo.handle(says("7"))

    assert user.reminder_days == 7


# --------------------------------------------------------------- isolation
async def test_one_account_cannot_open_another_accounts_transaction(session):
    owner, book, _ = await setup(session)
    tx = await LedgerService(session).record(
        book.id, owner.id, Flow.EXPENSE, Scope.WORK, "خصوصی", 500
    )

    identity = IdentityService(session)
    stranger = await identity.create_user("غریبه")
    issued = await identity.start_link_from_web(stranger.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "999")

    convo = Conversation(session, MemoryStateStore(), TG)
    reply = await convo.handle(press(f"td:open:{tx.id}", external_id="999"))

    assert "پیدا نشد" in reply.text
    assert "خصوصی" not in reply.text


# ------------------------------------------------- what a receipt actually is
#
# A provider's file id is opaque. Storing it alone meant a PDF invoice and a
# photograph of a till roll were indistinguishable: the screen could only say
# "دارد", and sending one back had to try sendPhoto and wear the rejection
# before reaching sendDocument.

def sends_document(file_id="DOC-1", name="invoice-1405-06.pdf",
                   mime="application/pdf", external_id="555001"):
    return IncomingEvent(
        kind=EventKind.ATTACHMENT,
        identity=ChannelIdentity(TG, external_id, "emad", "عماد"),
        chat_id=external_id, message_id="11",
        attachment=Attachment(kind="document", file_id=file_id,
                              file_name=name, mime_type=mime),
    )


async def test_a_pdf_invoice_keeps_its_name_and_type(session):
    user, book, convo = await setup(session)
    tx = await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "خرید", 500
    )

    await convo.handle(press(f"td:rcp:{tx.id}"))
    reply = await convo.handle(sends_document())

    stored = await LedgerService(session).get_transaction(book.id, user.id, tx.id)
    assert stored.receipt_file_id == "DOC-1"
    assert stored.receipt_kind == "document"
    assert stored.receipt_file_name == "invoice-1405-06.pdf"
    assert stored.receipt_mime_type == "application/pdf"

    # And the screen names it rather than saying only that one exists.
    assert "invoice-1405-06.pdf" in reply.text


async def test_a_photo_has_no_name_and_the_screen_does_not_invent_one(session):
    user, book, convo = await setup(session)
    tx = await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500
    )

    await convo.handle(press(f"td:rcp:{tx.id}"))
    reply = await convo.handle(sends_photo("PHOTO-9"))

    assert "عکس" in reply.text
    assert "—" not in reply.text.split("رسید:")[1]


async def test_removing_a_receipt_takes_its_name_with_it(session):
    """A name left behind describes a file that is not there any more."""
    user, book, convo = await setup(session)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "خرید", 500)

    await convo.handle(press(f"td:rcp:{tx.id}"))
    await convo.handle(sends_document())
    reply = await convo.handle(press(f"td:rcpd:{tx.id}"))

    stored = await ledger.get_transaction(book.id, user.id, tx.id)
    assert stored.receipt_file_id is None
    assert stored.receipt_kind is None
    assert stored.receipt_file_name is None
    assert stored.receipt_mime_type is None
    assert "ندارد" in reply.text
    assert "invoice" not in reply.text


async def test_viewing_a_receipt_hands_the_adapter_its_kind(session):
    """Without this the recorded kind is never used where it would save a call."""
    user, book, convo = await setup(session)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "خرید", 500)
    await ledger.attach_receipt(book.id, user.id, tx.id, "DOC-2", "telegram",
                                kind="document", file_name="f.pdf")

    reply = await convo.handle(press(f"td:rcpv:{tx.id}"))
    assert reply.forward_file_id == "DOC-2"
    assert reply.forward_file_kind == "document"
    assert reply.document is None      # still nothing downloaded or re-uploaded


async def test_a_receipt_attached_before_kinds_existed_still_works(session):
    """Every row already in production has these three columns empty."""
    user, book, convo = await setup(session)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "خرید", 500)
    await ledger.attach_receipt(book.id, user.id, tx.id, "OLD-1", "telegram")

    reply = await convo.handle(press(f"td:rcpv:{tx.id}"))
    assert reply.forward_file_id == "OLD-1"
    assert reply.forward_file_kind is None

    detail = await convo.handle(press(f"td:open:{tx.id}"))
    assert "دارد" in detail.text


async def test_one_account_cannot_attach_a_receipt_to_anothers_transaction(session):
    owner, book, _ = await setup(session)
    tx = await LedgerService(session).record(
        book.id, owner.id, Flow.EXPENSE, Scope.WORK, "خصوصی", 500
    )

    identity = IdentityService(session)
    stranger = await identity.create_user("غریبه")
    issued = await identity.start_link_from_web(stranger.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "999")

    other = Conversation(session, MemoryStateStore(), TG)
    await other.handle(press(f"td:rcp:{tx.id}", external_id="999"))
    await other.handle(sends_document(external_id="999"))

    stored = await LedgerService(session).get_transaction(book.id, owner.id, tx.id)
    assert stored.receipt_file_id is None
    assert stored.receipt_file_name is None
