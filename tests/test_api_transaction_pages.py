"""Pages of the all-books list that never cut a day in two.

A shop reads its takings a day at a time; half a day on one page and half on the next means adding
two screens to know what Tuesday made. `whole_days` makes `per_page` a target, and these tests pin
what that means at its edges: a day that does not fit moves over whole, a day bigger than the page
gets a page of its own, and a sort that scatters the days is left to plain slicing.
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


# Three entries on the 3rd, one on the 2nd, two on the 1st.
DAYS = ["2026-11-03"] * 3 + ["2026-11-02"] + ["2026-11-01"] * 2


async def seeded(api):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "p@example.com", "password": "a-good-password"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    book = (await api.post("/api/v1/books", headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": "IRT"})).json()["id"]
    for index, day in enumerate(DAYS):
        response = await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json={
            "flow": "expense", "scope": "work", "category": "حمل", "amount": str(10 + index),
            "occurred_on": day, "description": f"n{index}"})
        assert response.status_code == 201, response.text
    return headers


async def pages(api, headers, per_page, **extra):
    """Every page's days, walked from the first until the server says it is the last."""
    found, number = [], 1
    while True:
        response = await api.get("/api/v1/transactions", headers=headers, params={
            "per_page": per_page, "page": number, "whole_days": "true", **extra})
        assert response.status_code == 200, response.text
        body = response.json()
        found.append([row["occurred_on"] for row in body["items"]])
        if number >= body["page_count"]:
            return found, body
        number += 1


async def test_a_day_that_does_not_fit_moves_to_the_next_page_whole(api):
    headers = await seeded(api)
    found, body = await pages(api, headers, per_page=4)
    # 3 on the 3rd, then the 2nd would make 4 (fits), then the 1st's two would make 6: next page.
    assert found == [["2026-11-03"] * 3 + ["2026-11-02"], ["2026-11-01"] * 2]
    assert body["page_count"] == 2 and body["total"] == 6


async def test_a_day_bigger_than_the_page_gets_a_page_of_its_own(api):
    headers = await seeded(api)
    found, _ = await pages(api, headers, per_page=2)
    assert found == [["2026-11-03"] * 3, ["2026-11-02"], ["2026-11-01"] * 2]
    # Never a day on two pages, whatever the size asked for.
    for size in range(1, 8):
        found, _ = await pages(api, headers, per_page=size)
        seen = [day for page in found for day in set(page)]
        assert len(seen) == len(set(seen)), (size, found)
        assert sum(len(page) for page in found) == 6


async def test_a_page_size_above_the_total_shows_everything_on_one_page(api):
    headers = await seeded(api)
    found, body = await pages(api, headers, per_page=1000)
    assert len(found) == 1 and len(found[0]) == 6 and body["page_count"] == 1


async def test_oldest_first_cuts_on_day_boundaries_too(api):
    headers = await seeded(api)
    found, _ = await pages(api, headers, per_page=3, sort="oldest")
    assert found == [["2026-11-01"] * 2 + ["2026-11-02"], ["2026-11-03"] * 3]
    for page in found:
        assert page == sorted(page)


async def test_without_whole_days_the_pages_are_plain_slices(api):
    headers = await seeded(api)
    response = await api.get("/api/v1/transactions", headers=headers, params={"per_page": 2, "page": 2})
    body = response.json()
    assert len(body["items"]) == 2 and body["page_count"] == 3


async def test_sorted_by_amount_the_days_are_scattered_so_pages_stay_plain(api):
    headers = await seeded(api)
    response = await api.get("/api/v1/transactions", headers=headers, params={
        "per_page": 4, "whole_days": "true", "sort": "amount_desc"})
    body = response.json()
    assert len(body["items"]) == 4 and body["page_count"] == 2


async def test_a_page_past_the_end_is_empty_not_an_error(api):
    headers = await seeded(api)
    response = await api.get("/api/v1/transactions", headers=headers, params={
        "per_page": 4, "page": 9, "whole_days": "true"})
    assert response.status_code == 200 and response.json()["items"] == []


async def test_the_largest_page_size_loads_and_one_more_is_refused(api):
    headers = await seeded(api)
    top = await api.get("/api/v1/transactions", headers=headers, params={
        "per_page": 10000, "whole_days": "true"})
    assert top.status_code == 200 and len(top.json()["items"]) == 6
    over = await api.get("/api/v1/transactions", headers=headers, params={"per_page": 10001})
    assert over.status_code == 422
