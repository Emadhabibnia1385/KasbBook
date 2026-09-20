"""The live rate source, and what happens when it is not there.

Nothing here touches the network: a test that reaches the internet fails on a
train, and a price feed is exactly the dependency you cannot assume.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.exchange.service import ExchangeService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.rates.swapwallet import SwapWalletRates

pytestmark = pytest.mark.asyncio

TG = Provider.TELEGRAM
DAY = date(2026, 8, 24)

# What the service actually answers — a result object inside an envelope, with
# every price as a string.
BODY = {
    "status": "OK",
    "result": {"USDT/IRT": "230970", "TON/IRT": "316890", "TON/USDT": "1.372",
               "TRX/IRT": "78957", "BTC/IRT": "18591167949"},
}


def source(handler, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SwapWalletRates(client=client, **kwargs)


def ok(_request):
    return httpx.Response(200, json=BODY)


async def test_a_published_price_is_read_exactly(session):
    rates = source(ok)
    # A string all the way to Decimal: a rate that went through a float is a
    # rate that is quietly wrong.
    assert await rates.quote("USDT", "IRT") == Decimal("230970")
    assert await rates.quote("TON", "USDT") == Decimal("1.372")
    assert await rates.quote("IRT", "IRT") == Decimal("1")


async def test_a_pair_published_the_other_way_round_is_inverted(session):
    rates = source(ok)
    # IRT/TON is not published; TON/IRT is.
    got = await rates.quote("IRT", "TON")
    assert got == Decimal("1") / Decimal("316890")


async def test_an_unknown_currency_has_no_quote(session):
    assert await source(ok).quote("DOGE", "IRT") is None


async def test_a_dead_price_service_is_not_an_error(session):
    """Somebody recording a sale must not be stopped because a feed is down."""
    def boom(_request):
        raise httpx.ConnectError("no route")

    assert await source(boom).quote("USDT", "IRT") is None


async def test_an_unexpected_body_shape_is_not_an_error(session):
    def wrong(_request):
        return httpx.Response(200, json={"status": "OK"})

    assert await source(wrong).quote("USDT", "IRT") is None


async def test_prices_are_fetched_once_within_the_cache_window(session):
    calls = []

    def counted(request):
        calls.append(request.url)
        return httpx.Response(200, json=BODY)

    rates = source(counted, ttl_seconds=300)
    for _ in range(5):
        await rates.quote("USDT", "IRT")
    assert len(calls) == 1


# ------------------------------------------------------------------- in use
async def workspace(session, rates=None):
    identity = IdentityService(session)
    owner = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(owner.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "930001")
    book = await BookService(session).create_book(owner.id, "کارگاه", BookType.BUSINESS, "IRT")
    await ExchangeService(session).set_enabled(owner.id, book.id, "USDT", True)
    return owner, book, Conversation(session, MemoryStateStore(), TG, rates=rates)


def press(data):
    return IncomingEvent(kind=EventKind.CALLBACK,
                         identity=ChannelIdentity(TG, "930001", "emad", "عماد"),
                         chat_id="930001", message_id="10", callback_data=data, callback_id="cb")


def says(text):
    return IncomingEvent(kind=EventKind.MESSAGE,
                         identity=ChannelIdentity(TG, "930001", "emad", "عماد"),
                         chat_id="930001", message_id="10", text=text)


async def entry(convo, book):
    await convo.handle(press(f"tx:book:{book.id}"))
    await convo.handle(press("tx:on:today"))
    await convo.handle(press("tx:type:wi"))
    await convo.handle(says("فروش"))
    await convo.handle(says("8"))
    return await convo.handle(press("tx:cur:USDT"))


async def test_the_bot_applies_todays_price_without_asking(session):
    owner, book, convo = await workspace(session, rates=source(ok))
    reply = await entry(convo, book)

    assert "نرخ امروز" in reply.text
    assert "230,970" in reply.text
    # 8 × 230,970
    assert "1,847,760" in reply.text

    await convo.handle(press("tx:skip"))
    from sqlalchemy import select
    from kasbbook.modules.ledger.models import Transaction
    row = (await session.execute(select(Transaction).where(
        Transaction.book_id == book.id))).scalars().one()
    assert row.original_currency == "USDT"
    assert row.conversion_rate == Decimal("230970.0000")
    assert row.converted_amount == Decimal("1847760.0000")


async def test_without_a_price_source_the_bot_still_asks(session):
    """The old path has to keep working, or a dead feed blocks every entry."""
    owner, book, convo = await workspace(session, rates=None)
    reply = await entry(convo, book)

    assert "نرخ هر تتر" in reply.text
    await convo.handle(says("228389"))
    await convo.handle(press("tx:skip"))

    from sqlalchemy import select
    from kasbbook.modules.ledger.models import Transaction
    row = (await session.execute(select(Transaction).where(
        Transaction.book_id == book.id))).scalars().one()
    assert row.conversion_rate == Decimal("228389.0000")


async def test_the_person_can_override_the_live_price(session):
    owner, book, convo = await workspace(session, rates=source(ok))
    await entry(convo, book)

    reply = await convo.handle(press("tx:rate:x"))
    assert "نرخ هر تتر" in reply.text
    await convo.handle(says("250000"))
    await convo.handle(press("tx:skip"))

    from sqlalchemy import select
    from kasbbook.modules.ledger.models import Transaction
    row = (await session.execute(select(Transaction).where(
        Transaction.book_id == book.id))).scalars().one()
    assert row.conversion_rate == Decimal("250000.0000")


async def test_the_wallet_is_valued_at_todays_price(session):
    owner, book, convo = await workspace(session, rates=source(ok))
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "10", currency="USDT", conversion_rate="167499", occurred_on=DAY)

    exchange = ExchangeService(session, rates=source(ok))
    rows, total = await exchange.valuation(owner.id, book.id)
    usdt = [r for r in rows if r.code == "USDT"][0]

    # Recorded at 167,499 and still recorded at 167,499; only the holding is
    # revalued.
    assert usdt.amount == Decimal("10.0000")
    assert usdt.value == Decimal("2309700.0000")
    assert total == Decimal("2309700.0000")

    from sqlalchemy import select
    from kasbbook.modules.ledger.models import Transaction
    row = (await session.execute(select(Transaction).where(
        Transaction.book_id == book.id))).scalars().one()
    assert row.converted_amount == Decimal("1674990.0000")


async def test_a_holding_with_no_price_leaves_no_total(session):
    """A total built on a guess is worse than no total."""
    owner, book, convo = await workspace(session, rates=source(ok))
    await ExchangeService(session).set_enabled(owner.id, book.id, "TON", True)
    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.WORK, "فروش",
                        "5", currency="TON", conversion_rate="300000", occurred_on=DAY)

    def only_usdt(_request):
        return httpx.Response(200, json={"status": "OK", "result": {"USDT/IRT": "230970"}})

    rows, total = await ExchangeService(session, rates=source(only_usdt)).valuation(
        owner.id, book.id)
    ton = [r for r in rows if r.code == "TON"][0]
    assert ton.value is None
    assert total is None
