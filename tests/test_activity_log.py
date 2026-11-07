"""«رویدادها»: who did what, when, and through what; and who may read it."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.modules.activity.models import ActivityEvent
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


async def sign_up(api, email, name="عماد"):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": name, "email": email, "password": "a-good-password"})).json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


async def new_book(api, headers, kind="business"):
    return (await api.post("/api/v1/books", headers=headers, json={
        "name": "کارگاه", "type": kind, "currency": "IRT"})).json()["id"]


async def record(api, headers, book, **body):
    body = {"scope": "work", "category": "فروش", "flow": "income", "amount": "1300000", **body}
    response = await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def events(api, headers, **params):
    response = await api.get("/api/v1/activity", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_recording_editing_and_deleting_are_each_one_line_with_who_and_how(api):
    _, headers = await sign_up(api, "a@example.com")
    book = await new_book(api, headers)
    tx = await record(api, headers, book)
    await api.patch(f"/api/v1/books/{book}/transactions/{tx['id']}", headers=headers,
                    json={"amount": "1400000"})
    await api.delete(f"/api/v1/books/{book}/transactions/{tx['id']}", headers=headers)

    page = await events(api, headers, category="transactions")

    sentences = [item["summary"] for item in page["items"]]
    assert page["total"] == 3
    assert any(s.startswith("ثبت درآمد") and "1,300,000" in s and "فروش" in s for s in sentences)
    assert any(s.startswith("ویرایش درآمد") and "مبلغ" in s for s in sentences)
    assert any(s.startswith("حذف درآمد") for s in sentences)
    first = page["items"][0]
    assert first["is_me"] is True and first["via"] == "web" and first["book_name"] == "کارگاه"
    assert first["category_label"] == "تراکنش‌ها" and first["at"]


async def test_an_api_key_is_told_apart_from_the_person(api):
    tokens, headers = await sign_up(api, "k@example.com")
    book = await new_book(api, headers)
    key = (await api.post("/api/v1/auth/api-keys", headers=headers, json={"name": "sync"})).json()["key"]
    await record(api, {"X-API-Key": key}, book, amount="900000")

    by_key = await events(api, headers, via="api", category="transactions")

    assert by_key["total"] == 1
    assert by_key["items"][0]["via_label"] == "API" and by_key["items"][0]["is_me"] is True
    assert "900,000" in by_key["items"][0]["summary"]


async def test_filters_search_and_the_summary_agree(api):
    _, headers = await sign_up(api, "f@example.com")
    book = await new_book(api, headers)
    await record(api, headers, book, category="اجاره", flow="expense", amount="500000")
    await record(api, headers, book, category="فروش")
    await api.post(f"/api/v1/books/{book}/categories", headers=headers, json={"name": "هدیه", "flow": "income"})

    assert (await events(api, headers, q="اجاره"))["total"] >= 1
    assert all("اجاره" in item["summary"] for item in (await events(api, headers, q="اجاره"))["items"])
    cats = {row["key"]: row["count"] for row in (await api.get(
        "/api/v1/activity/summary", headers=headers)).json()["by_category"]}
    assert cats["transactions"] == 2 and cats["categories"] >= 1
    summary = (await api.get("/api/v1/activity/summary", headers=headers)).json()
    assert summary["total"] == (await events(api, headers))["total"]
    assert len(summary["by_day"]) == 30
    assert sum(day["count"] for day in summary["by_day"]) == summary["total"]
    options = (await api.get("/api/v1/activity/options", headers=headers)).json()
    assert {o["key"] for o in options["categories"]} >= {"transactions", "payroll"}
    assert "کارگاه" in {b["name"] for b in options["books"]}


async def test_the_log_is_a_spreadsheet_too(api):
    _, headers = await sign_up(api, "c@example.com")
    book = await new_book(api, headers)
    await record(api, headers, book)

    out = await api.get("/api/v1/activity/export.csv", headers=headers, params={"category": "transactions"})

    assert out.status_code == 200 and out.headers["content-type"].startswith("text/csv")
    text = out.content.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("چه کسی,از راه,تاریخ,ساعت,گروه,دفتر,عملیات")
    assert len(lines) == 2 and "ثبت درآمد" in lines[1] and "تو,پنل" in lines[1]


async def test_a_stranger_sees_none_of_it_and_an_owner_sees_the_books_members(api):
    _, owner = await sign_up(api, "o@example.com", "مدیر")
    _, other = await sign_up(api, "x@example.com", "غریبه")
    book = await new_book(api, owner, "team")
    await record(api, owner, book)

    seen_by_other = [i for i in (await events(api, other))["items"] if i["book_id"] == book]
    assert seen_by_other == []
    assert any(i["book_id"] == book for i in (await events(api, owner))["items"])
    # Someone else's id as a filter shows nothing of theirs that this person may not see.
    me = (await api.get("/api/v1/auth/me", headers=owner)).json()["id"]
    assert (await events(api, other, who=me))["total"] == 0


async def test_signing_in_and_out_are_logged_and_the_demo_is_not_noise(api, db):
    tokens, headers = await sign_up(api, "s@example.com")
    await api.post("/api/v1/auth/login", json={"identifier": "s@example.com", "password": "a-good-password"})
    await api.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    login_again = (await api.post("/api/v1/auth/login", json={
        "identifier": "s@example.com", "password": "a-good-password"})).json()
    headers = {"Authorization": f"Bearer {login_again['access_token']}"}

    page = await events(api, headers, category="account")
    assert {i["summary"] for i in page["items"]} >= {"ساخت حساب", "ورود به حساب", "خروج از حساب"}

    await api.post("/api/v1/auth/demo")
    async for session in db.session():
        total = (await session.execute(select(func.count(ActivityEvent.id)))).scalar_one()
        assert total < 20  # a demo of a thousand rows left no thousand lines
