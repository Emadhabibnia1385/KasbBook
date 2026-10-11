"""Debts over HTTP, and that the API asks the question the bot asks.

Settling a debt is where the two clients most easily drift: the bot shows a
confirmation with two answers, so the API has to offer the same two, with the
same default, or a program and a person settle the same debt differently.
"""

from __future__ import annotations

import pytest

from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.shared.settings import Settings
from tests.test_api_auth import SECRET, bearer, register

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def _book_with_debt(api, headers, direction="owed_to_me"):
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "مغازه", "type": "business"})).json()
    debt = await api.post(f"/api/v1/books/{book['id']}/debts", headers=headers,
                          json={"person": "علی", "amount": "500000", "direction": direction})
    assert debt.status_code == 201, debt.text
    return book, debt.json()


async def _transactions(api, headers, book):
    return (await api.get(f"/api/v1/books/{book['id']}/transactions", headers=headers)).json()["items"]


async def test_settling_over_http_records_no_money_by_default(api):
    headers = bearer(await register(api))
    book, debt = await _book_with_debt(api, headers)

    settled = await api.post(f"/api/v1/books/{book['id']}/debts/{debt['id']}/settle",
                             headers=headers)

    assert settled.status_code == 200 and settled.json()["is_settled"] is True
    assert await _transactions(api, headers, book) == []


async def test_settling_over_http_can_record_the_money_once(api):
    headers = bearer(await register(api))
    book, debt = await _book_with_debt(api, headers, direction="i_owe")
    url = f"/api/v1/books/{book['id']}/debts/{debt['id']}/settle"

    assert (await api.post(url, headers=headers,
                           json={"record_transaction": True})).status_code == 200
    rows = await _transactions(api, headers, book)
    assert [(r["flow"], r["converted_amount"]) for r in rows] == [("expense", "500000.0000")]

    again = await api.post(url, headers=headers, json={"record_transaction": True})
    assert again.status_code == 422
    assert len(await _transactions(api, headers, book)) == 1


async def test_a_debt_of_nothing_is_refused_over_http(api):
    headers = bearer(await register(api))
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "مغازه", "type": "business"})).json()
    response = await api.post(f"/api/v1/books/{book['id']}/debts", headers=headers,
                              json={"person": "علی", "amount": "0", "direction": "i_owe"})
    assert response.status_code == 422


async def test_another_account_cannot_settle_this_debt(api):
    headers = bearer(await register(api))
    book, debt = await _book_with_debt(api, headers)
    stranger = bearer(await register(api, email="other@example.com"))

    response = await api.post(f"/api/v1/books/{book['id']}/debts/{debt['id']}/settle",
                              headers=stranger, json={"record_transaction": True})

    assert response.status_code == 404
    assert await _transactions(api, headers, book) == []
