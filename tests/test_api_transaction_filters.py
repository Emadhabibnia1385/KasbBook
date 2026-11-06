"""Narrowing the transaction list: income or expense, several categories, words, dates, together.

The totals are the point of a filter someone reads money from, so they are asserted too: they must
cover every match, not only the page being shown.
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


async def seeded(api):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "f@example.com", "password": "a-good-password"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    book = (await api.post("/api/v1/books", headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": "IRT"})).json()["id"]
    rows = [
        ("income", "فروش", "1000", "2026-11-01", "مشتری اول"),
        ("expense", "اجاره", "300", "2026-11-02", "ماه آبان"),
        ("expense", "حمل", "50", "2026-11-03", "پست پیشتاز"),
        ("expense", "اجاره", "300", "2026-10-02", "ماه مهر"),
        ("income", "فروش", "700", "2026-10-05", "50% تخفیف"),
    ]
    for flow, category, amount, day, note in rows:
        response = await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json={
            "flow": flow, "scope": "work", "category": category, "amount": amount,
            "occurred_on": day, "description": note})
        assert response.status_code == 201, response.text
    return headers, book


async def ask(api, headers, book, query):
    response = await api.get(f"/api/v1/books/{book}/transactions?{query}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_income_only_and_expense_only(api):
    headers, book = await seeded(api)
    income = await ask(api, headers, book, "flow=income")
    assert income["total"] == 2 and income["total_income"] == "1700.0000" and income["total_expense"] == "0.0000"
    both = await ask(api, headers, book, "flow=income&flow=expense")
    assert both["total"] == 5


async def test_several_categories_are_alternatives(api):
    headers, book = await seeded(api)
    page = await ask(api, headers, book, "category=%D8%A7%D8%AC%D8%A7%D8%B1%D9%87&category=%D8%AD%D9%85%D9%84")
    assert page["total"] == 3
    assert {row["category"] for row in page["items"]} == {"اجاره", "حمل"}
    assert page["total_expense"] == "650.0000"


async def test_the_kinds_of_filter_all_have_to_hold(api):
    headers, book = await seeded(api)
    page = await ask(api, headers, book, "flow=expense&category=%D8%A7%D8%AC%D8%A7%D8%B1%D9%87&since=2026-11-01&until=2026-11-30")
    assert page["total"] == 1 and page["items"][0]["description"] == "ماه آبان"


async def test_words_match_the_note_and_the_category_and_percent_is_literal(api):
    headers, book = await seeded(api)
    assert (await ask(api, headers, book, "q=%D9%BE%D8%B3%D8%AA"))["total"] == 1
    assert (await ask(api, headers, book, "q=%D9%81%D8%B1%D9%88%D8%B4"))["total"] == 2
    assert (await ask(api, headers, book, "q=50%25"))["total"] == 1
    # One character means nothing: it must not match the whole book.
    assert (await ask(api, headers, book, "q=%D9%85"))["total"] == 5


async def test_totals_cover_every_match_not_only_the_page(api):
    headers, book = await seeded(api)
    page = await ask(api, headers, book, "per_page=1")
    assert len(page["items"]) == 1 and page["total"] == 5
    assert page["total_income"] == "1700.0000" and page["total_expense"] == "650.0000"


async def test_a_bad_flow_is_refused_and_a_stranger_sees_nothing(api):
    headers, book = await seeded(api)
    assert (await api.get(f"/api/v1/books/{book}/transactions?flow=sideways", headers=headers)).status_code == 422
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "غریبه", "email": "x@example.com", "password": "a-good-password"})).json()
    other = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await api.get(f"/api/v1/books/{book}/transactions?flow=income", headers=other)).status_code == 404


async def test_the_list_can_be_sorted_by_amount_category_and_age(api):
    headers, book = await seeded(api)
    order = lambda page: [row["description"] for row in page["items"]]
    newest = await ask(api, headers, book, "sort=newest")
    oldest = await ask(api, headers, book, "sort=oldest")
    assert order(newest) == list(reversed(order(oldest)))
    assert newest["items"][0]["occurred_on"] == "2026-11-03"
    big = await ask(api, headers, book, "sort=amount_desc")
    assert [row["converted_amount"] for row in big["items"]][:2] == ["1000.0000", "700.0000"]
    small = await ask(api, headers, book, "sort=amount_asc")
    assert small["items"][0]["converted_amount"] == "50.0000"
    by_category = await ask(api, headers, book, "sort=category")
    names = [row["category"] for row in by_category["items"]]
    assert names == sorted(names, key=str.casefold)
    assert (await api.get(f"/api/v1/books/{book}/transactions?sort=sideways", headers=headers)).status_code == 422


async def test_amounts_sort_as_numbers_not_as_text(api):
    headers, book = await seeded(api)
    await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json={
        "flow": "expense", "scope": "work", "category": "تست", "amount": "9", "occurred_on": "2026-11-04"})
    small = await ask(api, headers, book, "sort=amount_asc")
    assert [row["converted_amount"] for row in small["items"]][:2] == ["9.0000", "50.0000"]
