"""The currency catalog, the picker's endpoints, and the rule about a book's main unit.

The rule that matters is the last one: every figure in a book is stored in its
base currency, so re-labelling the base of a book with history would not convert
anything, it would silently change what every number means.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.modules.exchange.catalog import BY_CODE, CATALOG, POPULAR
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def signed_in(api, email):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": email, "password": "a-good-password"})).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def new_book(api, headers, currency="IRT"):
    response = await api.post("/api/v1/books", headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": currency})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_the_catalog_is_sane():
    codes = [c.code for c in CATALOG]
    assert len(codes) == len(set(codes))
    # The column that stores a code is 8 characters wide.
    assert max(len(code) for code in codes) <= 8
    kinds = {c.kind for c in CATALOG}
    assert kinds == {"fiat", "crypto", "metal"}
    assert all(code in BY_CODE for code in POPULAR)
    # The old three must survive, and the common world currencies must exist.
    for code in ("IRT", "IRR", "USDT", "TON", "TRX", "USD", "EUR", "GBP", "AED", "TRY", "BTC"):
        assert code in BY_CODE
    assert sum(c.kind == "fiat" for c in CATALOG) > 140


async def test_the_catalog_endpoint_lists_everything_for_a_signed_in_person(api):
    assert (await api.get("/api/v1/currencies")).status_code == 401
    headers = await signed_in(api, "a@example.com")
    rows = (await api.get("/api/v1/currencies", headers=headers)).json()
    assert len(rows) == len(CATALOG)
    usd = next(r for r in rows if r["code"] == "USD")
    assert usd["kind"] == "fiat" and usd["name"] and usd["popular"] is True


async def test_a_book_can_hold_any_catalog_currency_and_not_anything_else(api):
    headers = await signed_in(api, "b@example.com")
    book = await new_book(api, headers)
    options = (await api.get(f"/api/v1/books/{book}/currencies", headers=headers)).json()
    assert len(options) == len(CATALOG)
    assert options[0]["code"] == "IRT" and options[0]["is_base"] is True

    ok = await api.put(f"/api/v1/books/{book}/currencies/AED", headers=headers, json={"enabled": True})
    assert ok.status_code == 200
    assert next(o for o in ok.json() if o["code"] == "AED")["enabled"] is True

    bad = await api.put(f"/api/v1/books/{book}/currencies/ZZZ", headers=headers, json={"enabled": True})
    assert bad.status_code == 422


async def test_creating_a_book_in_an_unknown_currency_is_refused(api):
    headers = await signed_in(api, "c@example.com")
    response = await api.post("/api/v1/books", headers=headers, json={
        "name": "x", "type": "business", "currency": "ZZZ"})
    assert response.status_code == 422


async def test_an_empty_book_can_change_its_main_currency(api):
    headers = await signed_in(api, "d@example.com")
    book = await new_book(api, headers)
    response = await api.put(f"/api/v1/books/{book}/base-currency", headers=headers, json={"code": "usd"})
    assert response.status_code == 200, response.text
    assert response.json()["currency"] == "USD"
    options = (await api.get(f"/api/v1/books/{book}/currencies", headers=headers)).json()
    assert options[0]["code"] == "USD" and options[0]["is_base"] is True


async def test_a_book_with_history_keeps_its_main_currency(api):
    headers = await signed_in(api, "e@example.com")
    book = await new_book(api, headers)
    await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json={
        "flow": "income", "scope": "work", "category": "فروش", "amount": "1000"})
    response = await api.put(f"/api/v1/books/{book}/base-currency", headers=headers, json={"code": "USD"})
    assert response.status_code == 422
    assert "دفتر تازه" in response.json()["detail"]
    got = (await api.get(f"/api/v1/books/{book}", headers=headers)).json()
    assert got["currency"] == "IRT"


async def test_only_the_owner_changes_the_main_currency_and_strangers_see_nothing(api):
    owner = await signed_in(api, "f@example.com")
    stranger = await signed_in(api, "g@example.com")
    book = await new_book(api, owner)
    assert (await api.put(f"/api/v1/books/{book}/base-currency", headers=stranger,
                          json={"code": "USD"})).status_code == 404
    assert (await api.put(f"/api/v1/books/{book}/base-currency", headers=owner,
                          json={"code": "ZZZ"})).status_code == 422
