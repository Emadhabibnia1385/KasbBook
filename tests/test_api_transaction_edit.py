"""Editing everything an entry has: its kind, its currency and rate as well as its amount, category, day and note.

A rewrite takes its effect out of the old currency and puts it into the new one, so the properties worth
proving are about the wallets: neither side may go below zero, the books must stay balanced, and a
stranger must not reach any of it.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
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


async def book_with(api, email="e@example.com", enable=("TON", "USDT")):
    headers = await signed_in(api, email)
    book = (await api.post("/api/v1/books", headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": "IRT"})).json()["id"]
    for code in enable:
        await api.put(f"/api/v1/books/{book}/currencies/{code}", headers=headers, json={"enabled": True})
    return headers, book


async def add(api, headers, book, **body):
    body = {"scope": "work", "category": "فروش", **body}
    response = await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def edit(api, headers, book, tx, **body):
    return await api.patch(f"/api/v1/books/{book}/transactions/{tx}", headers=headers, json=body)


async def balances(api, headers, book):
    rows = (await api.get(f"/api/v1/books/{book}/wallet", headers=headers)).json()
    return {r["code"]: r["amount"] for r in rows}


async def test_the_currency_and_rate_of_an_entry_can_be_changed(api):
    headers, book = await book_with(api)
    tx = await add(api, headers, book, flow="income", amount="10", currency="TON", conversion_rate="300000")
    assert tx["converted_amount"] == "3000000.0000"

    done = await edit(api, headers, book, tx["id"], currency="USDT", conversion_rate="270000")
    assert done.status_code == 200, done.text
    row = done.json()
    assert row["original_currency"] == "USDT" and row["converted_amount"] == "2700000.0000"
    held = await balances(api, headers, book)
    assert held["USDT"] == "10.0000" and held["TON"] == "0.0000"


async def test_a_rate_alone_changes_the_value_and_not_the_holding(api):
    headers, book = await book_with(api)
    tx = await add(api, headers, book, flow="income", amount="10", currency="TON", conversion_rate="300000")
    done = await edit(api, headers, book, tx["id"], conversion_rate="310000")
    assert done.status_code == 200 and done.json()["converted_amount"] == "3100000.0000"
    assert (await balances(api, headers, book))["TON"] == "10.0000"


async def test_the_kind_of_an_entry_can_be_changed_and_the_summary_follows(api):
    headers, book = await book_with(api)
    tx = await add(api, headers, book, flow="income", amount="500", category="فروش")
    done = await edit(api, headers, book, tx["id"], flow="expense", category="اجاره")
    assert done.status_code == 200, done.text
    summary = (await api.get(f"/api/v1/books/{book}/reports/summary", headers=headers)).json()
    assert summary["income"] == "0.0000" and summary["expense"] == "500.0000"
    # A category of the old kind is refused for the new one: the entry would sit under the wrong heading.
    other = await add(api, headers, book, flow="expense", amount="5", category="حمل")
    bad = await edit(api, headers, book, other["id"], flow="income")
    assert bad.status_code == 422


async def test_a_change_that_would_leave_a_wallet_negative_is_refused_on_either_side(api):
    headers, book = await book_with(api)
    income = await add(api, headers, book, flow="income", amount="10", currency="TON", conversion_rate="300000")
    await add(api, headers, book, flow="expense", amount="8", currency="TON", conversion_rate="300000", category="اجاره")
    # The income cannot move away from TON while 8 of it were spent.
    moved = await edit(api, headers, book, income["id"], currency="USDT", conversion_rate="270000")
    assert moved.status_code == 422
    # Nor shrink below what was spent.
    shrunk = await edit(api, headers, book, income["id"], amount="5")
    assert shrunk.status_code == 422
    # An expense cannot move to a currency that is not held.
    spend = await add(api, headers, book, flow="expense", amount="1", currency="TON", conversion_rate="300000", category="حمل")
    bad = await edit(api, headers, book, spend["id"], currency="USDT", conversion_rate="270000")
    assert bad.status_code == 422
    assert (await balances(api, headers, book))["TON"] == "1.0000"


async def test_a_new_currency_needs_a_rate_and_must_be_one_the_book_holds(api):
    headers, book = await book_with(api, enable=("TON",))
    tx = await add(api, headers, book, flow="income", amount="10", currency="TON", conversion_rate="300000")
    assert (await edit(api, headers, book, tx["id"], currency="TON", amount="11")).status_code == 200
    # Back to the book's own currency needs no rate.
    home = await edit(api, headers, book, tx["id"], currency="IRT")
    assert home.status_code == 200 and home.json()["converted_amount"] == "11.0000"
    # A currency the book never ticked is refused, and so is one with no rate.
    assert (await edit(api, headers, book, tx["id"], currency="USDT", conversion_rate="1")).status_code == 422
    assert (await edit(api, headers, book, tx["id"], currency="TON")).status_code == 422


async def test_a_stranger_cannot_edit_and_a_null_core_field_is_refused(api):
    headers, book = await book_with(api)
    tx = await add(api, headers, book, flow="income", amount="10")
    stranger = await signed_in(api, "s@example.com")
    assert (await edit(api, stranger, book, tx["id"], currency="TON", conversion_rate="1")).status_code == 404
    assert (await edit(api, headers, book, tx["id"], flow=None)).status_code == 422


async def test_the_list_can_be_filtered_by_the_money_it_was_paid_in(api):
    headers, book = await book_with(api)
    await add(api, headers, book, flow="income", amount="1000")
    await add(api, headers, book, flow="income", amount="10", currency="TON", conversion_rate="300000")
    await add(api, headers, book, flow="income", amount="7", currency="USDT", conversion_rate="270000")
    only = (await api.get(f"/api/v1/books/{book}/transactions?currency=ton", headers=headers)).json()
    assert only["total"] == 1 and only["items"][0]["original_currency"] == "TON"
    two = (await api.get(f"/api/v1/books/{book}/transactions?currency=TON&currency=IRT", headers=headers)).json()
    assert two["total"] == 2
