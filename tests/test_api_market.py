"""Live prices over HTTP, and what the panel is told when the feed is not live.

No test here reaches the network: a price feed is exactly the dependency that
cannot be assumed, and the cases that matter (down with a memory, down with
none) can only be made to happen with a provider the test controls.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.rates.swapwallet import SwapWalletRates
from kasbbook.shared.security import utcnow
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"

# The live endpoint's real shape (checked against swapwallet.app): an envelope
# around a flat pair map whose values are strings.
BODY = {
    "status": "OK",
    "result": {
        "USDT/IRT": "271927", "BTC/IRT": "20754393191", "ETH/IRT": "614680106",
        "TON/IRT": "304558", "BTC/USDT": "76323.4", "SHIB/USDT": "0.00000045",
    },
}


class FakeRates:
    """A provider that is whatever the test says it is."""

    name = "fake"
    ttl_seconds = 60

    def __init__(self, prices=None, age=0):
        self._prices = {k: Decimal(v) for k, v in (prices or {}).items()}
        self._fetched_at = utcnow() - timedelta(seconds=age) if prices else None

    @property
    def fetched_at(self):
        return self._fetched_at

    async def prices(self):
        return self._prices


async def signed_in(client):
    tokens = (await client.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "owner@example.com",
        "password": "a-good-password",
    })).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
async def make(db):
    """Build an API around a given provider and sign someone in; closed with the test."""
    opened = []

    async def _make(rates):
        settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
        app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter(),
                         rates=rates)
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        opened.append((client, context))
        return client, await signed_in(client)

    yield _make
    for client, context in opened:
        await context.__aexit__(None, None, None)
        await client.aclose()


# ------------------------------------------------------------------ happy path
async def test_default_rates_come_back_exact_with_source_and_time(make):
    client, headers = await make(FakeRates({
        "USDT/IRT": "271927", "BTC/IRT": "20754393191", "DOGE/IRT": "19728.3",
    }))
    response = await client.get("/api/v1/market/rates", headers=headers)

    assert response.status_code == 200
    rows = {row["pair"]: row for row in response.json()}
    # Only what is both published and on the default list; DOGE is not asked
    # for, and the pairs the market lacks are not invented.
    assert set(rows) == {"USDT/IRT", "BTC/IRT"}
    usdt = rows["USDT/IRT"]
    assert usdt["value"] == "271927"
    assert (usdt["base"], usdt["quote"]) == ("USDT", "IRT")
    assert usdt["source"] == "fake"
    assert usdt["stale"] is False
    assert usdt["age_seconds"] < 5
    assert usdt["fetched_at"].startswith(str(utcnow().year))


async def test_a_requested_pair_is_returned_in_the_order_asked_in_any_case(make):
    client, headers = await make(FakeRates({
        "USDT/IRT": "271927", "TON/USDT": "1.12", "TON/IRT": "304558",
    }))
    response = await client.get("/api/v1/market/rates", headers=headers,
                                params={"pairs": "ton/usdt, usdt/irt, nope/irt"})

    assert [r["pair"] for r in response.json()] == ["TON/USDT", "USDT/IRT"]
    assert response.json()[0]["value"] == "1.12"


async def test_a_tiny_price_is_never_written_in_scientific_notation(make):
    client, headers = await make(FakeRates({"SHIB/USDT": "0.00000045"}))
    response = await client.get("/api/v1/market/rates", headers=headers,
                                params={"pairs": "SHIB/USDT"})
    # str(Decimal("0.00000045")) is "4.5E-7", which no client should parse.
    assert response.json()[0]["value"] == "0.00000045"


# --------------------------------------------------------------------- refusal
async def test_a_malformed_pair_is_refused(make):
    client, headers = await make(FakeRates({"USDT/IRT": "1"}))
    for bad in ("USDTIRT", "USDT/IRT/X", "../etc", "US DT/IRT"):
        response = await client.get("/api/v1/market/rates", headers=headers,
                                    params={"pairs": bad})
        assert response.status_code == 422, bad


async def test_asking_for_too_many_pairs_is_refused(make):
    client, headers = await make(FakeRates({"USDT/IRT": "1"}))
    many = ",".join(f"C{i}/IRT" for i in range(21))
    response = await client.get("/api/v1/market/rates", headers=headers,
                                params={"pairs": many})
    assert response.status_code == 422


async def test_prices_are_for_signed_in_people_only(make):
    client, _ = await make(FakeRates({"USDT/IRT": "1"}))
    assert (await client.get("/api/v1/market/rates")).status_code == 401


# ----------------------------------------------------------------- feed is down
async def test_an_old_price_is_returned_flagged_stale_with_its_age(make):
    # The provider keeps its last good prices through an outage, and its
    # clock says they are five minutes old.
    client, headers = await make(FakeRates({"USDT/IRT": "271927"}, age=300))
    row = (await client.get("/api/v1/market/rates", headers=headers)).json()[0]

    assert row["stale"] is True
    assert 299 <= row["age_seconds"] <= 305
    assert row["value"] == "271927"


async def test_with_no_price_at_all_the_answer_is_503_in_persian(make):
    client, headers = await make(FakeRates())
    response = await client.get("/api/v1/market/rates", headers=headers)

    assert response.status_code == 503
    assert "در دسترس نیست" in response.json()["detail"]


# ------------------------------------------------- the real provider, mocked wire
def wire(handler, **kwargs):
    return SwapWalletRates(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kwargs)


async def test_the_real_provider_shape_is_served_and_fetched_once_a_minute(make):
    calls = []

    def ok(request):
        calls.append(request.url)
        return httpx.Response(200, json=BODY)

    client, headers = await make(wire(ok))
    for _ in range(4):
        response = await client.get("/api/v1/market/rates", headers=headers)
    assert response.status_code == 200
    assert {r["pair"] for r in response.json()} == {
        "USDT/IRT", "BTC/IRT", "ETH/IRT", "TON/IRT", "BTC/USDT"}
    assert {r["source"] for r in response.json()} == {"swapwallet"}
    # Four polls, one request to the provider.
    assert len(calls) == 1


async def test_an_outage_after_a_good_fetch_serves_the_old_prices_stale(make):
    state = {"up": True, "calls": 0}

    def flaky(_request):
        state["calls"] += 1
        if not state["up"]:
            raise httpx.ConnectError("no route")
        return httpx.Response(200, json=BODY)

    provider = wire(flaky, ttl_seconds=60)
    client, headers = await make(provider)
    first = (await client.get("/api/v1/market/rates", headers=headers)).json()
    assert first[0]["stale"] is False

    # Two minutes pass and the provider goes down.
    provider._fetched_at = utcnow() - timedelta(seconds=120)
    state["up"] = False
    rows = (await client.get("/api/v1/market/rates", headers=headers)).json()
    assert rows[0]["stale"] is True
    assert rows[0]["value"] == "271927"
    assert rows[0]["age_seconds"] >= 120

    # And the next poll does not go back to a dead service straight away.
    calls_before = state["calls"]
    await client.get("/api/v1/market/rates", headers=headers)
    assert state["calls"] == calls_before


async def test_a_provider_that_never_answered_gives_503(make):
    def boom(_request):
        raise httpx.ConnectError("no route")

    client, headers = await make(wire(boom))
    response = await client.get("/api/v1/market/rates", headers=headers)
    assert response.status_code == 503
