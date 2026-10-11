"""The Persian UX fixes, driven the way a person drives them.

Every test goes through Conversation.handle() with an IncomingEvent, the same
seam a Telegram update crosses. What is pinned: a quick line is never recorded
on a guess, a refusal says why and keeps the step, a button never leads
somewhere other than what it says, and the copy follows one vocabulary.
"""

from __future__ import annotations

import pathlib
import re
from datetime import date
from decimal import Decimal

import pytest

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot import quick, screens
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.budgets.models import BudgetKind
from kasbbook.modules.budgets.service import BudgetService
from kasbbook.modules.debts.models import Direction
from kasbbook.modules.debts.service import DebtService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.loans.service import LoanService
from kasbbook.modules.recurring.models import Period
from kasbbook.modules.recurring.service import RecurringService
from kasbbook.shared import jalali
from kasbbook.shared.errors import BalanceError, NotFound, PermissionDenied, ValidationError

pytestmark = pytest.mark.asyncio

TG = Provider.TELEGRAM
BOT = pathlib.Path(__file__).resolve().parents[1] / "src/kasbbook/bot"


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
    """Press the button the screen actually offered (its data carries the draft's nonce)."""
    data = next(b.data for row in reply.buttons for b in row if b.data.startswith(prefix))
    return press(data)


def labels(reply):
    return [b.text for row in reply.buttons for b in row]


def datas(reply):
    return [b.data for row in reply.buttons for b in row if b.data]


async def setup(session, names=("مغازه",), kind=BookType.BUSINESS):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")
    books = [await BookService(session).create_book(user.id, name, kind) for name in names]
    return user, books, Conversation(session, MemoryStateStore(), TG)


async def recorded(session, user, book):
    return await LedgerService(session).transactions(book.id, user.id)


def has_no_latin_words(text):
    """User-facing sentences are Persian; digits and a few product names are fine."""
    return not re.search(r"[A-Za-z]{3,}", text.replace("KasbBook", ""))


# ===================================================================== B3
async def test_a_quantity_before_the_price_is_not_taken_as_the_amount(session):
    user, (book,), convo = await setup(session)

    confirm = await convo.handle(says("خرید ۲ عدد نان ۲۰۰۰۰"))
    # What was understood is on screen before anything is recorded.
    assert "20,000" in confirm.text
    assert "2 عدد نان" in confirm.text
    assert "دفتر مغازه" in confirm.text
    assert await recorded(session, user, book) == []

    await convo.handle(tapped(confirm, "qk:flow:expense"))
    row = (await recorded(session, user, book))[0]
    assert row.converted_amount == Decimal("20000")
    assert row.category == "خرید"
    assert row.description == "2 عدد نان"


@pytest.mark.parametrize("line, expected", [
    ("قهوه ۳۰ هزار و ۵۰۰", "30500"),
    ("قهوه 30 هزار و 500", "30500"),
    ("خرید لوازم ۲ میلیون و ۳۰۰ هزار", "2300000"),
    ("فروش 2 میلیون و 300 هزار و 50 هزار", None),   # parts must shrink: asked, not summed
    ("فروش 250 هزار تومان", "250000"),
    ("فروش ۱,۲۰۰,۰۰۰", "1200000"),
])
async def test_compound_persian_amounts_are_read_exactly(session, line, expected):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(says(line))
    if expected is None:
        assert not any(d.startswith("qk:flow") for d in datas(reply))
        return
    await convo.handle(tapped(reply, "qk:flow:expense"))
    assert (await recorded(session, user, book))[0].converted_amount == Decimal(expected)


@pytest.mark.parametrize("line", [
    "خرید ۲ نان ۲۰۰۰۰",          # a count or the price? two bare numbers
    "فروش 1,5",                   # 1.5 or 15
    "فروش 250.000",               # 250 or 250,000
    "مبل ۲ میلیون و ۵۰۰",         # 2,000,500 or 2,500,000
    "فروش 250000 ریال",           # the book counts in toman
    "فروش 0",
    "30 هزار و 500",              # an amount with nothing to call it
])
async def test_a_line_that_could_mean_two_sums_is_asked_not_recorded(session, line):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(says(line))

    assert reply.text.lstrip(screens.RLM).startswith("❓")
    assert not any(d.startswith("qk:") for d in datas(reply)), "no draft to confirm"
    assert await recorded(session, user, book) == []
    # And there is an example the person can copy.
    assert "مثلاً" in reply.text or "مثال" in reply.text


async def test_the_confirm_screen_shows_date_book_and_note(session):
    user, (book,), convo = await setup(session)

    confirm = await convo.handle(says("1405/05/31 اجاره ۱٫۲م بابت مرداد"))

    assert "1,200,000" in confirm.text and "تومان" in confirm.text
    assert "اجاره" in confirm.text
    assert "1405/05/31" in confirm.text
    assert "دفتر مغازه" in confirm.text
    assert "بابت مرداد" in confirm.text


async def test_without_a_typed_date_the_confirm_says_today_in_the_persons_day(session, monkeypatch):
    user, (book,), convo = await setup(session)
    monkeypatch.setattr(jalali, "today_in", lambda *a, **k: date(2026, 3, 19))

    confirm = await convo.handle(says("فروش 250ک"))

    assert "امروز (1404/12/28)" in confirm.text


async def test_with_two_books_the_book_question_repeats_what_was_understood(session):
    user, (shop, home), convo = await setup(session, ("مغازه", "خرج خانه"))

    ask = await convo.handle(says("خرید ۲ عدد نان ۲۰۰۰۰"))
    assert "20,000" in ask.text and "کدام دفتر" in ask.text

    confirm = await convo.handle(tapped(ask, f"qk:book:{home.id}"))
    assert "دفتر خرج خانه" in confirm.text

    saved = await convo.handle(tapped(confirm, "qk:flow:expense"))
    assert "20,000 تومان" in saved.text and "خرج خانه" in saved.text
    assert len(await recorded(session, user, home)) == 1
    assert await recorded(session, user, shop) == []


async def test_a_crafted_book_button_does_not_reveal_another_accounts_book(session):
    owner, (secret,), _ = await setup(session, ("خصوصی",))
    identity = IdentityService(session)
    stranger = await identity.create_user("غریبه")
    issued = await identity.start_link_from_web(stranger.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "999")
    mine = await BookService(session).create_book(stranger.id, "من", BookType.BUSINESS)
    mine2 = await BookService(session).create_book(stranger.id, "من دو", BookType.BUSINESS)
    convo = Conversation(session, MemoryStateStore(), TG)

    ask = await convo.handle(says("فروش 100ک", "999"))
    assert mine and mine2
    nonce = next(d for d in datas(ask) if d.startswith("qk:flow") or d.startswith("qk:book")).rsplit(":", 1)[1]
    reply = await convo.handle(press(f"qk:book:{secret.id}:{nonce}", "999"))

    assert "خصوصی" not in reply.text


async def test_the_quick_reader_itself():
    clear = quick.read("خرید ۲ عدد نان ۲۰۰۰۰")
    assert (clear.category, clear.amount, clear.description) == ("خرید", Decimal("20000"), "2 عدد نان")

    named_by_the_words_after = quick.read("۲ کیلو سیب ۵۰۰۰۰")
    assert (named_by_the_words_after.category, named_by_the_words_after.amount) == ("سیب", Decimal("50000"))

    # A large first number is trusted even when the note carries another.
    assert quick.read("فروش 250000 فاکتور 123").amount == Decimal("250000")
    assert quick.read("فروش 250000 فاکتور 123").description == "فاکتور 123"

    assert isinstance(quick.read("فروش 0"), quick.Unclear)
    assert quick.parse("خرید ۲ نان ۲۰۰۰۰") is None   # parse() only returns clear lines
    assert quick.read_amount("۳۰ هزار و ۵۰۰") == Decimal("30500")
    assert quick.read_amount("250000 تومان") == Decimal("250000")
    assert quick.read_amount("250000 بابت اجاره") is None


# ===================================================================== B4
async def test_a_zero_amount_is_refused_at_the_step_with_cause_and_fix(session):
    user, (book,), convo = await setup(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:on:today"))
    await convo.handle(press("tx:type:we"))
    await convo.handle(says("اجاره"))

    for bad in ("0", "۰", "abc", "-500"):
        reply = await convo.handle(says(bad))
        assert reply.text.lstrip(screens.RLM).startswith("⚠️"), bad
        assert has_no_latin_words(reply.text.replace("abc", "")), reply.text
        # Still on the amount step, with the example to copy from.
        assert "مبلغ را بنویس" in reply.text and "250ک" in reply.text

    zero = await convo.handle(says("0"))
    assert "بیشتر از صفر" in zero.text

    # Nothing was swallowed: the very next line is the amount, and it works.
    after = await convo.handle(says("۱۲۰ک"))
    assert "توضیحات" in after.text
    saved = await convo.handle(press("tx:skip"))
    assert "ثبت شد" in saved.text
    assert (await recorded(session, user, book))[0].converted_amount == Decimal("120000")


async def test_every_amount_prompt_refuses_zero_and_stays_put(session):
    user, (book,), convo = await setup(session)

    # budget
    await convo.handle(press(f"bg:add:{book.id}"))
    await convo.handle(press("bg:kind:expense"))
    reply = await convo.handle(says("0"))
    assert "بیشتر از صفر" in reply.text and "هزینه‌ها" in reply.text
    assert await BudgetService(session).list_budgets(book.id, user.id) == []

    # debt
    await convo.handle(press(f"dt:add:{book.id}"))
    await convo.handle(says("علی"))
    await convo.handle(press("dt:dir:owed_to_me"))
    reply = await convo.handle(says("0"))
    assert "بیشتر از صفر" in reply.text and "مثلاً" in reply.text

    # recurring
    await convo.handle(press(f"rr:add:{book.id}"))
    await convo.handle(press("rr:flow:expense"))
    await convo.handle(says("اجاره"))
    reply = await convo.handle(says("0"))
    assert "بیشتر از صفر" in reply.text


async def test_editing_an_amount_to_zero_keeps_the_edit_open(session):
    user, (book,), convo = await setup(session)
    tx = await LedgerService(session).record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 500)

    first = await convo.handle(press(f"td:ea:{tx.id}"))
    assert "مبلغ فعلی: 500" in first.text
    # The foreign-currency sentence is only true of foreign money.
    assert "نرخ تبدیل" not in first.text

    refused = await convo.handle(says("0"))
    assert "بیشتر از صفر" in refused.text and "مبلغ فعلی: 500" in refused.text

    done = await convo.handle(says("750"))
    assert done.text.lstrip(screens.RLM).startswith("✅ ویرایش شد")
    assert "750" in done.text


# ============================================================ B5 / B6 books
async def test_blank_and_overlong_book_names_are_refused_with_the_reason(session):
    user, _, convo = await setup(session, ())
    await convo.handle(press("book:new"))
    await convo.handle(press("book:type:business"))

    blank = await convo.handle(says("   "))
    assert "خالی" in blank.text and "مثال" in blank.text

    long = await convo.handle(says("م" * 300))
    assert "حداکثر 40 حرف" in long.text

    assert await BookService(session).books_for_user(user.id) == []

    ok = await convo.handle(says("مغازه"))
    assert "دفتر «مغازه» ساخته شد" in ok.text


async def test_the_first_book_leads_to_the_first_transaction(session):
    user, _, convo = await setup(session, ())
    await convo.handle(press("book:new"))
    await convo.handle(press("book:type:business"))

    made = await convo.handle(says("مغازه"))

    assert "اولین تراکنش" in made.text
    assert any(d.startswith("tx:book:") for d in datas(made))


async def test_two_books_with_one_name_get_two_different_buttons(session):
    user, (first, second), convo = await setup(session, ("مغازه", "مغازه"))

    listing = await convo.handle(press("book:list"))
    book_buttons = [b.text for row in listing.buttons for b in row if b.data.startswith("book:open")]
    assert len(set(book_buttons)) == 2

    pick = await convo.handle(press("tx:one"))
    assert len({b.text for row in pick.buttons for b in row if b.data.startswith("tx:book")}) == 2


# ===================================================================== B7
async def test_no_list_offers_a_label_that_goes_home(session):
    user, (book,), convo = await setup(session)
    await BudgetService(session).set_budget(book.id, user.id, BudgetKind.CATEGORY, "اجاره", 1000)
    await DebtService(session).create(
        book.id, user.id, "رضایی", Direction.OWED_TO_ME, Decimal(500), None, None)
    await RecurringService(session).create(book.id, user.id, Flow.EXPENSE, "اجاره", 500, Period.MONTHLY, date.today())
    ledger = LedgerService(session)
    for number in range(12):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, f"خرج {number}", 10 + number)

    screens_seen = [
        await convo.handle(press(f"bg:list:{book.id}")),
        await convo.handle(press(f"dt:list:{book.id}")),
        await convo.handle(press(f"rr:list:{book.id}")),
        await convo.handle(press(f"td:list:{book.id}")),
    ]
    await convo.handle(press(f"sr:new:{book.id}"))
    screens_seen.append(await convo.handle(says("خرج")))

    for reply in screens_seen:
        assert not any(d.startswith("noop") for d in datas(reply)), reply.text

    # The page counter redraws its own page instead of leaving.
    paged = screens_seen[3]
    counter = next(b for row in paged.buttons for b in row if "/" in b.text)
    assert counter.data.startswith("td:page:")

    # An old message may still carry a noop; it is told so, not silently sent home.
    old = await convo.handle(press("noop:x"))
    assert "قدیمی" in old.text


async def test_a_recurring_rule_is_listed_with_its_frequency(session):
    """PERIOD_LABELS was defined twice; the later one erased the frequency."""
    user, (book,), convo = await setup(session)
    await RecurringService(session).create(book.id, user.id, Flow.EXPENSE, "اجاره", 500, Period.MONTHLY, date.today())

    reply = await convo.handle(press(f"rr:list:{book.id}"))

    assert "ماهانه" in reply.text


# ===================================================================== B8
async def test_the_saved_notice_is_a_line_of_its_own(session):
    user, (book,), convo = await setup(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:on:today"))
    await convo.handle(press("tx:type:we"))
    await convo.handle(says("اجاره"))
    await convo.handle(says("500"))
    saved = await convo.handle(press("tx:skip"))

    lines = saved.text.split("\n")
    assert lines[0].endswith("ثبت شد")
    assert lines[1] == ""                      # a blank line, not the card's first line
    assert "جزئیات" not in lines[0]
    assert saved.text.index("ثبت شد") < saved.text.index("جزئیات")
    assert "➕ ثبت بعدی" in labels(saved)


async def test_a_notice_never_welds_onto_the_screen_below_it():
    text, _ = screens.with_notice("✅ ثبت شد", screens.welcome("عماد"))
    assert "ثبت شد\n\n" in text


# ===================================================================== B9
async def test_the_debt_prompt_and_the_word_it_asks_for_agree(session):
    user, (book,), convo = await setup(session)
    await convo.handle(press(f"dt:add:{book.id}"))
    await convo.handle(says("رضایی"))
    await convo.handle(press("dt:dir:owed_to_me"))
    prompt = await convo.handle(says("۵۰۰ک"))

    # The prompt points at the button, with a date example; no promise it can't keep.
    assert "بدون سررسید" in prompt.text and "1405/08/15" in prompt.text
    assert "ندارد" not in prompt.text

    # And a person who types the word anyway is understood, not looped.
    done = await convo.handle(says("ندارد"))
    assert "رضایی" in done.text
    debts = await DebtService(session).list_debts(book.id, user.id)
    assert len(debts) == 1 and debts[0].due_on is None

    # A date that is not a date names itself and keeps the step.
    await convo.handle(press(f"dt:add:{book.id}"))
    await convo.handle(says("احمدی"))
    await convo.handle(press("dt:dir:i_owe"))
    await convo.handle(says("1م"))
    refused = await convo.handle(says("هفته بعد"))
    assert "«هفته بعد»" in refused.text and "بدون سررسید" in refused.text


# ==================================================================== B10
async def test_a_flow_budget_never_shows_the_raw_enum(session):
    user, (book,), convo = await setup(session)
    await convo.handle(press(f"bg:add:{book.id}"))
    first = await convo.handle(press("bg:kind:expense"))
    again = await convo.handle(says("یه عددی"))

    for reply in (first, again):
        assert "expense" not in reply.text and "income" not in reply.text
        assert "هزینه‌ها" in reply.text
        assert "مثال" in reply.text


@pytest.mark.parametrize("error, expected", [
    (BalanceError("an entry of zero moves nothing"), "بیشتر از صفر"),
    (NotFound("book 1234"), "پیدا نشد"),
    (PermissionDenied("viewer may not edit_transaction"), "اجازه"),
    (ValidationError("the new owner must already be an active member"), "دوباره"),
    (ValidationError("نام باید پر باشد"), "نام باید پر باشد"),   # Persian passes through
])
async def test_domain_errors_reach_people_in_persian(error, expected):
    message = screens.user_message(error)
    assert expected in message
    assert has_no_latin_words(message)


async def test_a_refusal_from_a_service_is_shown_in_persian(session):
    owner, (secret,), _ = await setup(session, ("خصوصی",))
    identity = IdentityService(session)
    stranger = await identity.create_user("غریبه")
    issued = await identity.start_link_from_web(stranger.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "999")
    convo = Conversation(session, MemoryStateStore(), TG)

    reply = await convo.handle(press(f"rep:book:{secret.id}", "999"))

    assert reply.text.lstrip(screens.RLM).startswith("⚠️")
    assert has_no_latin_words(reply.text)
    assert "خصوصی" not in reply.text


# ==================================================================== B11
async def test_today_buttons_use_the_persons_day_not_the_servers(session, monkeypatch):
    user, (book,), convo = await setup(session)
    elsewhere = date(2031, 1, 5)
    monkeypatch.setattr(jalali, "today_in", lambda *a, **k: elsewhere)

    await convo.handle(press(f"rr:add:{book.id}"))
    await convo.handle(press("rr:flow:expense"))
    await convo.handle(says("اجاره"))
    await convo.handle(says("5م"))
    await convo.handle(press("rr:period:monthly"))
    await convo.handle(press("rr:today"))
    rules = await RecurringService(session).list_rules(book.id, user.id)
    assert rules[0].next_run_on == elsewhere

    await convo.handle(press(f"ln:add:{book.id}"))
    await convo.handle(says("وام"))
    await convo.handle(says("1000"))
    await convo.handle(says("6"))
    await convo.handle(press("ln:today"))
    assert (await LoanService(session).list_loans(book.id, user.id))[0].starts_on == elsewhere

    # Words like «فردا» are relative to that same day.
    await convo.handle(press(f"dt:add:{book.id}"))
    await convo.handle(says("علی"))
    await convo.handle(press("dt:dir:owed_to_me"))
    await convo.handle(says("1م"))
    await convo.handle(says("فردا"))
    debts = await DebtService(session).list_debts(book.id, user.id)
    assert debts[0].due_on == date(2031, 1, 6)


# ==================================================================== B12
async def test_a_search_result_can_be_opened_and_edited(session):
    user, (book,), convo = await setup(session)
    tx = await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 500, description="مشتری علی")

    await convo.handle(press(f"sr:new:{book.id}"))
    short = await convo.handle(says("ع"))
    assert "حداقل دو حرف" in short.text

    results = await convo.handle(says("علی"))
    assert f"td:open:{tx.id}" in datas(results)

    detail = await convo.handle(press(f"td:open:{tx.id}"))
    assert "جزئیات" in detail.text
    assert any(d.startswith("td:ea:") for d in datas(detail))


# ======================================================== destructive taps
async def test_nothing_is_deleted_by_the_first_tap(session):
    user, (book,), convo = await setup(session)
    debt = await DebtService(session).create(
        book.id, user.id, "رضایی", Direction.OWED_TO_ME, Decimal(500), None, None)

    ask = await convo.handle(press(f"dt:del:{debt.id}"))
    assert "مطمئنی" in ask.text
    assert len(await DebtService(session).list_debts(book.id, user.id)) == 1

    done = await convo.handle(tapped(ask, "dt:delok:"))
    assert "حذف شد" in done.text
    assert await DebtService(session).list_debts(book.id, user.id) == []


async def test_settling_says_what_it_did(session):
    user, (book,), convo = await setup(session)
    debt = await DebtService(session).create(
        book.id, user.id, "رضایی", Direction.OWED_TO_ME, Decimal(500), None, None)

    reply = await convo.handle(press(f"dt:settle:{debt.id}"))

    assert "«رضایی» تسویه شد" in reply.text
    assert "چیزی ثبت نشده" not in reply.text


# ============================================================== copy rules
def _bot_sources():
    return {path.name: path.read_text(encoding="utf-8") for path in (BOT / "screens.py", BOT / "conversation.py")}


async def test_the_vocabulary_is_one_word_per_concept():
    forbidden = {
        "دسته‌بندی": "the word is «دسته»",
        "ثبت تکی": "it is «ثبت تراکنش»",
        "پاک کردن": "it is «حذف»",
        "حساب من": "it is «حساب کاربری»",
        "لغو آخرین": "it is «برگرداندن»",
        "به من بدهکار است": "it is «طلب من»",
    }
    for name, source in _bot_sources().items():
        for word, why in forbidden.items():
            assert word not in source, f"{name}: «{word}» — {why}"


async def test_persian_is_typed_with_a_half_space_and_the_right_letters():
    for name, source in _bot_sources().items():
        assert not re.search(r"(?<![؀-ۿ])ن?می [؀-ۿ]", source), f"{name}: می without ZWNJ"
        assert "ي" not in source and "ك" not in source, f"{name}: Arabic ye/kaf"


async def test_user_facing_digits_are_written_one_way():
    persian = re.compile("[۰-۹٠-٩]")
    for name, source in _bot_sources().items():
        for number, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("#", '"""', "«")) or not ('"' in line):
                continue
            assert not persian.search(line), f"{name}:{number}: {line.strip()[:80]}"


@pytest.mark.parametrize("screen", [
    lambda: screens.ask_book_name(BookType.BUSINESS),
    lambda: screens.ask_category(Flow.EXPENSE),
    lambda: screens.ask_amount("اجاره"),
    lambda: screens.ask_date("nav:cancel"),
    lambda: screens.ask_description(),
    lambda: screens.ask_search(),
    lambda: screens.budget_ask_target(),
    lambda: screens.budget_ask_amount("هزینه‌ها"),
    lambda: screens.debt_ask_person(),
    lambda: screens.debt_ask_amount(),
    lambda: screens.debt_ask_due(),
    lambda: screens.loan_ask_title(),
    lambda: screens.loan_ask_amount("وام"),
    lambda: screens.loan_ask_count(),
    lambda: screens.loan_ask_start(),
    lambda: screens.recurring_ask_category(),
    lambda: screens.recurring_ask_amount("اجاره"),
    lambda: screens.recurring_ask_start(),
    lambda: screens.ask_hour(),
    lambda: screens.ask_days(),
])
async def test_every_text_prompt_carries_an_example(screen):
    text, buttons = screen()
    assert "مثال" in text or "مثلاً" in text
    # And a way out.
    assert any("انصراف" in b.text for row in buttons for b in row)


async def test_a_refusal_on_a_prompt_leads_with_the_cause():
    text, _ = screens.ask_amount("اجاره", problem="مبلغ باید بیشتر از صفر باشد.")
    assert text.lstrip(screens.RLM).startswith("⚠️ مبلغ باید بیشتر از صفر باشد.")
    assert "مثلاً" in text


async def test_an_old_button_says_it_is_old_instead_of_going_home_silently(session):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(press("tx:skip"))

    assert "قدیمی" in reply.text


async def test_amounts_are_named_in_toman_not_in_a_currency_code(session):
    user, (book,), convo = await setup(session)
    await LedgerService(session).record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 500000)

    report = await convo.handle(press(f"rp:{book.id}:w:0"))

    assert "500,000 تومان" in report.text and "IRT" not in report.text


async def test_an_empty_period_says_it_is_empty(session):
    user, (book,), convo = await setup(session)

    report = await convo.handle(press(f"rp:{book.id}:w:1"))

    assert "تراکنشی ثبت نشده" in report.text
    back = next(b.data for row in report.buttons for b in row if "بازگشت" in b.text)
    assert back == f"rep:book:{book.id}"          # up one level, not the main menu
