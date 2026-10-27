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


def tapped(reply, prefix):
    """Press the button the screen actually offered: its data carries the draft's nonce."""
    data = next(b.data for row in reply.buttons for b in row if b.data.startswith(prefix))
    return press(data)


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

    reply = await convo.handle(tapped(reply, "qk:flow:income"))
    assert "ثبت شد" in reply.text

    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].category == "فروش"
    assert rows[0].converted_amount == Decimal("250000")


async def test_with_several_books_the_line_asks_which_one(session):
    user, (shop, side), convo = await setup(session, ("مغازه", "فریلنس"))

    reply = await convo.handle(says("فروش ۲۵۰ک"))
    assert "کدام دفتر" in reply.text

    reply = await convo.handle(tapped(reply, f"qk:book:{side.id}"))
    await convo.handle(tapped(reply, "qk:flow:income"))

    assert len(await LedgerService(session).transactions(side.id, user.id)) == 1
    assert await LedgerService(session).transactions(shop.id, user.id) == []


async def test_the_note_and_date_from_the_line_are_kept(session):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(says("1405/05/31 اجاره ۱٫۲م بابت مرداد"))
    await convo.handle(tapped(reply, "qk:flow:expense"))

    row = (await LedgerService(session).transactions(book.id, user.id))[0]
    assert row.description == "بابت مرداد"
    assert row.occurred_on == jalali.from_parts(1405, 5, 31)
    assert row.flow is Flow.EXPENSE


async def test_an_unreadable_line_offers_help_rather_than_guessing(session):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(says("یه چیزی بنویس"))
    assert "مبلغی در این پیام ندیدم" in reply.text
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


# ------------------------------------------------- what the quick line misreads
# Each of these recorded the wrong thing, or refused with the wrong reason,
# while the quick line was the fastest way into the bot and the least watched.
async def test_a_space_before_the_unit_does_not_divide_the_amount_by_a_thousand():
    """«فروش 250 ک» is 250,000, the same as «فروش 250ک».

    `parse_amount` accepts «ک» glued to the digits, so the glued form was right
    and the spaced form read 250 with «ک» filed as the note: a silent
    thousand-fold undercount on the one path nothing asks to confirm. The
    invariant is that a space cannot change what a line means, so every unit
    `parse_amount` understands is checked both ways.
    """
    from kasbbook.shared.parsing import _UNITS

    for unit, factor in _UNITS:
        glued = quick.read(f"فروش 250{unit}")
        spaced = quick.read(f"فروش 250 {unit}")
        assert isinstance(glued, quick.QuickEntry), unit
        assert isinstance(spaced, quick.QuickEntry), f"«250 {unit}» was not read"
        assert spaced.amount == glued.amount == 250 * factor, unit
        # The unit is the magnitude, never a note left over beside it.
        assert spaced.description is None, f"«{unit}» leaked into the note"


async def test_a_leading_date_is_never_taken_as_the_category():
    """«1404/12/28 250000» is a back-dated entry, not a category called 1404/12/28.

    The leading-date strip was gated on more than two tokens, so the shortest
    back-dated line a person can write — a date and an amount — recorded the
    date as the category name and created that category in the book.
    """
    got = quick.read("1404/12/28 250000", today=date(2026, 1, 1))

    assert isinstance(got, quick.Unclear), f"recorded instead: {got}"
    # The date was understood; what is missing is what the money was for.
    assert got.reason == "nocategory"


async def test_an_amount_with_no_category_asks_for_the_category():
    """«250000» alone said "I saw no amount in this message", which is false.

    The amount is the only thing present. The reason is that the category is
    missing, and `_UNCLEAR["nocategory"]` already says exactly that.
    """
    got = quick.read("250000")

    assert isinstance(got, quick.Unclear), f"read as: {got}"
    assert got.reason == "nocategory"
    assert got.numbers == ("250000",)


async def test_dot_grouped_thousands_are_asked_about_rather_than_refused():
    """«قبض برق 1.500.000» is the commonest Persian typing style for 1,500,000.

    `parse_amount` refuses two dots outright, so no number was found at all and
    the line came back as unreadable — the one refusal that teaches nothing.
    A single group («250.000») was already asked about; more than one was not.
    """
    got = quick.read("قبض برق 1.500.000")

    assert isinstance(got, quick.Unclear), f"read as: {got}"
    assert got.reason == "dots"
    assert got.numbers == ("1.500.000",)


async def test_the_dots_question_is_asked_about_the_figure_that_was_typed():
    """The question hardcoded «250 است یا 250,000؟» whatever the figure was.

    Asked about «1.500.000» it would have offered two readings of a number the
    person never typed. Note that the echoed figure contains "1.5" as a
    substring, so only the grouped reading and the absence of the hardcoded
    example actually prove anything here.
    """
    from kasbbook.bot import screens

    multi = screens.unclear_reason("dots", ("1.500.000",))
    assert "1,500,000" in multi          # the one sensible reading, offered back
    assert "250" not in multi            # not the hardcoded example

    # One dot is genuinely two-way, and both readings are named.
    single = screens.unclear_reason("dots", ("250.000",))
    assert "250,000" in single and "250 " in single


# ------------------------------------- the direction the book already decided
#
# «فروش 250ک» was the fastest way into this bot and still cost two interactions,
# because the line names a category and not a direction. But a `Category` is
# unique per (book, name) and carries its own `flow`, and
# `CategoryService._ensure` refuses a transaction whose flow disagrees with the
# one on file — so for a name the book has used before, «درآمد است یا هزینه؟»
# was never the person's question to answer: one answer recorded and the other
# was refused at the end of the flow.

def datas(reply):
    return [b.data for row in reply.buttons for b in row if b.data]


async def test_a_category_the_book_already_uses_records_without_asking(session):
    """One message, one transaction: the second «فروش» costs no tap at all."""
    user, (book,), convo = await setup(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 250000)

    reply = await convo.handle(says("فروش ۳۰۰ک"))

    rows = await ledger.transactions(book.id, user.id)
    assert len(rows) == 2, f"not recorded; the screen said: {reply.text}"
    assert rows[-1].flow is Flow.INCOME
    assert rows[-1].converted_amount == Decimal("300000")
    assert "ثبت شد" in reply.text
    # Every recording is still a balanced pair of journal lines.
    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit == Decimal("550000")


async def test_the_card_says_the_direction_came_from_the_category(session):
    """The one fact the bot supplied rather than being told is named on the card."""
    user, (book,), convo = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 1000000
    )

    reply = await convo.handle(says("اجاره 1.2م"))

    assert "اجاره" in reply.text and "هزینه" in reply.text
    assert "پرسیده نشد" in reply.text
    assert any(d.startswith("qk:undo:") for d in datas(reply)), "no way back"


async def test_a_category_the_book_has_never_used_is_still_asked_about(session):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(says("مشاوره 100ک"))

    assert "درآمد است یا هزینه" in reply.text
    assert await LedgerService(session).transactions(book.id, user.id) == []


async def test_a_category_with_no_direction_on_file_is_asked_about(session):
    """A null `flow` is an unclassified legacy category, never an inferred one."""
    from kasbbook.modules.ledger.models import Category

    user, (book,), convo = await setup(session)
    session.add(Category(book_id=book.id, name="متفرقه", flow=None))
    await session.flush()

    reply = await convo.handle(says("متفرقه 50000"))

    assert "درآمد است یا هزینه" in reply.text
    assert await LedgerService(session).transactions(book.id, user.id) == []


async def test_a_near_match_is_not_a_match(session):
    """«فروشگاه» is not «فروش»: a fuzzy match would record the wrong direction."""
    user, (book,), convo = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 250000
    )

    reply = await convo.handle(says("فروشگاه 50000"))

    assert "درآمد است یا هزینه" in reply.text
    assert len(await LedgerService(session).transactions(book.id, user.id)) == 1


async def test_two_books_still_ask_which_book_before_anything_is_recorded(session):
    """Which book is a real question; the direction is not. Only the first survives."""
    user, (shop, side), convo = await setup(session, ("مغازه", "فریلنس"))
    ledger = LedgerService(session)
    for book in (shop, side):
        await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100)

    reply = await convo.handle(says("فروش 250ک"))
    assert "کدام دفتر" in reply.text

    reply = await convo.handle(tapped(reply, f"qk:book:{side.id}"))

    assert "ثبت شد" in reply.text
    rows = await ledger.transactions(side.id, user.id)
    assert [row.converted_amount for row in rows] == [Decimal("100"), Decimal("250000")]
    assert len(await ledger.transactions(shop.id, user.id)) == 1


async def test_an_inferred_direction_is_undone_in_one_tap(session):
    """The direction was not chosen by the person, so one tap takes it back.

    A flip button would be a button that can only fail: `_ensure` refuses a
    transaction whose flow disagrees with the stored category, which is the
    same rule that makes the guess safe. So the card offers the only correction
    the data allows — remove the entry, and ask the question that was skipped.
    """
    user, (book,), convo = await setup(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 1000000)

    saved = await convo.handle(says("اجاره 1.2م"))
    assert len(await ledger.transactions(book.id, user.id)) == 2

    back = await convo.handle(tapped(saved, "qk:undo:"))

    assert len(await ledger.transactions(book.id, user.id)) == 1
    assert "درآمد است یا هزینه" in back.text
    assert "1,200,000" in back.text, "the line is kept, not retyped"
    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit == Decimal("1000000")


async def test_the_same_undo_button_cannot_be_tapped_twice(session):
    user, (book,), convo = await setup(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100)

    saved = await convo.handle(says("فروش 250ک"))
    undo = next(b.data for row in saved.buttons for b in row if b.data.startswith("qk:undo:"))
    await convo.handle(press(undo))
    again = await convo.handle(press(undo))

    assert "قدیمی" in again.text
    assert len(await ledger.transactions(book.id, user.id)) == 1


async def test_someone_who_may_not_delete_is_not_offered_the_undo(session):
    """A member may record and may not delete; a button that can only raise is not offered."""
    from kasbbook.modules.books.models import Role

    user, (book,), convo = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100
    )

    identity = IdentityService(session)
    mate = await identity.create_user("رضا")
    issued = await identity.start_link_from_web(mate.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555002")
    await BookService(session).add_member(user.id, book.id, mate.id, Role.MEMBER)

    reply = await convo.handle(says("فروش 250ک", external_id="555002"))

    assert "ثبت شد" in reply.text
    assert not any(d.startswith("qk:undo:") for d in datas(reply))


# ------------------------------------- the figures a refusal refused to choose
#
# `Unclear` was holding the candidate figures and dropping them on the way to
# the screen, so every refusal cost a retyped line. They are carried through
# now: one button per reading, and the fix is a tap.

async def test_the_figures_a_refusal_saw_come_back_as_buttons(session):
    user, (book,), convo = await setup(session)
    ledger = LedgerService(session)

    asked = await convo.handle(says("خرید 2 نان 20000"))
    assert "نفهمیدم کدام مبلغ است" in asked.text
    labels = [b.text for row in asked.buttons for b in row if b.data.startswith("qk:amt:")]
    assert labels == ["2", "20,000"]
    assert await ledger.transactions(book.id, user.id) == []

    chosen = await convo.handle(tapped(asked, "qk:amt:1"))
    assert "20,000" in chosen.text
    saved = await convo.handle(tapped(chosen, "qk:flow:expense"))

    row = (await ledger.transactions(book.id, user.id))[0]
    assert row.converted_amount == Decimal("20000")
    assert row.category == "خرید"
    assert row.description == "2 نان"
    assert "ثبت شد" in saved.text
    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit == Decimal("20000")


async def test_the_dots_question_is_answered_with_a_tap(session):
    """«1.500.000» has one sensible reading, and now a button that says it."""
    user, (book,), convo = await setup(session)

    asked = await convo.handle(says("قبض برق 1.500.000"))
    labels = [b.text for row in asked.buttons for b in row if b.data.startswith("qk:amt:")]
    assert labels == ["1,500,000"]

    chosen = await convo.handle(tapped(asked, "qk:amt:0"))
    await convo.handle(tapped(chosen, "qk:flow:expense"))

    ledger = LedgerService(session)
    row = (await ledger.transactions(book.id, user.id))[0]
    assert row.category == "قبض برق"
    assert row.converted_amount == Decimal("1500000")
    assert await ledger.trial_balance(book.id) == (Decimal("1500000"), Decimal("1500000"))


async def test_one_dot_offers_both_readings(session):
    user, (book,), convo = await setup(session)

    asked = await convo.handle(says("فروش 250.000"))
    labels = [b.text for row in asked.buttons for b in row if b.data.startswith("qk:amt:")]

    assert labels == ["250", "250,000"]


async def test_a_refusal_with_nothing_to_choose_between_keeps_its_question(session):
    """Rials, zero and a missing category are not a choice among readings."""
    user, (book,), convo = await setup(session)

    for line in ("فروش 250000 ریال", "فروش 0", "30 هزار و 500"):
        reply = await convo.handle(says(line))
        assert not any(d.startswith("qk:amt:") for d in datas(reply)), line
        assert await LedgerService(session).transactions(book.id, user.id) == []


async def test_a_new_line_is_never_swallowed_by_a_waiting_refusal(session):
    """The draft a refusal keeps is read by buttons only; typing starts over."""
    user, (book,), convo = await setup(session)

    await convo.handle(says("خرید 2 نان 20000"))
    reply = await convo.handle(says("فروش 250000"))

    assert "فروش" in reply.text and "250,000" in reply.text
    assert any(d.startswith("qk:flow:") for d in datas(reply))


async def test_a_candidate_button_from_an_older_line_says_it_is_old(session):
    user, (book,), convo = await setup(session)

    stale_screen = await convo.handle(says("خرید 2 نان 20000"))
    old = next(b.data for row in stale_screen.buttons for b in row
               if b.data.startswith("qk:amt:"))
    await convo.handle(says("فروش 300 نان 40000"))

    reply = await convo.handle(press(old))

    assert "قدیمی" in reply.text
    assert await LedgerService(session).transactions(book.id, user.id) == []


# --------------------------------------------- two more lines the parser lost
async def test_a_unit_glued_to_the_word_toman_is_still_an_amount():
    """«فروش 250هزارتومان» found no number at all and was called unreadable.

    `parse_amount` reads a magnitude only at the very end of the token, so the
    word for the currency hid it. The book counts in toman, so the word adds
    nothing and is dropped.
    """
    for line in ("فروش 250هزارتومان", "فروش 250000تومان", "فروش 250کتومن"):
        got = quick.read(line)
        assert isinstance(got, quick.QuickEntry), f"{line}: {got}"
        assert got.category == "فروش"
        assert got.description is None, f"«تومان» leaked into the note of {line}"
    assert quick.read("فروش 250هزارتومان").amount == Decimal("250000")
    assert quick.read("فروش 250000تومان").amount == Decimal("250000")


async def test_a_negative_amount_is_named_rather_than_called_missing(session):
    """«فروش -250000» was answered with "I saw no amount", about its only amount."""
    got = quick.read("فروش -250000")
    assert isinstance(got, quick.Unclear), f"read as: {got}"
    assert got.reason == "negative"

    user, (book,), convo = await setup(session)
    reply = await convo.handle(says("فروش -250000"))

    assert "منفی" in reply.text
    assert "هزینه" in reply.text          # which is how money leaves a book
    assert "مثال" in reply.text or "مثلاً" in reply.text
    assert await LedgerService(session).transactions(book.id, user.id) == []


async def test_the_other_direction_is_still_refused_after_an_undo(session):
    """Why the card has no flip button: flipping is the one thing the data forbids.

    `_ensure` refuses a transaction whose flow disagrees with the stored
    category, so a button that re-recorded «اجاره» as income could only ever
    fail. The undo asks the question instead, and the refusal that answers it
    names the real problem — which is what the old flow did at this point too,
    after charging a tap for the privilege.
    """
    user, (book,), convo = await setup(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 1000000)

    saved = await convo.handle(says("اجاره 1.2م"))
    asked = await convo.handle(tapped(saved, "qk:undo:"))
    refused = await convo.handle(tapped(asked, "qk:flow:income"))

    assert "دسته" in refused.text
    assert len(await ledger.transactions(book.id, user.id)) == 1
    assert await ledger.trial_balance(book.id) == (Decimal("1000000"), Decimal("1000000"))


async def test_the_direction_is_read_from_the_book_the_line_landed_in(session):
    """Two books, the same category name, filed opposite ways: each book answers for itself."""
    user, (shop, home), convo = await setup(session, ("مغازه", "خانه"))
    ledger = LedgerService(session)
    await ledger.record(shop.id, user.id, Flow.INCOME, Scope.WORK, "اجاره", 100)
    await ledger.record(home.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 100)

    reply = await convo.handle(says("اجاره 500ک"))
    await convo.handle(tapped(reply, f"qk:book:{home.id}"))
    reply = await convo.handle(says("اجاره 500ک"))
    await convo.handle(tapped(reply, f"qk:book:{shop.id}"))

    assert [row.flow for row in await ledger.transactions(home.id, user.id)] == \
        [Flow.EXPENSE, Flow.EXPENSE]
    assert [row.flow for row in await ledger.transactions(shop.id, user.id)] == \
        [Flow.INCOME, Flow.INCOME]


async def test_a_viewer_is_refused_before_anything_is_inferred(session):
    """Reading the book's categories needs the same permission reading it does.

    A viewer may see a book and not record in it. The refusal now arrives on
    the line instead of one tap later, and it is the ledger's own: nothing is
    inferred for someone who may not record in the first place.
    """
    from kasbbook.modules.books.models import Role

    user, (book,), convo = await setup(session)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100
    )

    identity = IdentityService(session)
    guest = await identity.create_user("مهمان")
    issued = await identity.start_link_from_web(guest.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555003")
    await BookService(session).add_member(user.id, book.id, guest.id, Role.VIEWER)

    reply = await convo.handle(says("فروش 250ک", external_id="555003"))

    assert "اجازه" in reply.text
    assert len(await LedgerService(session).transactions(book.id, user.id)) == 1
