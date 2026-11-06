"""One list across every book, and moving an entry recorded in the wrong book to the right one."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a3e1ba3e0000000049454e44ae426082")


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


async def make_book(api, headers, name, currency="IRT", enable=()):
    book = (await api.post("/api/v1/books", headers=headers, json={
        "name": name, "type": "business", "currency": currency})).json()["id"]
    for code in enable:
        await api.put(f"/api/v1/books/{book}/currencies/{code}", headers=headers, json={"enabled": True})
    return book


async def add(api, headers, book, **body):
    body = {"scope": "work", "category": "فروش", **body}
    response = await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_the_list_spans_every_book_and_can_be_narrowed_to_some(api):
    headers = await signed_in(api, "a@example.com")
    shop = await make_book(api, headers, "مغازه")
    home = await make_book(api, headers, "خانه")
    await add(api, headers, shop, amount="1000", flow="income", occurred_on="2026-01-02")
    await add(api, headers, home, amount="300", flow="expense", category="اجاره", occurred_on="2026-01-03")

    page = (await api.get("/api/v1/transactions", headers=headers)).json()
    assert page["total"] == 2
    assert {item["book_name"] for item in page["items"]} == {"مغازه", "خانه"}
    assert page["items"][0]["book_name"] == "خانه"  # the newest first
    assert page["totals"] == [{"currency": "IRT", "income": "1000.00", "expense": "300.00"}] or (
        page["totals"][0]["currency"] == "IRT" and float(page["totals"][0]["income"]) == 1000)

    only = (await api.get("/api/v1/transactions", headers=headers, params={"book_id": shop})).json()
    assert [item["book_name"] for item in only["items"]] == ["مغازه"]


async def test_totals_are_kept_apart_per_currency(api):
    headers = await signed_in(api, "b@example.com")
    toman = await make_book(api, headers, "تومانی")
    dollars = await make_book(api, headers, "دلاری", currency="USDT")
    await add(api, headers, toman, amount="500", flow="income")
    await add(api, headers, dollars, amount="20", flow="income")
    totals = (await api.get("/api/v1/transactions", headers=headers)).json()["totals"]
    assert {row["currency"] for row in totals} == {"IRT", "USDT"}


async def test_a_book_that_is_not_yours_is_not_listed_or_leaked(api):
    mine = await signed_in(api, "c@example.com")
    theirs = await signed_in(api, "d@example.com")
    stranger_book = await make_book(api, theirs, "دفتر دیگران")
    await add(api, theirs, stranger_book, amount="5", flow="income")
    assert (await api.get("/api/v1/transactions", headers=mine)).json()["total"] == 0
    assert (await api.get("/api/v1/transactions", headers=mine,
                          params={"book_id": stranger_book})).status_code == 404


async def test_moving_to_another_book_takes_files_and_balances_along(api):
    headers = await signed_in(api, "e@example.com")
    wrong = await make_book(api, headers, "اشتباه")
    right = await make_book(api, headers, "درست")
    tx = await add(api, headers, wrong, amount="700", flow="expense", category="اجاره")
    up = await api.post(f"/api/v1/books/{wrong}/transactions/{tx['id']}/attachments", headers=headers,
                        files={"file": ("a.png", PNG, "image/png")})
    assert up.status_code == 201, up.text

    moved = await api.patch(f"/api/v1/books/{wrong}/transactions/{tx['id']}", headers=headers,
                            json={"book_id": right})
    assert moved.status_code == 200, moved.text
    assert moved.json()["attachment_count"] == 1

    assert (await api.get(f"/api/v1/books/{wrong}/transactions", headers=headers)).json()["total"] == 0
    there = (await api.get(f"/api/v1/books/{right}/transactions", headers=headers)).json()
    assert there["total"] == 1 and there["items"][0]["category"] == "اجاره"
    cats = (await api.get(f"/api/v1/books/{right}/categories", headers=headers)).json()
    assert "اجاره" in {c["name"] for c in cats}
    files = await api.get(f"/api/v1/books/{right}/transactions/{tx['id']}/attachments", headers=headers)
    assert files.status_code == 200 and len(files.json()) == 1
    for book in (wrong, right):
        report = await api.get(f"/api/v1/books/{book}/transactions", headers=headers)
        assert report.status_code == 200


async def test_the_move_can_change_other_things_in_the_same_edit(api):
    headers = await signed_in(api, "f@example.com")
    wrong = await make_book(api, headers, "اشتباه")
    right = await make_book(api, headers, "درست")
    tx = await add(api, headers, wrong, amount="700", flow="expense")
    moved = await api.patch(f"/api/v1/books/{wrong}/transactions/{tx['id']}", headers=headers,
                            json={"book_id": right, "amount": "900", "category": "خرید"})
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["category"] == "خرید" and float(body["original_amount"]) == 900


async def test_books_with_different_units_refuse_the_move(api):
    headers = await signed_in(api, "g@example.com")
    toman = await make_book(api, headers, "تومانی")
    dollars = await make_book(api, headers, "دلاری", currency="USDT")
    tx = await add(api, headers, toman, amount="10", flow="income")
    refused = await api.patch(f"/api/v1/books/{toman}/transactions/{tx['id']}", headers=headers,
                              json={"book_id": dollars})
    assert refused.status_code == 422
    assert (await api.get(f"/api/v1/books/{toman}/transactions", headers=headers)).json()["total"] == 1


async def test_a_stranger_cannot_receive_or_send_an_entry(api):
    owner = await signed_in(api, "h@example.com")
    other = await signed_in(api, "i@example.com")
    mine = await make_book(api, owner, "من")
    theirs = await make_book(api, other, "آنها")
    tx = await add(api, owner, mine, amount="10", flow="income")
    into = await api.patch(f"/api/v1/books/{mine}/transactions/{tx['id']}", headers=owner,
                           json={"book_id": theirs})
    assert into.status_code == 404
    out = await api.patch(f"/api/v1/books/{mine}/transactions/{tx['id']}", headers=other,
                          json={"book_id": theirs})
    assert out.status_code == 404
    assert (await api.get(f"/api/v1/books/{mine}/transactions", headers=owner)).json()["total"] == 1


async def test_a_foreign_currency_entry_needs_the_currency_in_the_target(api):
    headers = await signed_in(api, "j@example.com")
    wrong = await make_book(api, headers, "اشتباه", enable=("TON",))
    right = await make_book(api, headers, "درست")
    tx = await add(api, headers, wrong, amount="5", flow="income", currency="TON", conversion_rate="100000")
    refused = await api.patch(f"/api/v1/books/{wrong}/transactions/{tx['id']}", headers=headers,
                              json={"book_id": right})
    assert refused.status_code == 422
    await api.put(f"/api/v1/books/{right}/currencies/TON", headers=headers, json={"enabled": True})
    ok = await api.patch(f"/api/v1/books/{wrong}/transactions/{tx['id']}", headers=headers,
                         json={"book_id": right})
    assert ok.status_code == 200, ok.text
