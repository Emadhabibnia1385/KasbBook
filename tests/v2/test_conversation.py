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

    assert "KasbBook" in reply.text
    owner = await IdentityService(session).user_for_identity(TG, "555001")
    assert owner is not None


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

    # The next typed line is not mistaken for a category.
    reply = await convo.handle(says("فروش"))
    assert "KasbBook" in reply.text
    assert await LedgerService(session).transactions(book.id, user.id) == []


# ---------------------------------------------------------------- reports
async def test_the_report_shows_what_was_recorded(session):
    user = await linked_user(session)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    ledger = LedgerService(session)
    convo = await conversation(session)

    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:income"))
    await convo.handle(says("فروش"))
    await convo.handle(says("500000"))

    reply = await convo.handle(press(f"rep:book:{book.id}"))
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
    reply = await bale.handle(press(f"rep:book:{book.id}", external_id="bale-1"))
    assert "300,000" in reply.text


async def test_a_stranger_cannot_open_someone_elses_book(session):
    owner = await linked_user(session, "مالک", "555001")
    book = await BookService(session).create_book(owner.id, "خصوصی", BookType.BUSINESS)
    await linked_user(session, "غریبه", "999")

    convo = await conversation(session)
    reply = await convo.handle(press(f"rep:book:{book.id}", external_id="999"))

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
