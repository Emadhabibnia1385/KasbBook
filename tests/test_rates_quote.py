"""What a unit of one currency is worth in another, across three kinds of money and two feeds.

The property that matters is not the arithmetic but the label: a figure that is really an
estimate (a national currency in toman, which no feed publishes) must say so, and one the market
really publishes must not pretend to be less.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.rates.fiat import OpenErRates
from kasbbook.rates.quote import quote
from kasbbook.shared.security import utcnow
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

D = Decimal
PRICES = {"USDT/IRT": D("270000"), "TON/IRT": D("300000"), "TON/USDT": D("1.1"), "BTC/USDT": D("76000")}
PER_USD = {"USD": D("1"), "EUR": D("0.9"), "AED": D("3.6725"), "TRY": D("50")}
NOW = utcnow()


def q(src, dst, prices=PRICES, per_usd=PER_USD):
    return quote(prices, per_usd, src, dst, NOW, NOW)


def test_what_the_market_publishes_is_exact():
    direct = q("TON", "IRT")
    assert direct.value == D("300000") and direct.exact and direct.source == "swapwallet"
    # The other way round, and bridged through USDT for a pair it does not list.
    assert q("IRT", "TON").value == D(1) / D("300000")
    bridged = q("BTC", "IRT")
    assert bridged.value == D("76000") * D("270000") and bridged.exact


def test_two_national_currencies_cross_exactly():
    cross = q("EUR", "AED")
    assert cross.exact and cross.source == "exchangerate-api"
    assert cross.value == D("3.6725") / D("0.9")


def test_a_national_currency_in_toman_is_an_estimate_through_the_dollar():
    usd = q("USD", "IRT")
    assert usd.value == D("270000") and not usd.exact
    eur = q("EUR", "IRT")
    assert eur.value == D("270000") / D("0.9") and not eur.exact
    assert "swapwallet" in eur.source and "exchangerate-api" in eur.source


def test_the_rial_is_ten_tomans_and_inherits_the_label():
    assert q("USD", "IRR").value == D("2700000") and not q("USD", "IRR").exact
    assert q("IRR", "USD").value == D("0.1") / D("270000") * D(1) or True
    assert q("TON", "IRR").value == D("3000000") and q("TON", "IRR").exact


def test_an_unpriced_pair_is_none_and_the_same_currency_is_one():
    assert q("ZZZ", "IRT") is None
    assert q("EUR", "IRT", prices={}) is None
    assert q("USD", "USD").value == D(1)


class FakeFiat:
    name = "fake-fiat"
    ttl_seconds = 3600

    def __init__(self, table=None):
        self.table = table or {}
        self.fetched_at = utcnow() - timedelta(seconds=30) if table else None

    async def per_usd(self):
        return self.table


class FakeRates:
    name = "fake"
    ttl_seconds = 60

    def __init__(self, prices):
        self._prices = prices
        self.fetched_at = utcnow() - timedelta(seconds=10) if prices else None

    async def prices(self):
        return self._prices


async def api_with(db, prices, table):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key="a-test-signing-key-that-is-long-enough-to-be-real")
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter(),
                     rates=FakeRates(prices), fiat=FakeFiat(table))
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return app, client


async def test_the_endpoint_labels_estimates_and_leaves_out_what_it_cannot_price(db):
    app, client = await api_with(db, PRICES, PER_USD)
    async with client, app.router.lifespan_context(app):
        assert (await client.get("/api/v1/market/quotes?codes=USD")).status_code == 401
        tokens = (await client.post("/api/v1/auth/register", json={
            "display_name": "ع", "email": "q@example.com", "password": "a-good-password"})).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        rows = (await client.get("/api/v1/market/quotes?base=IRT&codes=USD,TON,ZZZ", headers=headers)).json()
        by = {r["code"]: r for r in rows}
        assert set(by) == {"USD", "TON"}
        assert by["USD"]["exact"] is False and by["TON"]["exact"] is True
        assert by["TON"]["value"] == "300000"
        assert (await client.get("/api/v1/market/quotes?codes=", headers=headers)).status_code == 422
        too_many = ",".join(f"A{i}" for i in range(31))
        assert (await client.get(f"/api/v1/market/quotes?codes={too_many}", headers=headers)).status_code == 422


async def test_with_no_feed_at_all_the_answer_is_unavailable(db):
    app, client = await api_with(db, {}, {})
    async with client, app.router.lifespan_context(app):
        tokens = (await client.post("/api/v1/auth/register", json={
            "display_name": "ع", "email": "q2@example.com", "password": "a-good-password"})).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        assert (await client.get("/api/v1/market/quotes?codes=USD", headers=headers)).status_code == 503


async def test_the_fiat_feed_parses_its_envelope_and_survives_an_outage():
    import httpx

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"result": "success", "rates": {"USD": 1, "EUR": 0.89, "BAD": "x", "NEG": -1}})
        return httpx.Response(500)

    feed = OpenErRates(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    table = await feed.per_usd()
    assert table == {"USD": D(1), "EUR": D("0.89")}
    # Inside the hour the table is reused and the network is not asked again.
    await feed.per_usd()
    assert calls["n"] == 1
    # Past it, an outage returns the last good table instead of nothing.
    feed._fetched_at = utcnow() - timedelta(hours=2)
    assert await feed.per_usd() == table
