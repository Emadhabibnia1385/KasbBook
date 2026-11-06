"""Holdings valued at today's price, and financial notes.

The market feeds are faked: a test decides what gold costs, and what happens when a feed is down.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.rates.metals import MetalSnapshot
from kasbbook.shared.security import utcnow
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"


class FakeMetals:
    def __init__(self, iran=None, world=None):
        at = utcnow() - timedelta(seconds=20)
        self._snapshot = MetalSnapshot(
            iran={k: Decimal(v) for k, v in (iran or {}).items()}, iran_at=at if iran else None,
            world={k: Decimal(v) for k, v in (world or {}).items()}, world_at=at if world else None,
        )

    async def snapshot(self):
        return self._snapshot


class FakeFiat:
    name = "fake-fiat"

    def __init__(self, table=None):
        self.table = {k: Decimal(v) for k, v in (table or {}).items()}
        self.fetched_at = utcnow() - timedelta(seconds=30) if table else None

    async def per_usd(self):
        return self.table


class FakeRates:
    name = "fake"
    ttl_seconds = 60

    def __init__(self, prices):
        self._prices = {k: Decimal(v) for k, v in prices.items()}
        self.fetched_at = utcnow() - timedelta(seconds=10)

    async def prices(self):
        return self._prices


IRAN = {"gold18": "26000000", "coin_emami": "266000000", "silver": "470000"}
WORLD = {"XAU": "4000", "XAG": "50"}
USDT = {"USDT/IRT": "270000", "BTC/USDT": "100000"}


@pytest.fixture
async def make(db):
    opened = []

    async def _make(metals=None, rates=None, fiat=None):
        settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
        app = create_app(
            settings=settings, database=db, limiter=MemoryRateLimiter(),
            rates=FakeRates(USDT if rates is None else rates),
            fiat=fiat or FakeFiat(), metals=metals or FakeMetals(IRAN, WORLD),
        )
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        opened.append((client, context))
        tokens = (await client.post("/api/v1/auth/register", json={
            "display_name": "عماد", "email": "owner@example.com", "password": "a-good-password"})).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        book = (await client.get("/api/v1/books", headers=headers)).json()[0]
        return client, headers, book

    yield _make
    for client, context in opened:
        await context.__aexit__(None, None, None)
        await client.aclose()


async def add(client, headers, book, **body):
    return await client.post(f"/api/v1/books/{book['id']}/portfolio/holdings", headers=headers, json=body)


async def view(client, headers, book):
    return (await client.get(f"/api/v1/books/{book['id']}/portfolio", headers=headers)).json()


# --------------------------------------------------------------- the prices
async def test_every_instrument_is_listed_with_its_price_and_where_it_came_from(make):
    client, headers, _ = await make()

    rows = {row["code"]: row for row in (await client.get("/api/v1/portfolio/instruments", headers=headers)).json()}

    assert Decimal(rows["gold18"]["price"]) == 26_000_000 and rows["gold18"]["price_source"] == "tgju"
    assert rows["gold18"]["exact"] is True
    # An ounce is dollars through the dollar: 4000 * 270000 toman, and it is an estimate.
    assert Decimal(rows["XAU"]["price"]) == 1_080_000_000 and rows["XAU"]["exact"] is False
    assert Decimal(rows["USDT"]["price"]) == 270_000
    assert rows["other"]["price"] is None


async def test_gram_prices_are_estimated_from_the_ounce_when_the_iranian_feed_is_down(make):
    client, headers, _ = await make(metals=FakeMetals(iran={}, world=WORLD))

    rows = {row["code"]: row for row in (await client.get("/api/v1/portfolio/instruments", headers=headers)).json()}

    gram24 = Decimal(rows["gold24"]["price"])
    assert 34_000_000 < gram24 < 35_000_000 and rows["gold24"]["exact"] is False
    assert rows["gold24"]["price_source"] == "world-estimate"
    assert rows["coin_emami"]["price"] is None  # a coin has no estimate, and is not invented


async def test_with_no_feed_at_all_nothing_is_priced_and_nothing_breaks(make):
    client, headers, book = await make(metals=FakeMetals(), rates={})
    await add(client, headers, book, instrument="gold18", quantity="10")

    body = await view(client, headers, book)

    assert body["holdings"][0]["value"] is None and body["unpriced"] == 1
    assert Decimal(body["total_value"]) == 0


# ----------------------------------------------------------------- holdings
async def test_a_holding_is_worth_its_quantity_at_today_s_price(make):
    client, headers, book = await make()

    made = await add(client, headers, book, instrument="coin_emami", quantity="3", cost="700000000")

    assert made.status_code == 201, made.text
    row = made.json()
    assert Decimal(row["price"]) == 266_000_000 and Decimal(row["value"]) == 798_000_000
    assert Decimal(row["profit"]) == 98_000_000 and Decimal(row["profit_percent"]) == Decimal("14.00")


async def test_totals_add_up_and_profit_counts_only_what_has_a_cost(make):
    client, headers, book = await make()
    await add(client, headers, book, instrument="coin_emami", quantity="2", cost="500000000")
    await add(client, headers, book, instrument="gold18", quantity="10")  # no cost: worth, but no profit
    await add(client, headers, book, instrument="USDT", quantity="1000", cost="250000000")

    body = await view(client, headers, book)

    assert Decimal(body["total_value"]) == 532_000_000 + 260_000_000 + 270_000_000
    assert Decimal(body["total_cost"]) == 750_000_000
    assert Decimal(body["total_profit"]) == (532_000_000 - 500_000_000) + (270_000_000 - 250_000_000)
    assert body["unpriced"] == 0


async def test_a_thing_with_no_feed_is_valued_at_the_price_the_person_gives(make):
    client, headers, book = await make()

    made = await add(client, headers, book, instrument="other", label="زمین", quantity="1",
                     unit_price="900000000")

    assert made.status_code == 201, made.text
    assert made.json()["name"] == "زمین" and Decimal(made.json()["value"]) == 900_000_000
    assert (await add(client, headers, book, instrument="other", quantity="1")).status_code == 422


async def test_a_priced_instrument_ignores_a_price_typed_for_it(make):
    client, headers, book = await make()

    made = await add(client, headers, book, instrument="gold18", quantity="1", unit_price="1")

    assert Decimal(made.json()["price"]) == 26_000_000


async def test_an_unknown_instrument_or_a_bad_quantity_is_refused(make):
    client, headers, book = await make()

    assert (await add(client, headers, book, instrument="unobtainium", quantity="1")).status_code == 422
    assert (await add(client, headers, book, instrument="gold18", quantity="0")).status_code == 422


async def test_a_holding_can_be_changed_and_removed(make):
    client, headers, book = await make()
    row = (await add(client, headers, book, instrument="gold18", quantity="10")).json()
    base = f"/api/v1/books/{book['id']}/portfolio/holdings/{row['id']}"

    changed = await client.patch(base, headers=headers, json={"quantity": "12", "cost": "300000000"})

    assert changed.status_code == 200 and Decimal(changed.json()["value"]) == 312_000_000
    assert (await client.delete(base, headers=headers)).status_code == 204
    assert (await view(client, headers, book))["holdings"] == []


async def test_a_book_in_another_currency_sees_the_values_in_it(make):
    client, headers, _ = await make(fiat=FakeFiat({"USD": "1"}))
    shop = (await client.post("/api/v1/books", headers=headers,
                              json={"name": "Shop", "type": "business", "currency": "USD"})).json()

    made = await add(client, headers, shop, instrument="coin_emami", quantity="1")

    # 266,000,000 toman at 270,000 toman to the dollar.
    assert made.status_code == 201, made.text
    assert abs(Decimal(made.json()["value"]) - Decimal("985.1852")) < Decimal("0.01")
    assert (await view(client, headers, shop))["currency"] == "USD"


async def test_a_stranger_sees_nothing_of_the_portfolio(make):
    client, headers, book = await make()
    await add(client, headers, book, instrument="gold18", quantity="10")
    tokens = (await client.post("/api/v1/auth/register", json={
        "display_name": "سارا", "email": "sara@example.com", "password": "a-good-password"})).json()
    theirs = {"Authorization": f"Bearer {tokens['access_token']}"}

    for path in ("", "/notes"):
        assert (await client.get(f"/api/v1/books/{book['id']}/portfolio{path}", headers=theirs)).status_code == 404
    refused = await client.post(f"/api/v1/books/{book['id']}/portfolio/holdings", headers=theirs,
                                json={"instrument": "gold18", "quantity": "1"})
    assert refused.status_code == 404


# -------------------------------------------------------------------- notes
async def note(client, headers, book, title="زمین"):
    made = await client.post(f"/api/v1/books/{book['id']}/portfolio/notes", headers=headers, json={"title": title})
    assert made.status_code == 201, made.text
    return made.json()


async def entry(client, headers, book, n, **body):
    return await client.post(f"/api/v1/books/{book['id']}/portfolio/notes/{n['id']}/entries",
                             headers=headers, json=body)


async def test_a_note_adds_up_what_was_put_in_and_what_it_became(make):
    client, headers, book = await make()
    land = await note(client, headers, book)

    await entry(client, headers, book, land, kind="spent", occurred_on="2026-01-10", amount="500000000", memo="خرید زمین")
    await entry(client, headers, book, land, kind="spent", occurred_on="2026-03-01", amount="50000000", memo="سند و مالیات")
    done = await entry(client, headers, book, land, kind="value", occurred_on="2031-01-10", amount="900000000")

    assert done.status_code == 201, done.text
    body = done.json()
    assert Decimal(body["spent"]) == 550_000_000
    assert Decimal(body["value"]) == 900_000_000 and body["value_on"] == "2031-01-10"
    assert Decimal(body["gain"]) == 350_000_000
    assert [e["kind"] for e in body["entries"]] == ["spent", "spent", "value"]


async def test_the_latest_value_wins_by_date_not_by_when_it_was_typed(make):
    client, headers, book = await make()
    land = await note(client, headers, book)
    await entry(client, headers, book, land, kind="spent", occurred_on="2026-01-10", amount="100")
    await entry(client, headers, book, land, kind="value", occurred_on="2030-01-01", amount="300")
    later = await entry(client, headers, book, land, kind="value", occurred_on="2028-01-01", amount="200")

    assert Decimal(later.json()["value"]) == 300 and later.json()["value_on"] == "2030-01-01"


async def test_a_note_with_no_value_yet_has_no_gain(make):
    client, headers, book = await make()
    land = await note(client, headers, book)

    body = (await entry(client, headers, book, land, kind="spent", occurred_on="2026-01-10", amount="100")).json()

    assert body["value"] is None and body["gain"] is None and Decimal(body["spent"]) == 100


async def test_a_remark_needs_words_and_money_needs_an_amount(make):
    client, headers, book = await make()
    land = await note(client, headers, book)

    assert (await entry(client, headers, book, land, kind="note", occurred_on="2026-01-10")).status_code == 422
    assert (await entry(client, headers, book, land, kind="spent", occurred_on="2026-01-10")).status_code == 422
    assert (await entry(client, headers, book, land, kind="sold", occurred_on="2026-01-10", amount="1")).status_code == 422
    ok = await entry(client, headers, book, land, kind="note", occurred_on="2026-01-10", memo="قول‌نامه امضا شد")
    assert ok.status_code == 201


async def test_an_entry_and_a_note_can_be_removed(make):
    client, headers, book = await make()
    land = await note(client, headers, book)
    made = (await entry(client, headers, book, land, kind="spent", occurred_on="2026-01-10", amount="100")).json()

    gone = await client.delete(
        f"/api/v1/books/{book['id']}/portfolio/notes/{land['id']}/entries/{made['entries'][0]['id']}", headers=headers)

    assert gone.status_code == 200 and gone.json()["entries"] == []
    assert (await client.delete(f"/api/v1/books/{book['id']}/portfolio/notes/{land['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/v1/books/{book['id']}/portfolio/notes", headers=headers)).json() == []


async def test_any_currency_the_app_knows_can_be_held_not_only_the_listed_instruments(make):
    client, headers, book = await make(rates={"USDT/IRT": "270000", "TRX/USDT": "0.2"})

    made = await add(client, headers, book, instrument="TRX", quantity="100")

    assert made.status_code == 201, made.text
    row = made.json()
    assert row["group"] == "crypto" and Decimal(row["value"]) == 5_400_000
    assert (await add(client, headers, book, instrument="ZZZ", quantity="1")).status_code == 422
    # Changing how much of it is held must not trip over it not being in the instrument list.
    base = f"/api/v1/books/{book['id']}/portfolio/holdings/{row['id']}"
    assert (await client.patch(base, headers=headers, json={"quantity": "200"})).status_code == 200


async def test_a_note_and_its_lines_can_be_corrected(make):
    client, headers, book = await make()
    land = await note(client, headers, book)
    made = (await entry(client, headers, book, land, kind="spent", occurred_on="2026-01-10", amount="100")).json()
    root = f"/api/v1/books/{book['id']}/portfolio/notes/{land['id']}"

    renamed = await client.patch(root, headers=headers, json={"title": "زمین شمال"})
    fixed = await client.patch(
        f"{root}/entries/{made['entries'][0]['id']}", headers=headers,
        json={"amount": "250", "occurred_on": "2026-01-12", "memo": "بیعانه"},
    )

    assert renamed.status_code == 200 and renamed.json()["title"] == "زمین شمال"
    assert fixed.status_code == 200, fixed.text
    line = fixed.json()["entries"][0]
    assert Decimal(line["amount"]) == 250 and line["occurred_on"] == "2026-01-12" and line["memo"] == "بیعانه"
    assert Decimal(fixed.json()["spent"]) == 250
    stranger = await client.patch(f"{root}/entries/{made['entries'][0]['id']}", json={"amount": "1"})
    assert stranger.status_code in (401, 403)


async def test_gold_and_coins_are_units_a_book_can_hold_and_are_quoted_in_toman(make):
    client, headers, book = await make()

    quoted = await client.get("/api/v1/market/quotes", headers=headers,
                              params={"base": "IRT", "codes": "GOLD18,EMAMI,XAU"})

    assert quoted.status_code == 200, quoted.text
    rows = {row["code"]: row for row in quoted.json()}
    assert Decimal(rows["GOLD18"]["value"]) == 26_000_000 and rows["GOLD18"]["exact"] is True
    assert Decimal(rows["EMAMI"]["value"]) == 266_000_000
    # The world ounce goes through the dollar, so it is an estimate.
    assert Decimal(rows["XAU"]["value"]) == 4000 * 270_000 and rows["XAU"]["exact"] is False
    ticked = await client.put(f"/api/v1/books/{book['id']}/currencies/GOLD18", headers=headers,
                              json={"enabled": True})
    assert ticked.status_code == 200
    assert any(o["code"] == "GOLD18" and o["enabled"] and o["kind"] == "metal" for o in ticked.json())


async def test_a_book_can_be_renamed_and_its_kind_changed(make):
    client, headers, book = await make()
    base = f"/api/v1/books/{book['id']}"

    changed = await client.patch(base, headers=headers, json={"name": "دفتر من", "type": "business"})

    assert changed.status_code == 200, changed.text
    assert changed.json()["name"] == "دفتر من" and changed.json()["type"] == "business"
    assert (await client.patch(base, headers=headers, json={"type": "spaceship"})).status_code == 422
    assert (await client.patch(base, json={"name": "x"})).status_code in (401, 403)
