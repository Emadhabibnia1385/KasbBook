"""A book holds what it receives, in the currency it received it.

The arithmetic that matters here is a quantity, not a valuation: ten tethers in
and four out is six tethers, whatever the rate did in between. Every test
asserts the balance itself rather than that nothing raised.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType, Role
from kasbbook.modules.books.service import BookService
from kasbbook.modules.exchange.models import CurrencyConversion
from kasbbook.modules.exchange.service import ExchangeService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope, Transaction
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.errors import NotFound, ValidationError

pytestmark = pytest.mark.asyncio

TG = Provider.TELEGRAM
# Pinned: a wallet test that reads the clock fails on a future Tuesday for
# reasons nobody will connect to currencies.
DAY = date(2026, 8, 24)


def press(data, external_id="900001"):
    return IncomingEvent(
        kind=EventKind.CALLBACK,
        identity=ChannelIdentity(TG, external_id, "emad", "عماد"),
        chat_id=external_id, message_id="10", callback_data=data, callback_id="cb",
    )


def says(text, external_id="900001"):
    return IncomingEvent(
        kind=EventKind.MESSAGE,
        identity=ChannelIdentity(TG, external_id, "emad", "عماد"),
        chat_id=external_id, message_id="10", text=text,
    )


def labels(reply):
    return [b.text for row in reply.buttons for b in row]


async def workspace(session, enable=("USDT",)):
    identity = IdentityService(session)
    owner = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(owner.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "900001")

    books = BookService(session)
    book = await books.create_book(owner.id, "کارگاه", BookType.BUSINESS, "IRT")

    exchange = ExchangeService(session)
    for code in enable:
        await exchange.set_enabled(owner.id, book.id, code, True)

    return owner, book, exchange, Conversation(session, MemoryStateStore(), TG)


# ----------------------------------------------------------------- balances
async def test_a_received_token_stays_that_token(session):
    owner, book, exchange, _ = await workspace(session)
    ledger = LedgerService(session)

    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "10", currency="USDT", conversion_rate="167499",
                        occurred_on=DAY)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "5", currency="USDT", conversion_rate="228389",
                        occurred_on=DAY)
    await ledger.record(book.id, owner.id, Flow.EXPENSE, Scope.WORK, "سرور",
                        "4", currency="USDT", conversion_rate="228389",
                        occurred_on=DAY)

    # Fifteen in, four out. The rate moved in between and changed nothing.
    assert await exchange.balance_of(book.id, "USDT") == Decimal("11.0000")

    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit


async def test_the_base_currency_is_a_wallet_too(session):
    owner, book, exchange, _ = await workspace(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "5000000", occurred_on=DAY)
    await ledger.record(book.id, owner.id, Flow.EXPENSE, Scope.WORK, "اجاره",
                        "2000000", occurred_on=DAY)

    assert await exchange.balance_of(book.id, "IRT") == Decimal("3000000.0000")


# ----------------------------------------------------------------- refusals
async def test_a_token_expense_beyond_the_balance_is_refused(session):
    owner, book, exchange, _ = await workspace(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "10", currency="USDT", conversion_rate="167499",
                        occurred_on=DAY)
    before = await ledger.trial_balance(book.id)

    with pytest.raises(ValidationError) as refused:
        await ledger.record(book.id, owner.id, Flow.EXPENSE, Scope.WORK, "سرور",
                            "11", currency="USDT", conversion_rate="167499",
                            occurred_on=DAY)
    assert "کافی نیست" in str(refused.value)

    # Nothing was written: still one transaction, and the books still balance.
    rows = (await session.execute(
        select(Transaction).where(Transaction.book_id == book.id)
    )).scalars().all()
    assert len(rows) == 1
    assert await ledger.trial_balance(book.id) == before
    assert await exchange.balance_of(book.id, "USDT") == Decimal("10.0000")


async def test_a_currency_the_book_never_ticked_is_refused(session):
    owner, book, _, _ = await workspace(session, enable=())
    ledger = LedgerService(session)

    with pytest.raises(ValidationError) as refused:
        await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                            "10", currency="USDT", conversion_rate="167499",
                            occurred_on=DAY)
    assert "پشتیبانی نمی‌کند" in str(refused.value)
    assert (await session.execute(
        select(Transaction).where(Transaction.book_id == book.id)
    )).scalars().all() == []


async def test_a_base_currency_expense_is_never_blocked_by_a_balance(session):
    """A book's first entry is often an expense; refusing it would be absurd."""
    owner, book, _, _ = await workspace(session, enable=())
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, owner.id, Flow.EXPENSE, Scope.WORK, "اجاره",
                             "2000000", occurred_on=DAY)
    assert tx.converted_amount == Decimal("2000000.0000")


async def test_a_currency_still_held_cannot_be_switched_off(session):
    owner, book, exchange, _ = await workspace(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "3", currency="USDT", conversion_rate="167499",
                        occurred_on=DAY)

    with pytest.raises(ValidationError):
        await exchange.set_enabled(owner.id, book.id, "USDT", False)
    assert "USDT" in await exchange.allowed(book.id)


async def test_the_base_currency_cannot_be_switched_off(session):
    owner, book, exchange, _ = await workspace(session)
    with pytest.raises(ValidationError):
        await exchange.set_enabled(owner.id, book.id, "IRT", False)


# -------------------------------------------------------------- conversions
async def test_a_conversion_moves_the_balance_between_currencies(session):
    owner, book, exchange, _ = await workspace(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "100", currency="USDT", conversion_rate="167499",
                        occurred_on=DAY)
    before_debit, before_credit = await ledger.trial_balance(book.id)

    conversion = await exchange.convert(
        owner.id, book.id, "USDT", "40", "IRT", "9135560", occurred_on=DAY
    )

    assert await exchange.balance_of(book.id, "USDT") == Decimal("60.0000")
    assert await exchange.balance_of(book.id, "IRT") == Decimal("9135560.0000")
    # 9,135,560 toman for 40 tethers is 228,389 each.
    assert conversion.from_rate == Decimal("228389")

    # A swap is not income and not an expense, so the journal does not move.
    assert await ledger.trial_balance(book.id) == (before_debit, before_credit)


async def test_converting_more_than_is_held_is_refused(session):
    owner, book, exchange, _ = await workspace(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "5", currency="USDT", conversion_rate="167499",
                        occurred_on=DAY)

    with pytest.raises(ValidationError):
        await exchange.convert(owner.id, book.id, "USDT", "6", "IRT", "1000000",
                               occurred_on=DAY)
    assert (await session.execute(select(CurrencyConversion))).scalars().all() == []
    assert await exchange.balance_of(book.id, "USDT") == Decimal("5.0000")


async def test_a_token_to_token_swap_needs_its_value_in_the_books_currency(session):
    owner, book, exchange, _ = await workspace(session, enable=("USDT", "TON"))
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "100", currency="USDT", conversion_rate="228389",
                        occurred_on=DAY)

    with pytest.raises(ValidationError):
        await exchange.convert(owner.id, book.id, "USDT", "10", "TON", "7",
                               occurred_on=DAY)

    conversion = await exchange.convert(
        owner.id, book.id, "USDT", "10", "TON", "7",
        base_value="2283890", occurred_on=DAY,
    )
    assert await exchange.balance_of(book.id, "USDT") == Decimal("90.0000")
    assert await exchange.balance_of(book.id, "TON") == Decimal("7.0000")
    assert conversion.base_value == Decimal("2283890.0000")


# ---------------------------------------------------------------- isolation
async def test_another_account_cannot_see_or_touch_this_wallet(session):
    owner, book, exchange, _ = await workspace(session)
    stranger = await IdentityService(session).create_user("غریبه")

    # NotFound, not PermissionDenied: a book id must not be probeable.
    for call in (
        exchange.balances(stranger.id, book.id),
        exchange.options(stranger.id, book.id),
        exchange.set_enabled(stranger.id, book.id, "TON", True),
        exchange.convert(stranger.id, book.id, "USDT", "1", "IRT", "1", occurred_on=DAY),
    ):
        with pytest.raises(NotFound):
            await call


async def test_a_viewer_cannot_change_the_currencies(session):
    owner, book, exchange, _ = await workspace(session)
    identity = IdentityService(session)
    viewer = await identity.create_user("ناظر")
    await BookService(session).add_member(owner.id, book.id, viewer.id, Role.VIEWER)

    from kasbbook.shared.errors import PermissionDenied
    with pytest.raises(PermissionDenied):
        await exchange.set_enabled(viewer.id, book.id, "TON", True)
    assert "TON" not in await exchange.allowed(book.id)


# -------------------------------------------------------------------- bot
async def test_the_bot_asks_which_currency_and_records_it(session):
    """The whole point: a person can enter a tether without leaving Telegram."""
    owner, book, exchange, convo = await workspace(session)

    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:on:today"))
    await convo.handle(press("tx:type:wi"))
    await convo.handle(says("فروش"))
    reply = await convo.handle(says("10"))

    assert "به چه ارزی است" in reply.text
    assert "تتر" in labels(reply)

    reply = await convo.handle(press("tx:cur:USDT"))
    assert "نرخ هر تتر" in reply.text

    await convo.handle(says("228389"))
    await convo.handle(press("tx:skip"))

    assert await exchange.balance_of(book.id, "USDT") == Decimal("10.0000")
    row = (await session.execute(
        select(Transaction).where(Transaction.book_id == book.id)
    )).scalars().one()
    assert row.original_currency == "USDT"
    assert row.original_amount == Decimal("10.0000")
    assert row.conversion_rate == Decimal("228389.0000")
    assert row.converted_amount == Decimal("2283890.0000")


async def test_a_single_currency_book_is_never_asked(session):
    """One answer is not a question. The extra tap would be pure noise."""
    owner, book, exchange, convo = await workspace(session, enable=())

    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:on:today"))
    await convo.handle(press("tx:type:wi"))
    await convo.handle(says("فروش"))
    reply = await convo.handle(says("500000"))

    assert "به چه ارزی است" not in reply.text


async def test_the_wallet_screen_is_reachable_and_shows_the_holding(session):
    owner, book, exchange, convo = await workspace(session)
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "229.19", currency="USDT", conversion_rate="228389",
                        occurred_on=DAY)

    menu = await convo.handle(press(f"book:open:{book.id}"))
    assert any("کیف پول" in label for label in labels(menu))

    reply = await convo.handle(press(f"cu:home:{book.id}"))
    # Not rounded to 229: the fraction is real money.
    assert "229.19 تتر" in reply.text


async def test_the_bot_can_tick_a_currency_on_and_off(session):
    owner, book, exchange, convo = await workspace(session, enable=())

    await convo.handle(press(f"cu:set:{book.id}"))
    reply = await convo.handle(press("cu:tog:TON"))

    assert "TON" in await exchange.allowed(book.id)
    assert any("✅ تون" in label for label in labels(reply))

    await convo.handle(press("cu:tog:TON"))
    assert "TON" not in await exchange.allowed(book.id)
