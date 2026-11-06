"""The bot learns what the web panel knows: any currency by name, prices, and the money a payment was in.

The catalog search is pure and tested on its own; the rest drives the conversation the way an adapter
would. A fake rate source stands in for the network, with a `table` and a `quote_detail` like the real one.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from kasbbook.bot import screens
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.exchange.catalog import search
from kasbbook.modules.identity.models import Provider
from kasbbook.rates.quote import Quote
from kasbbook.shared.security import utcnow

from tests.test_wallet_currencies import labels, press, says, workspace

pytestmark = pytest.mark.asyncio

TG = Provider.TELEGRAM


def test_the_search_finds_by_code_name_symbol_and_country():
    assert search("usd")[0].code == "USD"
    assert search("دلار")[0].name.startswith("دلار")
    assert any(c.code == "TRY" for c in search("ترکیه"))
    assert search("btc")[0].code == "BTC"
    # Arabic yeh and kaf, as a keyboard may type them, meet the Persian ones.
    assert search("بيت كوين")[0].code == "BTC"
    assert search("   ") == [] and search("zzzzzz") == []
    assert len(search("د", limit=3)) <= 3


class FakeMarket:
    """What the real `MarketRates` offers the bot, with fixed answers."""

    def __init__(self, exact=True):
        now = utcnow()
        self._exact = exact
        self.stamp = now

    async def quote_detail(self, code, base):
        return Quote(Decimal("270000"), self._exact, "swapwallet", self.stamp)

    async def quote(self, code, base):
        return Decimal("270000")

    async def table(self, codes, base):
        return [(code, Quote(Decimal("270000"), code in ("USDT", "BTC"), "swapwallet", self.stamp)) for code in codes]


async def test_any_currency_can_be_found_and_switched_on_from_the_bot(session):
    owner, book, exchange, bot = await workspace(session, enable=())
    await bot.handle(press(f"cu:set:{book.id}"))
    reply = await bot.handle(press("cu:find"))
    assert "کدام ارز" in reply.text

    found = await bot.handle(says("دلار"))
    assert "cu:tog:USD" in [b.data for row in found.buttons for b in row]

    after = await bot.handle(press("cu:tog:USD"))
    assert "USD" in await exchange.allowed(book.id)
    # Still on the search, so a second currency can follow without starting over.
    assert "✅" in after.text


async def test_a_search_with_no_match_says_so_and_asks_again(session):
    owner, book, exchange, bot = await workspace(session, enable=())
    await bot.handle(press(f"cu:set:{book.id}"))
    await bot.handle(press("cu:find"))
    reply = await bot.handle(says("zzzzzz"))
    assert "پیدا نشد" in reply.text


async def test_a_line_typed_on_the_tick_screen_is_not_taken_for_a_search(session):
    owner, book, exchange, bot = await workspace(session, enable=())
    await bot.handle(press(f"cu:set:{book.id}"))
    reply = await bot.handle(says("دلار"))
    assert "cu:tog:USD" not in [b.data for row in reply.buttons for b in row]


async def test_the_prices_screen_labels_national_currencies_as_estimates(session):
    owner, book, exchange, _ = await workspace(session, enable=())
    bot = Conversation(session, MemoryStateStore(), TG, rates=FakeMarket())
    reply = await bot.handle(press(f"cu:prices:{book.id}"))
    assert "حدودی" in reply.text and "دلار" in reply.text and "تتر" in reply.text
    assert any("تازه‌سازی" in label for label in labels(reply))


async def test_the_prices_screen_survives_a_provider_with_no_table(session):
    owner, book, exchange, _ = await workspace(session, enable=())
    bot = Conversation(session, MemoryStateStore(), TG, rates=None)
    reply = await bot.handle(press(f"cu:prices:{book.id}"))
    assert "قیمتی در دسترس نیست" in reply.text


async def test_prices_are_for_those_who_can_see_the_book(session):
    from kasbbook.modules.identity.service import IdentityService

    owner, book, exchange, _ = await workspace(session, enable=())
    other = await IdentityService(session).create_user("غریبه")
    issued = await IdentityService(session).start_link_from_web(other.id, TG)
    await IdentityService(session).complete_link_from_messenger(issued.token, TG, "900002")
    bot = Conversation(session, MemoryStateStore(), TG, rates=FakeMarket())
    reply = await bot.handle(press(f"cu:prices:{book.id}", external_id="900002"))
    assert "تتر" not in reply.text


def tx(original_currency, original_amount, converted):
    return SimpleNamespace(original_currency=original_currency, original_amount=Decimal(original_amount),
                           converted_amount=Decimal(converted))


def test_a_payment_in_another_currency_is_shown_in_that_currency_first():
    foreign = tx("TON", "20", "7169006")
    assert screens.tx_money(foreign, "IRT").startswith("20 ")
    assert "≈" in screens.tx_money(foreign, "IRT") and "7,169,006" in screens.tx_money(foreign, "IRT")
    assert "≈" not in screens.tx_short(foreign, "IRT") and screens.tx_short(foreign, "IRT").startswith("20 ")
    local = tx("IRT", "5000", "5000")
    assert screens.tx_money(local, "IRT") == "5,000 تومان"
    # A button label drops the unit to stay short.
    assert screens.tx_short(local, "IRT") == "5,000"


def test_an_estimated_rate_is_labelled_and_an_exact_one_is_not():
    estimate, _ = screens.ask_description_with_rate("USD", Decimal("270000"), "IRT", Decimal("1"), estimate=True)
    exact, _ = screens.ask_description_with_rate("TON", Decimal("300000"), "IRT", Decimal("1"))
    assert "حدودی" in estimate and "حدودی" not in exact
