"""What the web panel's account page and login screen lean on.

A default book for everyone, a username to sign in by, one device signed out
at a time, and a guest who is gone the moment they leave.
"""

from __future__ import annotations

import pytest

from tests.test_api_auth import api, bearer, register  # noqa: F401  (the api fixture)

pytestmark = pytest.mark.asyncio


async def books_of(api, tokens):
    return (await api.get("/api/v1/books", headers=bearer(tokens))).json()


async def test_a_new_account_starts_with_a_personal_book(api):
    tokens = await register(api)

    books = await books_of(api, tokens)

    assert [(b["name"], b["type"]) for b in books] == [("حساب‌داری شخصی", "personal")]


async def test_an_account_without_a_book_gets_one_when_it_lists_them(api):
    tokens = await register(api)
    only = (await books_of(api, tokens))[0]
    await api.delete(f"/api/v1/books/{only['id']}", headers=bearer(tokens))

    books = await books_of(api, tokens)

    assert len(books) == 1


async def test_a_username_and_password_sign_in(api):
    tokens = await register(api)
    named = await api.put("/api/v1/auth/me/username", headers=bearer(tokens),
                          json={"username": "Emad.Habibnia"})
    assert named.status_code == 200
    assert named.json()["username"] == "emad.habibnia"

    signed = await api.post("/api/v1/auth/login", json={
        "identifier": "emad.habibnia", "password": "a-good-password"})

    assert signed.status_code == 200


async def test_a_username_that_is_taken_or_malformed_is_refused(api):
    first = await register(api)
    second = await register(api, email="sara@example.com")
    await api.put("/api/v1/auth/me/username", headers=bearer(first), json={"username": "emad"})

    taken = await api.put("/api/v1/auth/me/username", headers=bearer(second),
                          json={"username": "EMAD"})
    short = await api.put("/api/v1/auth/me/username", headers=bearer(second),
                          json={"username": "ab"})
    spaced = await api.put("/api/v1/auth/me/username", headers=bearer(second),
                           json={"username": "has space"})

    assert taken.status_code == 422 and short.status_code == 422 and spaced.status_code == 422


async def test_one_device_can_be_signed_out_and_not_the_others(api):
    one = await register(api)
    two = (await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password"})).json()
    listed = (await api.get("/api/v1/auth/sessions", headers=bearer(one))).json()
    assert len(listed) == 2

    gone = await api.delete(f"/api/v1/auth/sessions/{listed[0]['id']}", headers=bearer(one))

    assert gone.status_code == 204
    left = (await api.get("/api/v1/auth/sessions", headers=bearer(one))).json()
    assert len(left) == 1
    assert two["refresh_token"]


async def test_someone_elses_device_cannot_be_signed_out(api):
    mine = await register(api)
    theirs = await register(api, email="sara@example.com")
    theirs_listed = (await api.get("/api/v1/auth/sessions", headers=bearer(theirs))).json()

    refused = await api.delete(
        f"/api/v1/auth/sessions/{theirs_listed[0]['id']}", headers=bearer(mine))

    assert refused.status_code == 404
    assert len((await api.get("/api/v1/auth/sessions", headers=bearer(theirs))).json()) == 1


async def test_a_guest_can_record_and_is_removed_on_sign_out(api):
    made = await api.post("/api/v1/auth/guest")
    assert made.status_code == 201
    tokens = made.json()
    me = (await api.get("/api/v1/auth/me", headers=bearer(tokens))).json()
    assert me["is_guest"] is True
    books = await books_of(api, tokens)
    assert len(books) == 1
    recorded = await api.post(
        f"/api/v1/books/{books[0]['id']}/transactions", headers=bearer(tokens),
        json={"flow": "income", "scope": "personal", "category": "حقوق",
              "amount": "1000", "occurred_on": "2026-11-06"})
    assert recorded.status_code == 201, recorded.text

    out = await api.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert out.status_code == 204
    assert (await api.get("/api/v1/auth/me", headers=bearer(tokens))).status_code == 401


async def test_a_guest_cannot_take_a_name_or_a_password(api):
    tokens = (await api.post("/api/v1/auth/guest")).json()

    name = await api.put("/api/v1/auth/me/username", headers=bearer(tokens),
                         json={"username": "visitor"})
    password = await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                             json={"new_password": "a-good-password"})

    assert name.status_code == 422 and password.status_code == 422


async def test_guest_creation_is_rate_limited(api):
    for _ in range(10):
        assert (await api.post("/api/v1/auth/guest")).status_code == 201

    assert (await api.post("/api/v1/auth/guest")).status_code == 429


async def test_a_messenger_remembers_when_it_last_spoke(session):
    from datetime import timedelta

    from kasbbook.modules.identity.models import Provider
    from kasbbook.modules.identity.service import IdentityService
    from kasbbook.shared.security import utcnow

    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "777001")
    row = await identity.find_identity(Provider.TELEGRAM, "777001")
    assert row.last_seen_at is not None and row.user_id == user.id

    # A burst of updates inside a minute leaves the stamp alone; a later one moves it.
    stamp = row.last_seen_at
    await identity.observe_username(Provider.TELEGRAM, "777001", "emad")
    assert (await identity.find_identity(Provider.TELEGRAM, "777001")).last_seen_at == stamp
    row.last_seen_at = utcnow() - timedelta(minutes=5)
    await identity.observe_username(Provider.TELEGRAM, "777001", "emad")
    moved = (await identity.find_identity(Provider.TELEGRAM, "777001")).last_seen_at
    # SQLite hands times back without a zone; compare them the same way.
    assert moved.replace(tzinfo=None) >= stamp.replace(tzinfo=None) - timedelta(seconds=1)


# ------------------------------------------------- a forgotten password
async def link_messenger(db, api, tokens):
    """Attach a Telegram account to the registered user, the way the bot does when someone presses Start."""
    from kasbbook.modules.identity.models import Provider
    from kasbbook.modules.identity.service import IdentityService

    me = (await api.get("/api/v1/auth/me", headers=bearer(tokens))).json()
    import uuid

    async for s in db.session():
        service = IdentityService(s)
        issued = await service.start_link_from_web(uuid.UUID(me["id"]), Provider.TELEGRAM)
        await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "909090")
        await s.commit()


@pytest.fixture
def sent(monkeypatch):
    """What the panel would have handed to the messenger."""
    outbox = []

    async def capture(request, settings, identity, text, buttons):
        outbox.append((identity.provider.value, identity.external_id, text))

    monkeypatch.setattr("kasbbook.api.routers.auth._send_code", capture)
    return outbox


async def test_a_forgotten_password_is_reset_with_a_code_from_the_messenger(api, db, sent):
    tokens = await register(api)
    await link_messenger(db, api, tokens)

    asked = await api.post("/api/v1/auth/me/password/reset-code", headers=bearer(tokens))

    assert asked.status_code == 200 and asked.json()["sent_to"] == "telegram"
    assert len(sent) == 1 and sent[0][1] == "909090"
    import re

    code = re.search(r"[A-Z2-9]{8}", sent[0][2]).group()
    changed = await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                            json={"new_password": "brand-new-password", "reset_code": code})
    assert changed.status_code == 204
    signed = await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "brand-new-password"})
    assert signed.status_code == 200


async def test_a_wrong_code_changes_nothing(api, db, sent):
    tokens = await register(api)
    await link_messenger(db, api, tokens)

    refused = await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                            json={"new_password": "brand-new-password", "reset_code": "AAAAAAAA"})

    assert refused.status_code == 422
    signed = await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password"})
    assert signed.status_code == 200


async def test_a_used_code_is_dead(api, db, sent):
    tokens = await register(api)
    await link_messenger(db, api, tokens)
    await api.post("/api/v1/auth/me/password/reset-code", headers=bearer(tokens))
    import re

    code = re.search(r"[A-Z2-9]{8}", sent[0][2]).group()
    await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                  json={"new_password": "brand-new-password", "reset_code": code})
    again = await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "brand-new-password"})

    reused = await api.put("/api/v1/auth/me/password",
                           headers=bearer(again.json()),
                           json={"new_password": "third-password-here", "reset_code": code})

    assert reused.status_code == 422


async def test_no_code_is_sent_without_a_messenger_or_a_password(api, sent):
    tokens = await register(api)

    no_messenger = await api.post("/api/v1/auth/me/password/reset-code", headers=bearer(tokens))

    assert no_messenger.status_code == 422 and sent == []
    guest = (await api.post("/api/v1/auth/guest")).json()
    assert (await api.post("/api/v1/auth/me/password/reset-code", headers=bearer(guest))).status_code == 422


async def test_asking_for_codes_is_limited(api, db, sent):
    tokens = await register(api)
    await link_messenger(db, api, tokens)
    for _ in range(3):
        assert (await api.post("/api/v1/auth/me/password/reset-code", headers=bearer(tokens))).status_code == 200

    assert (await api.post("/api/v1/auth/me/password/reset-code", headers=bearer(tokens))).status_code == 429


async def test_a_guest_cannot_tie_anything_lasting_to_the_account(api):
    tokens = (await api.post("/api/v1/auth/guest")).json()

    key = await api.post("/api/v1/auth/api-keys", headers=bearer(tokens), json={"name": "k"})
    link = await api.post("/api/v1/identities/link", headers=bearer(tokens), json={"provider": "telegram"})
    contact = await api.put("/api/v1/auth/me/contact", headers=bearer(tokens), json={"email": "g@example.com"})

    assert key.status_code == 403 and link.status_code == 403 and contact.status_code == 403


async def test_a_guest_cannot_add_people_to_a_book(api, db):
    import uuid

    from kasbbook.modules.books.models import Role
    from kasbbook.modules.books.service import BookService
    from kasbbook.shared.errors import PermissionDenied

    guest = (await api.post("/api/v1/auth/guest")).json()
    me = (await api.get("/api/v1/auth/me", headers=bearer(guest))).json()
    book = (await api.get("/api/v1/books", headers=bearer(guest))).json()[0]
    other = await register(api)
    other_me = (await api.get("/api/v1/auth/me", headers=bearer(other))).json()

    async for s in db.session():
        with pytest.raises(PermissionDenied):
            await BookService(s).add_member(
                uuid.UUID(me["id"]), uuid.UUID(book["id"]), uuid.UUID(other_me["id"]), Role.MEMBER)
