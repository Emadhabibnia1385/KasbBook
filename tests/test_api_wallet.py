"""Currencies and conversions over HTTP, through the same service the bot uses."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"
DAY = "2026-08-24"


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with app.router.lifespan_context(app):
            yield client


async def workspace(api):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "owner@example.com",
        "password": "a-good-password",
    })).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "کارگاه", "type": "business",
                                 "currency": "IRT"})).json()
    return headers, book


async def test_currencies_start_at_the_base_one_and_can_be_ticked(api, db):
    headers, book = await workspace(api)

    listing = (await api.get(f"/api/v1/books/{book['id']}/currencies",
                             headers=headers)).json()
    base = [c for c in listing if c["is_base"]]
    assert len(base) == 1
    assert all(not c["enabled"] for c in listing if not c["is_base"])

    updated = (await api.put(f"/api/v1/books/{book['id']}/currencies/USDT",
                             headers=headers, json={"enabled": True})).json()
    assert [c for c in updated if c["code"] == "USDT"][0]["enabled"] is True


async def test_an_unsupported_currency_is_refused(api, db):
    headers, book = await workspace(api)
    reply = await api.put(f"/api/v1/books/{book['id']}/currencies/DOGE",
                          headers=headers, json={"enabled": True})
    assert reply.status_code == 422


async def test_the_wallet_reports_each_currency_as_a_string(api, db):
    headers, book = await workspace(api)
    await api.put(f"/api/v1/books/{book['id']}/currencies/USDT",
                  headers=headers, json={"enabled": True})
    await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers,
                   json={"flow": "income", "category": "فروش", "amount": "12.5",
                         "currency": "USDT", "conversion_rate": "228389",
                         "occurred_on": DAY})

    wallet = (await api.get(f"/api/v1/books/{book['id']}/wallet",
                            headers=headers)).json()
    usdt = [b for b in wallet if b["code"] == "USDT"][0]
    # A string, not a float: 12.5 tethers must survive the round trip exactly.
    assert usdt["amount"] == "12.5000"
    assert usdt["name"] == "تتر"


async def test_a_conversion_moves_the_balances_over_http(api, db):
    headers, book = await workspace(api)
    await api.put(f"/api/v1/books/{book['id']}/currencies/USDT",
                  headers=headers, json={"enabled": True})
    await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers,
                   json={"flow": "income", "category": "فروش", "amount": "100",
                         "currency": "USDT", "conversion_rate": "228389",
                         "occurred_on": DAY})

    created = await api.post(f"/api/v1/books/{book['id']}/conversions", headers=headers,
                             json={"from_currency": "USDT", "from_amount": "40",
                                   "to_currency": "IRT", "to_amount": "9135560",
                                   "occurred_on": DAY})
    assert created.status_code == 201
    assert created.json()["base_value"] == "9135560.0000"

    wallet = {b["code"]: b["amount"] for b in
              (await api.get(f"/api/v1/books/{book['id']}/wallet", headers=headers)).json()}
    assert wallet["USDT"] == "60.0000"
    assert wallet["IRT"] == "9135560.0000"

    listed = (await api.get(f"/api/v1/books/{book['id']}/conversions",
                            headers=headers)).json()
    assert len(listed) == 1


async def test_spending_a_token_the_book_does_not_hold_is_refused_over_http(api, db):
    headers, book = await workspace(api)
    await api.put(f"/api/v1/books/{book['id']}/currencies/USDT",
                  headers=headers, json={"enabled": True})

    reply = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers,
                           json={"flow": "expense", "category": "سرور", "amount": "5",
                                 "currency": "USDT", "conversion_rate": "228389",
                         "occurred_on": DAY})
    assert reply.status_code == 422
    wallet = {b["code"]: b["amount"] for b in
              (await api.get(f"/api/v1/books/{book['id']}/wallet", headers=headers)).json()}
    assert wallet["USDT"] == "0.0000"


async def test_another_account_cannot_reach_this_wallet(api, db):
    headers, book = await workspace(api)
    other = (await api.post("/api/v1/auth/register", json={
        "display_name": "غریبه", "email": "stranger@example.com",
        "password": "a-good-password",
    })).json()
    theirs = {"Authorization": f"Bearer {other['access_token']}"}

    # 404, never 403: answering differently would confirm the book exists.
    assert (await api.get(f"/api/v1/books/{book['id']}/wallet",
                          headers=theirs)).status_code == 404
    assert (await api.put(f"/api/v1/books/{book['id']}/currencies/USDT",
                          headers=theirs, json={"enabled": True})).status_code == 404


async def test_the_api_can_post_to_a_book_the_bot_created(api, session):
    """Both clients, one book. This was broken and nothing said so.

    `BookRequest.currency` defaulted to "IRR" while `create_book` defaults to
    "IRT", so a book made in the bot refused every plain transaction posted to
    it over HTTP — with an error about currencies, for a request that never
    mentioned one.
    """
    import uuid as _uuid

    from kasbbook.modules.books.models import BookType
    from kasbbook.modules.books.service import BookService

    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "both@example.com",
        "password": "a-good-password",
    })).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = (await api.get("/api/v1/auth/me", headers=headers)).json()

    book = await BookService(session).create_book(
        _uuid.UUID(me["id"]), "دفتر ربات", BookType.BUSINESS
    )
    await session.commit()

    reply = await api.post(f"/api/v1/books/{book.id}/transactions", headers=headers,
                           json={"flow": "income", "category": "فروش",
                                 "amount": "250000", "occurred_on": DAY})
    assert reply.status_code == 201
    assert reply.json()["original_currency"] == "IRT"


async def test_a_book_made_over_http_counts_in_the_same_currency_as_one_made_in_the_bot(api, db):
    headers, _ = await workspace(api)
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "بی‌ارز", "type": "business"})).json()
    wallet = (await api.get(f"/api/v1/books/{book['id']}/wallet", headers=headers)).json()
    assert [b["code"] for b in wallet] == ["IRT"]


async def test_a_transaction_date_can_be_corrected_over_http(api, db):
    headers, book = await workspace(api)
    tx = (await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers,
                         json={"flow": "income", "category": "فروش", "amount": "1000000",
                               "occurred_on": "2026-10-20"})).json()
    assert tx["occurred_on"] == "2026-10-20"

    fixed = await api.patch(
        f"/api/v1/books/{book['id']}/transactions/{tx['id']}",
        headers=headers, json={"occurred_on": "2026-09-19"},
    )
    assert fixed.status_code == 200
    assert fixed.json()["occurred_on"] == "2026-09-19"
    assert fixed.json()["converted_amount"] == "1000000.0000"
