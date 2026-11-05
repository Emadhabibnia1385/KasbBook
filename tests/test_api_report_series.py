"""The series behind the web dashboard's charts.

They exist for a picture, so what is asserted is the figures a picture would
mislead with: months with nothing in them still appear, an old transaction
outside the window is left out, and a stranger sees a 404 and not an empty
chart.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.shared import jalali
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


async def add(api, headers, book, flow, amount, on):
    response = await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json={
        "flow": flow, "scope": "work", "category": "فروش" if flow == "income" else "اجاره",
        "amount": amount, "occurred_on": on.isoformat()})
    assert response.status_code == 201, response.text


async def test_monthly_fills_empty_months_and_keeps_money_exact(api):
    headers = await signed_in(api, "a@example.com")
    book = (await api.post("/api/v1/books", headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": "IRT"})).json()["id"]
    today = dt.date.today()
    await add(api, headers, book, "income", "1000.50", today)
    await add(api, headers, book, "expense", "400", today)
    # Far outside a three-month window.
    await add(api, headers, book, "income", "999", today - dt.timedelta(days=400))

    rows = (await api.get(f"/api/v1/books/{book}/reports/monthly?months=3", headers=headers)).json()

    assert len(rows) == 3
    y, m, _ = jalali.to_parts(today)
    assert rows[-1]["period"] == f"{y}-{m:02d}"
    assert (rows[-1]["income"], rows[-1]["expense"], rows[-1]["net"]) == ("1000.5000", "400.0000", "600.5000")
    assert rows[0]["income"] == "0.0000" and rows[0]["transaction_count"] == 0


async def test_daily_lists_only_days_with_activity(api):
    headers = await signed_in(api, "b@example.com")
    book = (await api.post("/api/v1/books", headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": "IRT"})).json()["id"]
    today = dt.date.today()
    y, m, _ = jalali.to_parts(today)
    await add(api, headers, book, "expense", "250", today)

    rows = (await api.get(f"/api/v1/books/{book}/reports/daily?period={y}-{m:02d}", headers=headers)).json()

    assert rows == [{"on": today.isoformat(), "income": "0.0000", "expense": "250.0000"}]


async def test_a_stranger_gets_not_found_for_both_series(api):
    owner = await signed_in(api, "c@example.com")
    stranger = await signed_in(api, "d@example.com")
    book = (await api.post("/api/v1/books", headers=owner, json={
        "name": "کارگاه", "type": "business", "currency": "IRT"})).json()["id"]

    assert (await api.get(f"/api/v1/books/{book}/reports/monthly", headers=stranger)).status_code == 404
    assert (await api.get(f"/api/v1/books/{book}/reports/daily?period=week", headers=stranger)).status_code == 404
