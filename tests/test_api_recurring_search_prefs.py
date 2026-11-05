"""Recurring rules, search and digest preferences over HTTP.

Each calls the service the bot calls, so these assert the arithmetic and the
refusals the service owns, and that another account can reach none of it.
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


async def _book(api, headers):
    return (await api.post("/api/v1/books", headers=headers,
                           json={"name": "مغازه", "type": "business"})).json()


RULE = {"flow": "expense", "category": "اجاره", "amount": "12000000.5",
        "period": "monthly", "starts_on": "2026-08-25"}


# ------------------------------------------------------------ recurring
async def test_a_rule_can_be_defined_listed_paused_and_deleted(api):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    url = f"/api/v1/books/{book['id']}/recurring"

    created = await api.post(url, headers=headers, json=RULE)
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["amount"] == "12000000.5000"
    assert (rule["period"], rule["next_run_on"], rule["is_active"]) == ("monthly", "2026-08-25", True)

    assert [r["id"] for r in (await api.get(url, headers=headers)).json()] == [rule["id"]]

    paused = await api.post(f"{url}/{rule['id']}/toggle", headers=headers)
    assert paused.json()["is_active"] is False
    resumed = await api.post(f"{url}/{rule['id']}/toggle", headers=headers)
    assert resumed.json()["is_active"] is True

    assert (await api.delete(f"{url}/{rule['id']}", headers=headers)).status_code == 204
    assert (await api.get(url, headers=headers)).json() == []


async def test_defining_a_rule_books_nothing(api):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    await api.post(f"/api/v1/books/{book['id']}/recurring", headers=headers, json=RULE)

    rows = (await api.get(f"/api/v1/books/{book['id']}/transactions", headers=headers)).json()
    assert rows["items"] == []


@pytest.mark.parametrize("patch", [
    {"amount": "0"}, {"period": "yearly"}, {"flow": "gift"}, {"category": ""},
])
async def test_a_malformed_rule_is_refused(api, patch):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    response = await api.post(f"/api/v1/books/{book['id']}/recurring", headers=headers,
                              json={**RULE, **patch})
    assert response.status_code == 422


async def test_another_account_cannot_see_or_touch_a_rule(api):
    owner = bearer(await register(api))
    stranger = bearer(await register(api, email="other@example.com"))
    book = await _book(api, owner)
    url = f"/api/v1/books/{book['id']}/recurring"
    rule = (await api.post(url, headers=owner, json=RULE)).json()

    assert (await api.get(url, headers=stranger)).status_code == 404
    assert (await api.post(url, headers=stranger, json=RULE)).status_code == 404
    assert (await api.post(f"{url}/{rule['id']}/toggle", headers=stranger)).status_code == 404
    assert (await api.delete(f"{url}/{rule['id']}", headers=stranger)).status_code == 404
    assert (await api.get(url, headers=owner)).json()[0]["is_active"] is True


async def test_a_rule_is_not_reachable_through_another_book(api):
    headers = bearer(await register(api))
    first, second = await _book(api, headers), await _book(api, headers)
    rule = (await api.post(f"/api/v1/books/{first['id']}/recurring", headers=headers,
                           json=RULE)).json()

    response = await api.delete(f"/api/v1/books/{second['id']}/recurring/{rule['id']}",
                                headers=headers)
    assert response.status_code == 404


# --------------------------------------------------------------- search
async def _earn(api, headers, book, category, amount, description=None):
    response = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers, json={
        "flow": "income", "category": category, "amount": amount,
        "occurred_on": "2026-08-25", "description": description,
    })
    assert response.status_code == 201, response.text


async def test_search_finds_by_category_or_description_and_totals_every_match(api):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    await _earn(api, headers, book, "فروش", "100")
    await _earn(api, headers, book, "فروش", "250")
    await _earn(api, headers, book, "متفرقه", "40", description="فروش نقدی")
    await _earn(api, headers, book, "اجاره", "999")
    url = f"/api/v1/books/{book['id']}/reports/search"

    page = (await api.get(url, headers=headers, params={"q": "فروش", "per_page": 2})).json()

    assert page["total"] == 3 and len(page["items"]) == 2
    # The sum covers all three matches although only two are on the page.
    assert page["total_amount"] == "390.0000"
    rest = (await api.get(url, headers=headers, params={"q": "فروش", "per_page": 2, "page": 2})).json()
    assert len(rest["items"]) == 1


async def test_search_treats_percent_as_a_character_not_a_wildcard(api):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    await _earn(api, headers, book, "تخفیف", "5", description="50% off")
    await _earn(api, headers, book, "تخفیف", "7", description="500 units")

    page = (await api.get(f"/api/v1/books/{book['id']}/reports/search", headers=headers,
                          params={"q": "50%"})).json()
    assert page["total"] == 1


async def test_a_one_character_search_matches_nothing(api):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    await _earn(api, headers, book, "فروش", "100")

    page = (await api.get(f"/api/v1/books/{book['id']}/reports/search", headers=headers,
                          params={"q": "ف"})).json()
    assert page["items"] == [] and page["total"] == 0 and page["total_amount"] == "0.0000"


async def test_search_never_crosses_into_another_account(api):
    owner = bearer(await register(api))
    stranger = bearer(await register(api, email="other@example.com"))
    book = await _book(api, owner)
    await _earn(api, owner, book, "فروش", "100")
    url = f"/api/v1/books/{book['id']}/reports/search"

    assert (await api.get(url, headers=stranger, params={"q": "فروش"})).status_code == 404

    mine = await _book(api, stranger)
    page = (await api.get(f"/api/v1/books/{mine['id']}/reports/search", headers=stranger,
                          params={"q": "فروش"})).json()
    assert page["total"] == 0


# ---------------------------------------------------------- preferences
async def test_digest_preferences_can_be_set_and_read_back(api):
    headers = bearer(await register(api))
    before = (await api.get("/api/v1/auth/me", headers=headers)).json()
    assert before["digest_enabled"] is True

    response = await api.patch("/api/v1/auth/me", headers=headers, json={
        "digest_enabled": False, "digest_hour": 8, "reminder_days": 0,
    })
    assert response.status_code == 200, response.text
    after = (await api.get("/api/v1/auth/me", headers=headers)).json()
    assert (after["digest_enabled"], after["digest_hour"], after["reminder_days"]) == (False, 8, 0)
    # An untouched field stays untouched.
    assert after["display_name"] == before["display_name"]


@pytest.mark.parametrize("body", [
    {"digest_hour": 24}, {"digest_hour": -1}, {"reminder_days": 61}, {"reminder_days": -3},
])
async def test_out_of_range_preferences_are_refused_and_change_nothing(api, body):
    headers = bearer(await register(api))
    before = (await api.get("/api/v1/auth/me", headers=headers)).json()

    assert (await api.patch("/api/v1/auth/me", headers=headers, json=body)).status_code == 422
    assert (await api.get("/api/v1/auth/me", headers=headers)).json() == before


async def test_preferences_belong_to_one_account(api):
    first = bearer(await register(api))
    second = bearer(await register(api, email="other@example.com"))
    await api.patch("/api/v1/auth/me", headers=first, json={"digest_hour": 5})

    assert (await api.get("/api/v1/auth/me", headers=second)).json()["digest_hour"] == 21
