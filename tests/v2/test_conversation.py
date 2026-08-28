"""The bot, driven end to end without a bot token.

Events go in the way an adapter would produce them; screens come out the way an
adapter would render them. What is proved here is the part that matters: a
transaction recorded from Telegram is the same transaction the account owns
everywhere else.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.parsing import parse_amount, parse_date

pytestmark = pytest.mark.asyncio

TG = Provider.TELEGRAM


def event(kind, external_id="555001", **kwargs) -> IncomingEvent:
    return IncomingEvent(
        kind=kind,
        identity=ChannelIdentity(
            provider=TG, external_id=external_id,
            username=kwargs.pop("username", "emad"),
            display_name=kwargs.pop("display_name", "عماد"),
        ),
        chat_id=external_id,
        message_id=kwargs.pop("message_id", "10"),
        **kwargs,
    )


def command(text_command, args=None, **kw):
    return event(EventKind.COMMAND, command=text_command, args=args, text=f"/{text_command}", **kw)


def press(data, **kw):
    return event(EventKind.CALLBACK, callback_data=data, callback_id="cb", **kw)


def says(text, **kw):
    return event(EventKind.MESSAGE, text=text, **kw)


async def conversation(session):
    return Conversation(session, MemoryStateStore(), TG)


async def linked_user(session, name="عماد", external_id="555001"):
    identity = IdentityService(session)
    user = await identity.create_user(name)
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, external_id)
    return user


# ------------------------------------------------------------- not linked
async def test_an_unknown_messenger_account_is_offered_a_code(session):
    convo = await conversation(session)
    reply = await convo.handle(command("start"))

    assert "وصل نیست" in reply.text
    labels = [b.text for row in reply.buttons for b in row]
    assert any("ساخت حساب" in label for label in labels)


async def test_a_deep_link_token_attaches_this_messenger_to_the_account(session):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, TG)

    convo = await conversation(session)
    reply = await convo.handle(command("start", args=issued.token))

    assert "عماد" in reply.text
    owner = await identity.user_for_identity(TG, "555001")
    assert owner is not None and owner.id == user.id


async def test_creating_an_account_from_the_bot_links_it_immediately(session):
    convo = await conversation(session)
    await convo.handle(command("start"))
    reply = await convo.handle(press("acc:create"))

    owner = await IdentityService(session).user_for_identity(TG, "555001")
    assert owner is not None

    # A brand-new account is reachable from this messenger and nowhere else,
    # and it says so rather than dropping the person into a generic welcome.
    assert "از دست بدهی" in reply.text
    assert any("ایمیل" in b.text for row in reply.buttons for b in row)


async def test_a_bad_link_token_does_not_crash_the_bot(session):
    convo = await conversation(session)
    reply = await convo.handle(command("start", args="NOTATOKEN"))
    assert "⚠️" in reply.text


# ---------------------------------------------------------------- welcome
async def test_a_linked_user_lands_on_the_main_menu(session):
    await linked_user(session)
    convo = await conversation(session)
    reply = await convo.handle(command("start"))

    labels = [b.text for row in reply.buttons for b in row]
    assert any("ثبت تراکنش" in label for label in labels)
    assert any("گزارش" in label for label in labels)


async def test_a_callback_asks_the_adapter_to_edit_in_place(session):
    await linked_user(session)
    convo = await conversation(session)

    reply = await convo.handle(press("nav:home"))
    assert reply.edit_message_id == "10"

    # A typed message has no screen to replace.
    reply = await convo.handle(says("سلام"))
    assert reply.edit_message_id is None


# ------------------------------------------------------------------ books
async def test_a_user_with_no_books_is_asked_to_make_one(session):
    await linked_user(session)
    convo = await conversation(session)

    reply = await convo.handle(press("book:list"))
    assert "دفتری نداری" in reply.text


async def test_a_book_can_be_created_from_the_bot(session):
    user = await linked_user(session)
    convo = await conversation(session)

    await convo.handle(press("book:new"))
    await convo.handle(press("book:type:business"))
    reply = await convo.handle(says("مغازه"))

    books = await BookService(session).books_for_user(user.id)
    assert [b.name for b in books] == ["مغازه"]
    assert books[0].type is BookType.BUSINESS
    assert "مغازه" in reply.text


# ----------------------------------------------------------- transactions
async def test_the_whole_recording_flow_saves_one_transaction(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    convo = await conversation(session)

    await convo.handle(press("tx:new"))
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:income"))
    await convo.handle(says("فروش"))
    reply = await convo.handle(says("۲۵۰ک"))

    assert "ثبت شد" in reply.text
    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].category == "فروش"
    assert rows[0].converted_amount == Decimal("250000")


async def test_an_unreadable_amount_asks_again_instead_of_guessing(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    convo = await conversation(session)

    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:expense"))
    await convo.handle(says("اجاره"))
    reply = await convo.handle(says("یه چیزی حدود زیاد"))

    assert "مبلغ" in reply.text
    assert await LedgerService(session).transactions(book.id, user.id) == []


async def test_the_scope_follows_the_book_so_money_cannot_mix(session):
    user = await linked_user(session)
    books = BookService(session)
    personal = await books.create_book(user.id, "شخصی", BookType.PERSONAL)
    team = await books.create_book(user.id, "تیم", BookType.TEAM)
    convo = await conversation(session)

    for book, expected in ((personal, "personal"), (team, "team")):
        await convo.handle(press(f"tx:book:{book.id}"))
        await convo.handle(press("tx:flow:income"))
        await convo.handle(says("پروژه"))
        await convo.handle(says("1000"))

        rows = await LedgerService(session).transactions(book.id, user.id)
        assert rows[0].scope.value == expected


async def test_cancel_drops_a_half_finished_flow(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    convo = await conversation(session)

    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:income"))
    await convo.handle(command("cancel"))

    # The next typed line is not mistaken for a category. It falls through to
    # quick entry, which refuses a line with no amount rather than guessing.
    reply = await convo.handle(says("فروش"))
    assert "متوجه نشدم" in reply.text
    assert await LedgerService(session).transactions(book.id, user.id) == []


# ---------------------------------------------------------------- reports
async def test_the_report_shows_what_was_recorded(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    convo = await conversation(session)

    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:income"))
    await convo.handle(says("فروش"))
    await convo.handle(says("500000"))

    menu = await convo.handle(press(f"rep:book:{book.id}"))
    assert "کدام بازه" in menu.text

    # This week, since the transaction was recorded today.
    reply = await convo.handle(press(f"rp:{book.id}:w:0"))
    assert "500,000" in reply.text


# ----------------------------------------------- one account, two messengers
async def test_a_transaction_from_telegram_belongs_to_the_shared_account(session):
    """The promise the whole rewrite exists for."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد")

    for provider, external in ((Provider.TELEGRAM, "tg-1"), (Provider.BALE, "bale-1")):
        issued = await identity.start_link_from_web(user.id, provider)
        await identity.complete_link_from_messenger(issued.token, provider, external)

    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)

    # Recorded from Telegram.
    telegram = Conversation(session, MemoryStateStore(), Provider.TELEGRAM)
    await telegram.handle(press(f"tx:book:{book.id}", external_id="tg-1"))
    await telegram.handle(press("tx:flow:income", external_id="tg-1"))
    await telegram.handle(says("فروش", external_id="tg-1"))
    await telegram.handle(says("300000", external_id="tg-1"))

    # Read from Bale, by the same person, without anything being copied across.
    bale = Conversation(session, MemoryStateStore(), Provider.BALE)
    reply = await bale.handle(press(f"rp:{book.id}:w:0", external_id="bale-1"))
    assert "300,000" in reply.text


async def test_a_stranger_cannot_open_someone_elses_book(session):
    owner = await linked_user(session, "مالک", "555001")
    book = await BookService(session).create_book(owner.id, "خصوصی", BookType.BUSINESS)
    await linked_user(session, "غریبه", "999")

    convo = await conversation(session)
    reply = await convo.handle(press(f"rp:{book.id}:w:0", external_id="999"))

    assert "⚠️" in reply.text
    assert "300,000" not in reply.text


# ---------------------------------------------------------------- parsing
async def test_amounts_are_read_the_way_people_write_them():
    for text, expected in (
        ("250000", "250000"),
        ("۲۵۰۰۰۰", "250000"),
        ("250,000", "250000"),
        ("۲۵۰ک", "250000"),
        ("250k", "250000"),
        ("1.2م", "1200000"),
        ("2 میلیون", "2000000"),
    ):
        assert parse_amount(text) == Decimal(expected), text

    for text in ("", "سلام", "12abc", "k"):
        assert parse_amount(text) is None, text


async def test_amounts_come_back_as_decimals_never_floats():
    value = parse_amount("0.1")
    assert isinstance(value, Decimal)
    assert value + parse_amount("0.2") == Decimal("0.3")


async def test_dates_accept_either_calendar():
    from datetime import date

    assert parse_date("2026-08-22") == date(2026, 8, 22)
    assert parse_date("1405/05/31") == date(2026, 8, 22)
    assert parse_date("1405-5-31") == date(2026, 8, 22)
    assert parse_date("امروز", today=date(2026, 8, 22)) == date(2026, 8, 22)
    assert parse_date("hello") is None


# ------------------------------------------------- callback namespace safety
async def test_no_two_features_share_a_callback_prefix():
    """
    A prefix collision is silent and expensive.

    `rc:` once meant both "report CSV" and "recurring"; the first branch won and
    every recurring button raised a UUID error. Nothing failed at import, and no
    existing test noticed. This walks the routing table instead.
    """
    import ast
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2] / "src/kasbbook/bot/conversation.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))

    routed: list = []
    for node in ast.walk(tree):
        # `if area == "xx"` and `if area in ("xx", "yy")`
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Name):
            continue
        if node.left.id != "area":
            continue

        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                routed.append(comparator.value)
            elif isinstance(comparator, (ast.Tuple, ast.List)):
                routed += [
                    element.value
                    for element in comparator.elts
                    if isinstance(element, ast.Constant)
                ]

    assert routed, "no callback routing found — has the dispatcher moved?"

    duplicates = {prefix for prefix in routed if routed.count(prefix) > 1}
    assert not duplicates, f"these prefixes are routed twice: {sorted(duplicates)}"


async def test_every_button_prefix_the_screens_emit_is_routed():
    """A button whose prefix nothing handles is a dead end the user can reach."""
    import ast
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2] / "src/kasbbook/bot"

    emitted = set()
    for line in (root / "screens.py").read_text(encoding="utf-8").splitlines():
        for match in re.finditer(r'data=f?"([a-z]+):', line):
            emitted.add(match.group(1))

    tree = ast.parse((root / "conversation.py").read_text(encoding="utf-8"))
    routed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) \
                and node.left.id == "area":
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant):
                    routed.add(comparator.value)
                elif isinstance(comparator, (ast.Tuple, ast.List)):
                    routed |= {
                        element.value for element in comparator.elts
                        if isinstance(element, ast.Constant)
                    }

    unrouted = emitted - routed
    assert not unrouted, f"screens emit prefixes nothing handles: {sorted(unrouted)}"


# ------------------------------------------------------- category suggestions
#
# A category is typed on every single entry, so the ones this book already uses
# are the highest-value buttons in the bot. They are offered by index, not by
# name: a callback payload is sixty-four bytes and a Persian category does not
# reliably fit — a button that overflows it fails silently.

async def test_the_first_transaction_has_nothing_to_suggest(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    convo = await conversation(session)

    await convo.handle(press(f"tx:book:{book.id}"))
    reply = await convo.handle(press("tx:flow:expense"))

    assert "دسته" in reply.text
    assert [b.text for row in reply.buttons for b in row] == ["↩️ انصراف"]


async def test_categories_already_used_are_offered_as_buttons(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    ledger = LedgerService(session)
    for category in ("اجاره", "قبض برق", "حقوق"):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, category, 100)

    convo = await conversation(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    reply = await convo.handle(press("tx:flow:expense"))

    labels = [b.text for row in reply.buttons for b in row]
    for category in ("اجاره", "قبض برق", "حقوق"):
        assert category in labels


async def test_income_categories_are_not_offered_for_an_expense(session):
    """Suggesting "فروش" as an expense would be worse than suggesting nothing."""
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    ledger = LedgerService(session)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 100)

    convo = await conversation(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    reply = await convo.handle(press("tx:flow:expense"))

    labels = [b.text for row in reply.buttons for b in row]
    assert "اجاره" in labels
    assert "فروش" not in labels


async def test_pressing_a_suggestion_skips_straight_to_the_amount(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 100
    )

    convo = await conversation(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:expense"))
    reply = await convo.handle(press("tx:cat:0"))

    assert "اجاره" in reply.text
    assert "مبلغ" in reply.text


async def test_a_suggested_category_records_the_transaction(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    ledger = LedgerService(session)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 100)

    convo = await conversation(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:expense"))
    await convo.handle(press("tx:cat:0"))
    await convo.handle(says("۲م"))

    rows = await ledger.transactions(book.id, user.id)
    assert len(rows) == 2
    assert rows[-1].category == "اجاره"
    assert rows[-1].converted_amount == Decimal("2000000")


async def test_typing_a_new_category_still_works(session):
    """The buttons are a shortcut, not a menu. Anything else is still accepted."""
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 100
    )

    convo = await conversation(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:expense"))
    await convo.handle(says("چیز تازه"))
    await convo.handle(says("۵۰۰ک"))

    rows = await LedgerService(session).transactions(book.id, user.id)
    assert rows[-1].category == "چیز تازه"


async def test_a_stale_suggestion_index_asks_again_rather_than_crashing(session):
    """The screen was drawn before; the list may have moved on since."""
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.EXPENSE, Scope.WORK, "اجاره", 100
    )

    convo = await conversation(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:expense"))
    reply = await convo.handle(press("tx:cat:99"))

    assert "دسته" in reply.text


async def test_only_the_most_recent_handful_are_offered(session):
    """Twenty buttons is not a shortcut, it is a wall."""
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    ledger = LedgerService(session)
    for index in range(12):
        await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, f"د{index}", 100)

    convo = await conversation(session)
    await convo.handle(press(f"tx:book:{book.id}"))
    reply = await convo.handle(press("tx:flow:expense"))

    suggestions = [
        b for row in reply.buttons for b in row if (b.data or "").startswith("tx:cat:")
    ]
    assert len(suggestions) == 6


async def test_another_books_categories_are_not_suggested(session):
    user = await linked_user(session)
    books = BookService(session)
    shop = await books.create_book(user.id, "مغازه", BookType.BUSINESS)
    home = await books.create_book(user.id, "خانه", BookType.PERSONAL)
    await LedgerService(session).record(
        shop.id, user.id, Flow.EXPENSE, Scope.WORK, "اجارهٔ مغازه", 100
    )

    convo = await conversation(session)
    await convo.handle(press(f"tx:book:{home.id}"))
    reply = await convo.handle(press("tx:flow:expense"))

    labels = [b.text for row in reply.buttons for b in row]
    assert "اجارهٔ مغازه" not in labels


# ================================================== the account panel
#
# An account made from a messenger has no email, no phone and no password, so
# it cannot sign in to the API, a colleague cannot find it, and losing the
# messenger loses the books. This is the way out of that, from the bot.

async def test_the_panel_says_plainly_when_an_account_has_no_way_back(session):
    identity = IdentityService(session)
    await identity.create_account_from_messenger(TG, "555001", display_name="عماد")
    convo = await conversation(session)

    reply = await convo.handle(press("acc:panel"))

    assert "عماد" in reply.text
    assert "ندارد" in reply.text
    assert "راه برگشت ندارد" in reply.text


async def test_an_email_can_be_added_from_the_bot(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(TG, "555001")
    convo = await conversation(session)

    await convo.handle(press("acc:email"))
    reply = await convo.handle(says("emad@example.com"))

    assert user.email == "emad@example.com"
    assert "emad@example.com" in reply.text
    # The warning is gone, and the next thing to do is offered instead.
    assert "راه برگشت ندارد" not in reply.text
    assert "رمز" in reply.text


async def test_a_bad_email_says_so_without_leaving_the_flow(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(TG, "555001")
    convo = await conversation(session)

    await convo.handle(press("acc:email"))
    reply = await convo.handle(says("@example.com"))

    assert user.email is None
    assert "⚠️" in reply.text


async def test_a_first_password_is_set_in_one_step(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(TG, "555001")
    await identity.set_contact(user.id, email="emad@example.com")
    convo = await conversation(session)

    # No current password exists, so it does not ask for one.
    asked = await convo.handle(press("acc:pw"))
    assert "فعلی" not in asked.text

    await convo.handle(says("a-good-password"))

    assert await identity.authenticate("emad@example.com", "a-good-password") is not None


async def test_changing_a_password_asks_for_the_current_one_first(session):
    identity = IdentityService(session)
    user = await identity.create_user("عماد", email="emad@example.com",
                                      password="the-old-password")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")
    convo = await conversation(session)

    asked = await convo.handle(press("acc:pw"))
    assert "فعلی" in asked.text

    await convo.handle(says("the-old-password"))
    await convo.handle(says("a-new-password"))

    assert await identity.authenticate("emad@example.com", "a-new-password") is not None
    assert await identity.authenticate("emad@example.com", "the-old-password") is None


async def test_a_wrong_current_password_changes_nothing(session):
    identity = IdentityService(session)
    user = await identity.create_user("عماد", email="emad@example.com",
                                      password="the-old-password")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")
    convo = await conversation(session)

    await convo.handle(press("acc:pw"))
    await convo.handle(says("not-the-old-password"))
    reply = await convo.handle(says("a-new-password"))

    assert "⚠️" in reply.text
    assert await identity.authenticate("emad@example.com", "the-old-password") is not None


async def test_changing_the_password_signs_every_other_session_out(session):
    """Somebody changing it because they fear a leak expects exactly that."""
    from kasbbook.modules.identity.auth import AuthService

    identity = IdentityService(session)
    user = await identity.create_user("عماد", email="emad@example.com",
                                      password="the-old-password")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")

    auth = AuthService(session, "a-signing-key-long-enough-for-a-test")
    await auth.issue_pair(user)
    await auth.issue_pair(user)
    assert len(await auth.sessions(user.id)) == 2

    convo = await conversation(session)
    await convo.handle(press("acc:pw"))
    await convo.handle(says("the-old-password"))
    await convo.handle(says("a-new-password"))

    assert await auth.sessions(user.id) == []


async def test_the_timezone_survives_the_slash_in_its_name(session):
    """The callback splitter treats ":" as a separator; "Asia/Tehran" has none,
    but "acc:tzset:Europe/Istanbul" still has to arrive whole."""
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(TG, "555001")
    convo = await conversation(session)

    reply = await convo.handle(press("acc:tzset:Europe/Istanbul"))

    assert user.timezone == "Europe/Istanbul"
    assert "Europe/Istanbul" in reply.text


async def test_the_display_name_can_be_changed(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(TG, "555001", display_name="عماد")
    convo = await conversation(session)

    await convo.handle(press("acc:name"))
    reply = await convo.handle(says("عماد حبیب‌نیا"))

    assert user.display_name == "عماد حبیب‌نیا"
    assert "عماد حبیب‌نیا" in reply.text


async def test_sessions_can_be_seen_and_ended_from_the_bot(session):
    from kasbbook.modules.identity.auth import AuthService

    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(TG, "555001")
    auth = AuthService(session, "a-signing-key-long-enough-for-a-test")
    await auth.issue_pair(user, user_agent="Firefox on Linux", ip_address="10.0.0.9")

    convo = await conversation(session)
    listed = await convo.handle(press("acc:sessions"))
    assert "Firefox on Linux" in listed.text
    assert "10.0.0.9" in listed.text

    await convo.handle(press("acc:signout"))
    assert await auth.sessions(user.id) == []


async def test_one_account_cannot_see_anothers_account_panel(session):
    identity = IdentityService(session)
    first = await identity.create_account_from_messenger(TG, "555001",
                                                         display_name="عماد")
    await identity.set_contact(first.id, email="emad@example.com")
    await identity.create_account_from_messenger(TG, "999", display_name="غریبه")

    convo = await conversation(session)
    reply = await convo.handle(press("acc:panel", external_id="999"))

    assert "غریبه" in reply.text
    assert "عماد" not in reply.text
    assert "emad@example.com" not in reply.text
