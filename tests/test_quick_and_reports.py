"""One-line entry, and reports on the Jalali calendar.

These are the two things people used most in the first generation, so they are
pinned here rather than left to be discovered broken.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot import quick
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.reports import service as reports
from kasbbook.modules.reports.service import ReportService
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


async def setup(session, books_named=("مغازه",)):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")

    service = BookService(session)
    made = [
        await service.create_book(user.id, name, BookType.BUSINESS)
        for name in books_named
    ]
    return user, made, Conversation(session, MemoryStateStore(), TG)


# ------------------------------------------------------------- quick parse
async def test_a_line_is_read_as_category_then_amount():
    entry = quick.parse("فروش 250000")
    assert entry.category == "فروش"
    assert entry.amount == Decimal("250000")
    assert entry.description is None


async def test_a_multi_word_category_survives():
    entry = quick.parse("خرید لوازم 40000")
    assert entry.category == "خرید لوازم"


async def test_whatever_follows_the_amount_is_a_note():
    entry = quick.parse("اجاره ۱٫۲م بابت مرداد")
    assert entry.category == "اجاره"
    assert entry.amount == Decimal("1200000")
    assert entry.description == "بابت مرداد"


async def test_a_leading_date_is_taken_off_the_front():
    entry = quick.parse("1405/05/31 خدمات ۵۰۰ک")
    assert entry.on == jalali.from_parts(1405, 5, 31)
    assert entry.category == "خدمات"
    assert entry.amount == Decimal("500000")


async def test_an_amount_first_line_takes_the_next_word_as_the_category():
    entry = quick.parse("250000 فروش")
    assert entry.category == "فروش"
    assert entry.amount == Decimal("250000")


async def test_a_two_token_amount_is_understood():
    entry = quick.parse("فروش 250 هزار")
    assert entry.amount == Decimal("250000")


async def test_a_line_that_is_not_a_transaction_is_refused():
    for text in ("", "سلام چطوری", "فروش", "12345", "/start", "چقدر شد؟"):
        assert quick.parse(text) is None, text


# -------------------------------------------------------------- quick flow
async def test_one_line_records_a_transaction_when_there_is_one_book(session):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(says("فروش 250000"))
    assert "درآمد است یا هزینه" in reply.text

    reply = await convo.handle(press("qk:flow:income"))
    assert "ثبت شد" in reply.text

    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].category == "فروش"
    assert rows[0].converted_amount == Decimal("250000")


async def test_with_several_books_the_line_asks_which_one(session):
    user, (shop, side), convo = await setup(session, ("مغازه", "فریلنس"))

    reply = await convo.handle(says("فروش ۲۵۰ک"))
    assert "کدام دفتر" in reply.text

    await convo.handle(press(f"qk:book:{side.id}"))
    await convo.handle(press("qk:flow:income"))

    assert len(await LedgerService(session).transactions(side.id, user.id)) == 1
    assert await LedgerService(session).transactions(shop.id, user.id) == []


async def test_the_note_and_date_from_the_line_are_kept(session):
    user, (book,), convo = await setup(session)

    await convo.handle(says("1405/05/31 اجاره ۱٫۲م بابت مرداد"))
    await convo.handle(press("qk:flow:expense"))

    row = (await LedgerService(session).transactions(book.id, user.id))[0]
    assert row.description == "بابت مرداد"
    assert row.occurred_on == jalali.from_parts(1405, 5, 31)
    assert row.flow is Flow.EXPENSE


async def test_an_unreadable_line_offers_help_rather_than_guessing(session):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(says("یه چیزی بنویس"))
    assert "متوجه نشدم" in reply.text
    assert await LedgerService(session).transactions(book.id, user.id) == []


# ----------------------------------------------------------- jalali periods
async def test_a_jalali_month_covers_the_right_gregorian_days():
    start, end = jalali.month_range(1404, 1)
    assert start == date(2025, 3, 21)
    assert end == date(2025, 4, 20)


async def test_esfand_rolls_into_the_next_year():
    _, end = jalali.month_range(1404, 12)
    assert end == jalali.from_parts(1405, 1, 1) - __import__("datetime").timedelta(days=1)


async def test_the_week_starts_on_saturday():
    start, end = jalali.week_range(date(2026, 8, 24))  # a Monday
    assert start.weekday() == 5
    assert (end - start).days == 6
    assert start <= date(2026, 8, 24) <= end


async def test_a_period_spec_round_trips():
    for spec in ("m:1405:05", "y:1404", "w:0", "w:1"):
        period = reports.parse_spec(spec)
        assert period is not None and period.spec.startswith(spec.split(":")[0])

    assert reports.parse_spec("nonsense") is None
    assert reports.parse_spec("m:notayear:05") is None


# ------------------------------------------------------------------ report
async def test_a_month_report_only_counts_that_month(session):
    user, (book,), convo = await setup(session)
    ledger = LedgerService(session)
    service = ReportService(session)

    inside = jalali.from_parts(1404, 5, 10)
    outside = jalali.from_parts(1404, 6, 10)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 500,
                        occurred_on=inside)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 900,
                        occurred_on=outside)

    summary = await service.summary(book.id, user.id, reports.month(1404, 5))
    assert summary.income == Decimal("500")
    assert summary.net == Decimal("500")


async def test_the_breakdown_ranks_categories_by_size(session):
    user, (book,), convo = await setup(session)
    ledger = LedgerService(session)

    for category, amount in (("اجاره", 900), ("قبض", 100), ("حقوق", 500)):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, category, amount)

    buckets = await ReportService(session).by_category(book.id, user.id)
    names = [name for name, _, _ in buckets[Flow.EXPENSE]]
    assert names == ["اجاره", "حقوق", "قبض"]


async def test_comparing_to_an_empty_previous_period_is_skipped(session):
    user, (book,), convo = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100
    )

    assert await ReportService(session).compare(
        book.id, user.id, reports.week(offset=0)
    ) is None


async def test_a_csv_export_carries_a_bom_and_both_calendars(session):
    user, (book,), convo = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 250000
    )

    payload = await ReportService(session).to_csv(book.id, user.id)
    assert payload.startswith("﻿".encode("utf-8"))

    text = payload.decode("utf-8-sig")
    assert "شناسه" in text
    assert "فروش" in text
    assert "/" in text.splitlines()[1]  # the Jalali column


async def test_the_csv_arrives_as_a_file_beside_the_screen(session):
    user, (book,), convo = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 250000
    )

    reply = await convo.handle(press(f"rc:{book.id}:w:0"))
    assert reply.document is not None
    assert reply.document.filename.endswith(".csv")
    # The screen is still shown; the file does not replace it.
    assert "درآمد" in reply.text


async def test_the_period_menu_offers_the_years_that_have_data(session):
    user, (book,), convo = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100,
        occurred_on=jalali.from_parts(1403, 2, 2),
    )

    reply = await convo.handle(press(f"rep:book:{book.id}"))
    labels = [b.text for row in reply.buttons for b in row]
    assert any("۱۴۰۳" in label or "1403" in label for label in labels)
