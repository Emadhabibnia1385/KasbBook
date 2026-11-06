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
