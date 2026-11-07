"""A colleague added by name only, and linking them to a real account later."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"
DAY = date(2026, 8, 24)


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def register(api, name, email):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": name, "email": email, "password": "a-good-password"})).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def team(api):
    headers = await register(api, "عماد", "owner@example.com")
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "کارگاه", "type": "team"})).json()["id"]
    return headers, book


async def test_a_person_is_added_by_name_without_an_account(api):
    headers, book = await team(api)
    made = await api.post(f"/api/v1/books/{book}/people", headers=headers, json={"name": "  علی   رضایی "})
    assert made.status_code == 201, made.text
    assert made.json()["display_name"] == "علی رضایی"
    assert made.json()["has_account"] is False

    listed = (await api.get(f"/api/v1/books/{book}/members", headers=headers)).json()
    flags = {row["display_name"]: row["has_account"] for row in listed}
    assert flags == {"عماد": True, "علی رضایی": False}


async def test_a_person_can_be_given_a_share_and_renamed(api):
    headers, book = await team(api)
    person = (await api.post(f"/api/v1/books/{book}/people", headers=headers, json={"name": "علی"})).json()

    share = await api.put(f"/api/v1/books/{book}/shares", headers=headers, json={
        "user_id": person["user_id"], "basis": "percent", "value": "30"})
    assert share.status_code == 200, share.text

    renamed = await api.patch(f"/api/v1/books/{book}/members/{person['user_id']}", headers=headers,
                              json={"display_name": "علی احمدی"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["display_name"] == "علی احمدی"


async def test_a_real_account_name_cannot_be_renamed_by_the_book(api):
    headers, book = await team(api)
    me = (await api.get("/api/v1/auth/me", headers=headers)).json()
    response = await api.patch(f"/api/v1/books/{book}/members/{me['id']}", headers=headers,
                               json={"display_name": "کس دیگر"})
    assert response.status_code == 422


async def test_linking_moves_the_share_and_the_slips_onto_the_account(api):
    headers, book = await team(api)
    person = (await api.post(f"/api/v1/books/{book}/people", headers=headers, json={"name": "سارا"})).json()
    put = await api.put(f"/api/v1/books/{book}/shares", headers=headers, json={
        "user_id": person["user_id"], "basis": "percent", "value": "40",
        "effective_from": "2026-08-01"})
    assert put.status_code == 200, put.text
    await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json={
        "flow": "income", "category": "فروش", "amount": "1000000", "occurred_on": DAY.isoformat()})
    period = (await api.post(f"/api/v1/books/{book}/periods", headers=headers, json={
        "label": "مرداد", "starts_on": "2026-08-01", "ends_on": "2026-08-31"})).json()
    calculated = await api.post(f"/api/v1/books/{book}/periods/{period['id']}/calculate", headers=headers)
    assert calculated.status_code == 200, calculated.text
    slips = (await api.get(f"/api/v1/books/{book}/periods/{period['id']}/payslips",
                           headers=headers)).json()
    assert person["user_id"] in {s["user_id"] for s in slips}

    sara = await register(api, "سارا واقعی", "sara@example.com")
    sara_id = (await api.get("/api/v1/auth/me", headers=sara)).json()["id"]

    linked = await api.post(f"/api/v1/books/{book}/members/{person['user_id']}/link", headers=headers,
                            json={"identifier": "sara@example.com", "role": "member"})
    assert linked.status_code == 200, linked.text
    assert linked.json()["user_id"] == sara_id
    assert linked.json()["has_account"] is True

    shares = (await api.get(f"/api/v1/books/{book}/shares", headers=headers)).json()
    assert [s["user_id"] for s in shares] == [sara_id]
    slips = (await api.get(f"/api/v1/books/{book}/periods/{period['id']}/payslips",
                           headers=headers)).json()
    assert {s["user_id"] for s in slips} == {sara_id}
    members = (await api.get(f"/api/v1/books/{book}/members", headers=headers)).json()
    assert {m["user_id"] for m in members} == {sara_id, (await api.get("/api/v1/auth/me", headers=headers)).json()["id"]}

    # The account can now reach the book.
    assert (await api.get(f"/api/v1/books/{book}/members", headers=sara)).status_code == 200


async def test_linking_to_an_unknown_or_already_present_account_is_refused(api):
    headers, book = await team(api)
    person = (await api.post(f"/api/v1/books/{book}/people", headers=headers, json={"name": "علی"})).json()
    missing = await api.post(f"/api/v1/books/{book}/members/{person['user_id']}/link", headers=headers,
                             json={"identifier": "nobody@example.com", "role": "member"})
    assert missing.status_code == 404

    own = await api.post(f"/api/v1/books/{book}/members/{person['user_id']}/link", headers=headers,
                         json={"identifier": "owner@example.com", "role": "member"})
    assert own.status_code == 422


async def test_a_member_without_the_right_cannot_add_people(api):
    headers, book = await team(api)
    sara = await register(api, "سارا", "sara@example.com")
    await api.post(f"/api/v1/books/{book}/members", headers=headers,
                   json={"identifier": "sara@example.com", "role": "member"})
    response = await api.post(f"/api/v1/books/{book}/people", headers=sara, json={"name": "کس"})
    assert response.status_code == 403


async def test_people_do_not_block_deleting_the_book_and_leave_no_orphans(api, session):
    from sqlalchemy import func, select

    from kasbbook.modules.identity.models import User

    headers, book = await team(api)
    await api.post(f"/api/v1/books/{book}/people", headers=headers, json={"name": "علی"})
    import uuid

    from kasbbook.modules.books.service import BookService

    me = (await api.get("/api/v1/auth/me", headers=headers)).json()["id"]
    await BookService(session).delete_book(uuid.UUID(me), uuid.UUID(book))
    await session.commit()
    session.expire_all()
    count = await session.scalar(select(func.count(User.id)).where(User.is_placeholder.is_(True)))
    assert count == 0


async def test_a_telegram_id_and_username_find_the_account(api, session):
    import uuid

    from kasbbook.modules.identity.models import Identity, Provider
    from kasbbook.shared.security import utcnow

    headers, book = await team(api)
    sara = await register(api, "سارا", "sara@example.com")
    sara_id = (await api.get("/api/v1/auth/me", headers=sara)).json()["id"]
    session.add(Identity(user_id=uuid.UUID(sara_id), provider=Provider.TELEGRAM, external_id="555111",
                         external_username="Sara_T", linked_at=utcnow()))
    await session.commit()

    for handle in ("555111", "@sara_t"):
        person = (await api.post(f"/api/v1/books/{book}/people", headers=headers, json={"name": "سارا"})).json()
        done = await api.post(f"/api/v1/books/{book}/members/{person['user_id']}/link", headers=headers,
                              json={"identifier": handle, "role": "member"})
        if handle == "555111":
            assert done.status_code == 200, done.text
            assert done.json()["user_id"] == sara_id
        else:
            # Already in the book now, so the second handle is refused rather than doubled.
            assert done.status_code == 422


async def test_a_guest_may_add_people_by_name(api):
    tokens = (await api.post("/api/v1/auth/guest")).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "کارگاه", "type": "team"})).json()["id"]
    made = await api.post(f"/api/v1/books/{book}/people", headers=headers, json={"name": "علی"})
    assert made.status_code == 201, made.text
