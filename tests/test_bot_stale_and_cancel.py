"""Old buttons, double taps and cancel: the three ways a chat can lie about state.

A chat keeps every message ever sent, so a button from five minutes ago is
always still tappable, and in webhook mode two taps can be in flight at once.
What is proved here: an old button never acts on a newer draft, one confirm
records one transaction, and "انصراف" always means cancel.
"""

from __future__ import annotations

import asyncio
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.database import Database

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


def button(reply, prefix):
    """The data of the first button on a screen that starts with `prefix`."""
    for row in reply.buttons:
        for b in row:
            if b.data and b.data.startswith(prefix):
                return b.data
    raise AssertionError(f"no {prefix!r} button; have {[b.data for r in reply.buttons for b in r]}")


async def setup(session, books_named=("مغازه",)):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")
    books = [await BookService(session).create_book(user.id, n, BookType.BUSINESS)
             for n in books_named]
    return user, books, Conversation(session, MemoryStateStore(), TG)


async def recorded(session, user, book):
    return await LedgerService(session).transactions(book.id, user.id)


# ------------------------------------------------------------------- B1
async def test_an_old_quick_button_does_not_record_the_newer_draft(session):
    user, (book,), convo = await setup(session)

    old = await convo.handle(says("فروش 100000"))
    await convo.handle(says("اجاره 9000000"))
    reply = await convo.handle(press(button(old, "qk:flow:income")))

    assert await recorded(session, user, book) == []
    assert "قدیمی" in reply.text
    # The person is shown what is actually waiting, not sent home empty-handed.
    assert "اجاره" in reply.text and "9,000,000" in reply.text


async def test_the_current_quick_button_still_records_after_a_stale_tap(session):
    user, (book,), convo = await setup(session)

    old = await convo.handle(says("فروش 100000"))
    new = await convo.handle(says("اجاره 9000000"))
    await convo.handle(press(button(old, "qk:flow:income")))
    reply = await convo.handle(press(button(new, "qk:flow:expense")))

    assert "ثبت شد" in reply.text
    rows = await recorded(session, user, book)
    assert [(r.category, r.converted_amount) for r in rows] == [("اجاره", Decimal("9000000"))]
    await _balanced(session)


async def test_an_old_book_choice_button_is_stale_too(session):
    user, (shop, side), convo = await setup(session, ("مغازه", "فریلنس"))

    old = await convo.handle(says("فروش 100000"))
    await convo.handle(says("اجاره 9000000"))
    reply = await convo.handle(press(button(old, "qk:book:")))

    assert "قدیمی" in reply.text
    # The new draft is still waiting for its book, and was not given one.
    assert "کدام دفتر" in reply.text
    assert await recorded(session, user, shop) == []


async def test_a_button_without_a_nonce_is_stale(session):
    user, (book,), convo = await setup(session)

    await convo.handle(says("فروش 100000"))
    reply = await convo.handle(press("qk:flow:income"))

    assert "قدیمی" in reply.text
    assert await recorded(session, user, book) == []


async def test_tapping_a_confirm_button_after_it_was_recorded_says_so(session):
    user, (book,), convo = await setup(session)

    screen = await convo.handle(says("فروش 100000"))
    data = button(screen, "qk:flow:income")
    await convo.handle(press(data))
    reply = await convo.handle(press(data))

    assert "قدیمی" in reply.text
    assert len(await recorded(session, user, book)) == 1


# ------------------------------------------------------------------- B2
async def _two_sessions_one_database():
    """Webhook mode: every request has its own session over one database."""
    folder = tempfile.TemporaryDirectory()
    database = Database(f"sqlite+aiosqlite:///{(Path(folder.name) / 'race.sqlite').as_posix()}")
    await database.create_all()
    return folder, database


async def _tap_in_own_session(database, state, data):
    async for s in database.session():
        try:
            reply = await Conversation(s, state, TG).handle(press(data))
            await s.commit()
            return reply
        except Exception:
            await s.rollback()
            raise


async def _count(database):
    from sqlalchemy import func, select
    from kasbbook.modules.ledger.models import Transaction
    async for s in database.session():
        return (await s.execute(select(func.count()).select_from(Transaction))).scalar()


async def test_two_simultaneous_quick_confirms_record_once():
    folder, database = await _two_sessions_one_database()
    try:
        state = MemoryStateStore()
        async for s in database.session():
            identity = IdentityService(s)
            user = await identity.create_user("عماد")
            issued = await identity.start_link_from_web(user.id, TG)
            await identity.complete_link_from_messenger(issued.token, TG, "555001")
            await BookService(s).create_book(user.id, "مغازه", BookType.BUSINESS)
            screen = await Conversation(s, state, TG).handle(says("فروش 250000"))
            await s.commit()
        data = button(screen, "qk:flow:income")

        replies = await asyncio.gather(
            _tap_in_own_session(database, state, data),
            _tap_in_own_session(database, state, data),
        )

        assert await _count(database) == 1
        assert sorted("قدیمی" in r.text for r in replies) == [False, True]
        async for s in database.session():
            await _balanced(s)
    finally:
        await database.dispose()
        folder.cleanup()


async def test_two_simultaneous_description_skips_record_once():
    folder, database = await _two_sessions_one_database()
    try:
        state = MemoryStateStore()
        async for s in database.session():
            identity = IdentityService(s)
            user = await identity.create_user("عماد")
            issued = await identity.start_link_from_web(user.id, TG)
            await identity.complete_link_from_messenger(issued.token, TG, "555001")
            book = await BookService(s).create_book(user.id, "مغازه", BookType.BUSINESS)
            convo = Conversation(s, state, TG)
            await convo.handle(press("tx:new"))
            await convo.handle(press(f"tx:book:{book.id}"))
            await convo.handle(press("tx:flow:income"))
            await convo.handle(says("فروش"))
            await convo.handle(says("۲۵۰ک"))
            await s.commit()

        replies = await asyncio.gather(
            _tap_in_own_session(database, state, "tx:skip"),
            _tap_in_own_session(database, state, "tx:skip"),
        )

        assert await _count(database) == 1
        assert sorted("قدیمی" in r.text for r in replies) == [False, True]
    finally:
        await database.dispose()
        folder.cleanup()


async def test_a_failed_save_keeps_the_draft_so_the_person_can_retry(session):
    # The draft is claimed before it is recorded; if the record is refused the
    # claim must be given back, or one typo would cost the whole entry.
    user, (book,), convo = await setup(session)
    await convo.handle(press("tx:new"))
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:income"))
    await convo.handle(says("فروش"))
    await convo.handle(says("0"))

    first = await convo.handle(press("tx:skip"))
    assert "ثبت شد" not in first.text
    assert (await convo.state.get("telegram:555001")).get("flow") == "tx"


async def test_an_old_skip_button_neither_records_twice_nor_wipes_the_next_draft(session):
    user, (book,), convo = await setup(session)
    await convo.handle(press("tx:new"))
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:flow:income"))
    await convo.handle(says("فروش"))
    await convo.handle(says("۲۵۰ک"))
    await convo.handle(press("tx:skip"))

    again = await convo.handle(press("tx:skip"))
    assert "قدیمی" in again.text
    assert len(await recorded(session, user, book)) == 1

    # A new entry is started; the old skip button must not eat it.
    await convo.handle(says("اجاره 9000000"))
    await convo.handle(press("tx:skip"))
    assert (await convo.state.get("telegram:555001")).get("flow") == "quick"


async def test_pop_takes_the_value_once():
    store = MemoryStateStore()
    await store.set("k", {"flow": "quick"})
    assert await store.pop("k") == {"flow": "quick"}
    assert await store.pop("k") == {}
    assert await store.get("k") == {}


# The Redis store's pop is raced against a real Redis in
# tests/test_concurrency_services.py (the CI `services` job): a fake here
# could only restate which commands the code sends, not that they are atomic.


# ------------------------------------------------------------------- B5
async def test_cancel_button_on_the_new_book_prompt_creates_no_book(session):
    user, books, convo = await setup(session, ())

    await convo.handle(press("book:new"))
    prompt = await convo.handle(press("book:type:business"))
    reply = await convo.handle(press(button(prompt, "nav:")))
    assert "انصراف دادی" in reply.text

    follow_up = await convo.handle(says("فروش 250000"))

    # The next line was read as a transaction attempt, not swallowed as a name.
    assert await BookService(session).books_for_user(user.id) == []
    assert "ساخته شد" not in follow_up.text


async def test_typing_cancel_on_the_new_book_prompt_creates_no_book(session):
    user, books, convo = await setup(session, ())

    await convo.handle(press("book:new"))
    await convo.handle(press("book:type:business"))
    reply = await convo.handle(says("انصراف"))

    assert "انصراف دادی" in reply.text
    assert await BookService(session).books_for_user(user.id) == []
    assert (await convo.state.get("telegram:555001")) == {}


@pytest.mark.parametrize("opening", [
    ["tx:new", "tx:one"],
    ["rep:menu"],
    ["book:new", "book:type:personal"],
    ["rm:panel"],
])
async def test_the_cancel_word_clears_every_text_input_state(session, opening):
    user, (book,), convo = await setup(session, ("مغازه",))
    if opening[0] == "tx:new":
        opening = ["tx:new", f"tx:book:{book.id}", "tx:flow:income"]
    for data in opening:
        await convo.handle(press(data))
    state_before = await convo.state.get("telegram:555001")

    reply = await convo.handle(says("انصراف"))

    if state_before.get("flow"):
        assert "انصراف دادی" in reply.text
    assert (await convo.state.get("telegram:555001")) == {}
    assert len(await BookService(session).books_for_user(user.id)) == 1


async def test_the_cancel_word_with_nothing_in_flight_is_not_a_transaction(session):
    user, (book,), convo = await setup(session)

    reply = await convo.handle(says("انصراف"))

    assert await recorded(session, user, book) == []
    assert reply.text


# ----------------------------------------------------------- helpers
async def _balanced(session):
    from kasbbook.modules.ledger.service import LedgerService as L
    from sqlalchemy import select
    from kasbbook.modules.books.models import Book

    ledger = L(session)
    for book in (await session.execute(select(Book))).scalars():
        debit, credit = await ledger.trial_balance(book.id)
        assert debit == credit


# ------------------------------------------- a refusal keeps nothing it began
async def test_a_refused_step_leaves_nothing_half_written(session, monkeypatch):
    """The bot answers a domain error, and the runner then commits the session.

    So anything a service had already flushed before it refused was committed
    with the refusal - a half-written change behind a message saying nothing
    was done. Simulated here with a record() that writes its row and then
    refuses, which is the shape any such service bug would have.
    """
    from kasbbook.modules.ledger.models import Transaction
    from kasbbook.shared.errors import ValidationError
    from sqlalchemy import select

    user, (book,), convo = await setup(session)
    real_record = LedgerService.record

    async def writes_then_refuses(self, *args, **kwargs):
        await real_record(self, *args, **kwargs)
        raise ValidationError("رد شد")

    monkeypatch.setattr(LedgerService, "record", writes_then_refuses)
    await session.commit()

    asked = await convo.handle(says("فروش 100000"))
    reply = await convo.handle(press(button(asked, "qk:flow:income")))
    assert "رد شد" in reply.text

    await session.commit()          # what the runner does next
    rows = (await session.execute(
        select(Transaction).where(Transaction.book_id == book.id)
    )).scalars().all()
    assert rows == []
    assert await LedgerService(session).trial_balance(book.id) == (0, 0)
