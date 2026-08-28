"""Registering, signing in, and everything that protects those two.

The interesting tests here are the negative ones. An auth layer that lets the
right people in is easy; the value is in what it refuses, and in what it
refuses to *tell* a caller who is guessing.
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
    """The real app, against the test database, with no network anywhere."""
    settings = Settings(
        database_url="sqlite+aiosqlite://", api_secret_key=SECRET,
        telegram_bot_username="KasbBookTest",
    )
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # The lifespan is what puts settings and the database on app.state.
        async with app.router.lifespan_context(app):
            yield client


async def register(api, email="emad@example.com", password="a-good-password"):
    response = await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": email, "password": password,
    })
    assert response.status_code == 201, response.text
    return response.json()


def bearer(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --------------------------------------------------------------- register
async def test_registering_returns_a_usable_pair(api):
    tokens = await register(api)

    assert tokens["token_type"] == "Bearer"
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["expires_in"] > 0

    me = await api.get("/api/v1/auth/me", headers=bearer(tokens))
    assert me.status_code == 200
    assert me.json()["display_name"] == "عماد"


async def test_an_account_needs_a_way_to_be_reached(api):
    response = await api.post("/api/v1/auth/register", json={
        "display_name": "بی‌نشان", "password": "a-good-password",
    })
    assert response.status_code == 422


async def test_a_short_password_is_refused_before_it_is_hashed(api):
    response = await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "x@example.com", "password": "1234",
    })
    assert response.status_code == 422


async def test_the_password_is_never_returned_anywhere(api):
    tokens = await register(api)
    me = await api.get("/api/v1/auth/me", headers=bearer(tokens))

    body = me.text
    assert "password" not in body
    assert "argon2" not in body.lower()


# ------------------------------------------------------------------ login
async def test_signing_in_with_the_right_password_works(api):
    await register(api)
    response = await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password",
    })
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_a_wrong_password_and_an_unknown_account_answer_identically(api):
    """Two different answers here would turn this into an account finder."""
    await register(api)

    wrong = await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "not-the-password",
    })
    unknown = await api.post("/api/v1/auth/login", json={
        "identifier": "nobody@example.com", "password": "not-the-password",
    })

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_guessing_is_rate_limited(api):
    await register(api)
    attempt = {"identifier": "emad@example.com", "password": "wrong"}

    codes = [
        (await api.post("/api/v1/auth/login", json=attempt)).status_code
        for _ in range(8)
    ]
    assert 429 in codes, codes
    # And it stops *before* the eighth try, not at some distant ceiling.
    assert codes.index(429) <= 5


# ---------------------------------------------------------------- bearer
async def test_a_protected_route_refuses_an_anonymous_caller(api):
    assert (await api.get("/api/v1/auth/me")).status_code == 401


async def test_a_forged_token_is_refused(api):
    response = await api.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"}
    )
    assert response.status_code == 401


async def test_a_token_signed_with_another_key_is_refused(api):
    """The whole point of signing. Worth asserting rather than assuming."""
    import jwt

    from kasbbook.shared.security import utcnow

    forged = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001", "typ": "access",
         "exp": int(utcnow().timestamp()) + 600},
        "a-different-key", algorithm="HS256",
    )
    response = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


async def test_a_refresh_token_cannot_be_used_as_a_bearer(api):
    """They are both long strings; only one of them opens doors."""
    tokens = await register(api)
    response = await api.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert response.status_code == 401


# --------------------------------------------------------------- refresh
async def test_refreshing_returns_a_new_pair(api):
    tokens = await register(api)
    response = await api.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"] != tokens["refresh_token"]


async def test_the_old_refresh_token_stops_working(api):
    """Rotation. Without this, a stolen token is good for a month."""
    tokens = await register(api)
    await api.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    again = await api.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert again.status_code == 401


async def test_reusing_a_spent_token_signs_the_whole_family_out(api):
    """Theft detection, and the reason rotation is worth the complexity.

    Two parties hold the same token and there is no way to tell which one is
    asking. Signing both out is the only safe answer.
    """
    tokens = await register(api)
    fresh = (await api.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )).json()

    # The thief replays the old one.
    replay = await api.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    # And the legitimate holder's newer token is dead too.
    legitimate = await api.post(
        "/api/v1/auth/refresh", json={"refresh_token": fresh["refresh_token"]}
    )
    assert legitimate.status_code == 401


async def test_logging_out_kills_that_session_only(api):
    tokens = await register(api)
    other = (await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password",
    })).json()

    await api.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert (await api.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )).status_code == 401
    assert (await api.post(
        "/api/v1/auth/refresh", json={"refresh_token": other["refresh_token"]}
    )).status_code == 200


async def test_logging_out_everywhere_kills_every_session(api):
    tokens = await register(api)
    other = (await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password",
    })).json()

    response = await api.post("/api/v1/auth/logout-everywhere", headers=bearer(tokens))
    assert response.status_code == 204

    for pair in (tokens, other):
        assert (await api.post(
            "/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )).status_code == 401


async def test_logging_out_an_unknown_token_is_not_an_error(api):
    """It is already signed out, which is what the caller wanted."""
    response = await api.post(
        "/api/v1/auth/logout", json={"refresh_token": "never-existed"}
    )
    assert response.status_code == 204


async def test_sessions_lists_where_the_account_is_signed_in(api):
    tokens = await register(api)
    await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password",
    })

    response = await api.get("/api/v1/auth/sessions", headers=bearer(tokens))
    assert response.status_code == 200
    assert len(response.json()) == 2


# -------------------------------------------------------------- api keys
async def test_an_api_key_works_as_a_credential(api):
    tokens = await register(api)
    created = await api.post(
        "/api/v1/auth/api-keys", json={"name": "nightly export"}, headers=bearer(tokens)
    )
    assert created.status_code == 201

    key = created.json()["key"]
    me = await api.get("/api/v1/auth/me", headers={"X-API-Key": key})
    assert me.status_code == 200
    assert me.json()["display_name"] == "عماد"


async def test_the_key_is_shown_once_and_never_again(api):
    tokens = await register(api)
    created = (await api.post(
        "/api/v1/auth/api-keys", json={"name": "nightly"}, headers=bearer(tokens)
    )).json()

    listed = (await api.get("/api/v1/auth/api-keys", headers=bearer(tokens))).json()
    assert listed[0]["prefix"] == created["key"][:8]
    assert "key" not in listed[0]
    assert created["key"] not in str(listed)


async def test_a_revoked_key_stops_working(api):
    tokens = await register(api)
    created = (await api.post(
        "/api/v1/auth/api-keys", json={"name": "nightly"}, headers=bearer(tokens)
    )).json()

    assert (await api.delete(
        f"/api/v1/auth/api-keys/{created['id']}", headers=bearer(tokens)
    )).status_code == 204
    assert (await api.get(
        "/api/v1/auth/me", headers={"X-API-Key": created["key"]}
    )).status_code == 401


async def test_an_invented_key_is_refused(api):
    assert (await api.get(
        "/api/v1/auth/me", headers={"X-API-Key": "kb_not-a-real-key"}
    )).status_code == 401


async def test_one_account_cannot_revoke_another_accounts_key(api):
    owner = await register(api, "owner@example.com")
    created = (await api.post(
        "/api/v1/auth/api-keys", json={"name": "mine"}, headers=bearer(owner)
    )).json()

    stranger = await register(api, "stranger@example.com")
    response = await api.delete(
        f"/api/v1/auth/api-keys/{created['id']}", headers=bearer(stranger)
    )
    assert response.status_code == 404

    # And it still works for its owner.
    assert (await api.get(
        "/api/v1/auth/me", headers={"X-API-Key": created["key"]}
    )).status_code == 200


# ---------------------------------------------------------------- health
async def test_healthz_answers_without_touching_the_database(api):
    response = await api.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readyz_actually_queries(api):
    response = await api.get("/readyz")
    assert response.status_code == 200
    assert response.json()["database"] == "reachable"


# ------------------------------------------------------------- receipts
async def test_a_transaction_reports_whether_it_has_a_receipt(api, db):
    """The bot can attach one; the API should at least be able to see it.

    The file id itself is deliberately not returned — it is opaque and scoped
    to the messenger holding the file, so it would mean nothing to an HTTP
    client and handing it out only widens what a leak exposes.
    """
    tokens = await register(api)
    book = (await api.post("/api/v1/books", headers=bearer(tokens),
                           json={"name": "مغازه", "type": "business"})).json()
    created = (await api.post(
        f"/api/v1/books/{book['id']}/transactions", headers=bearer(tokens),
        json={"flow": "expense", "category": "خرید", "amount": "500000"},
    )).json()

    assert created["has_receipt"] is False
    assert created["receipt_kind"] is None

    # Attach one the way the bot does, through the same service.
    import uuid as _uuid

    from kasbbook.modules.ledger.service import LedgerService

    async for session in db.session():
        me = (await api.get("/api/v1/auth/me", headers=bearer(tokens))).json()
        await LedgerService(session).attach_receipt(
            _uuid.UUID(book["id"]), _uuid.UUID(me["id"]), _uuid.UUID(created["id"]),
            "DOC-1", "telegram", kind="document", file_name="invoice.pdf",
        )
        await session.commit()

    fetched = (await api.get(
        f"/api/v1/books/{book['id']}/transactions/{created['id']}",
        headers=bearer(tokens),
    )).json()

    assert fetched["has_receipt"] is True
    assert fetched["receipt_kind"] == "document"
    assert fetched["receipt_file_name"] == "invoice.pdf"
    assert "receipt_file_id" not in fetched


# ------------------------------------------------------------- account
async def test_the_profile_can_be_changed(api):
    tokens = await register(api)
    response = await api.patch("/api/v1/auth/me", headers=bearer(tokens),
                               json={"display_name": "عماد حبیب‌نیا",
                                     "timezone": "Europe/Istanbul"})

    assert response.status_code == 200
    assert response.json()["display_name"] == "عماد حبیب‌نیا"
    assert response.json()["timezone"] == "Europe/Istanbul"


async def test_an_unknown_timezone_is_refused(api):
    tokens = await register(api)
    response = await api.patch("/api/v1/auth/me", headers=bearer(tokens),
                               json={"timezone": "Mars/Olympus"})
    assert response.status_code == 422


async def test_contact_details_can_be_changed(api):
    tokens = await register(api)
    response = await api.put("/api/v1/auth/me/contact", headers=bearer(tokens),
                             json={"phone": "09121234567"})

    assert response.status_code == 200
    assert response.json()["phone"] == "09121234567"


async def test_an_address_another_account_holds_is_refused(api):
    await register(api, "first@example.com")
    second = await register(api, "second@example.com")

    response = await api.put("/api/v1/auth/me/contact", headers=bearer(second),
                             json={"email": "first@example.com"})

    assert response.status_code == 422
    # And it does not confirm that the address is registered.
    assert "first@example.com" not in response.text


async def test_changing_the_password_requires_the_current_one(api):
    tokens = await register(api)

    without = await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                            json={"new_password": "a-different-password"})
    assert without.status_code == 422

    wrong = await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                          json={"current_password": "nope",
                                "new_password": "a-different-password"})
    assert wrong.status_code == 422

    # The old one still works, so nothing was half-changed.
    assert (await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password",
    })).status_code == 200


async def test_changing_the_password_ends_every_session(api):
    """Including the one that asked, which is the point of doing it."""
    tokens = await register(api)
    other = (await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password",
    })).json()

    changed = await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                            json={"current_password": "a-good-password",
                                  "new_password": "a-different-password"})
    assert changed.status_code == 204

    for pair in (tokens, other):
        assert (await api.post("/api/v1/auth/refresh",
                               json={"refresh_token": pair["refresh_token"]})
                ).status_code == 401

    assert (await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-different-password",
    })).status_code == 200


async def test_an_anonymous_caller_cannot_touch_an_account(api):
    await register(api)
    for method, path, body in (
        ("patch", "/api/v1/auth/me", {"display_name": "x"}),
        ("put", "/api/v1/auth/me/contact", {"phone": "09121234567"}),
        ("put", "/api/v1/auth/me/password", {"new_password": "a-good-password"}),
    ):
        response = await getattr(api, method)(path, json=body)
        assert response.status_code == 401, path


# ------------------------------------------------- the access-token window
#
# Revoking refresh tokens leaves every already-issued access token working
# until it expires. A live smoke test found it: after a password change the old
# bearer still answered 200, for up to thirty minutes. Nothing in the suite
# noticed, because every test until now asserted on refresh tokens.

async def test_the_old_bearer_dies_with_the_password(api):
    tokens = await register(api)
    assert (await api.get("/api/v1/auth/me", headers=bearer(tokens))).status_code == 200

    await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                  json={"current_password": "a-good-password",
                        "new_password": "a-different-password"})

    # Same token, one moment later. It was valid; it is not any more.
    assert (await api.get("/api/v1/auth/me", headers=bearer(tokens))).status_code == 401


async def test_signing_out_everywhere_ends_access_too(api):
    tokens = await register(api)
    other = (await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password",
    })).json()

    await api.post("/api/v1/auth/logout-everywhere", headers=bearer(tokens))

    for pair in (tokens, other):
        assert (await api.get("/api/v1/auth/me", headers=bearer(pair))).status_code == 401


async def test_a_token_issued_after_the_cutoff_still_works(api):
    """The cutoff must end the old sessions without breaking the new one."""
    tokens = await register(api)
    await api.post("/api/v1/auth/logout-everywhere", headers=bearer(tokens))

    fresh = (await api.post("/api/v1/auth/login", json={
        "identifier": "emad@example.com", "password": "a-good-password",
    })).json()

    assert (await api.get("/api/v1/auth/me", headers=bearer(fresh))).status_code == 200


async def test_one_accounts_cutoff_does_not_touch_another(api):
    mine = await register(api, "mine@example.com")
    theirs = await register(api, "theirs@example.com")

    await api.post("/api/v1/auth/logout-everywhere", headers=bearer(mine))

    assert (await api.get("/api/v1/auth/me", headers=bearer(mine))).status_code == 401
    assert (await api.get("/api/v1/auth/me", headers=bearer(theirs))).status_code == 200


async def test_an_api_key_is_unaffected_by_a_password_change(api):
    """A key belongs to a program; a nightly job should not stop at 3am."""
    tokens = await register(api)
    key = (await api.post("/api/v1/auth/api-keys", json={"name": "nightly"},
                          headers=bearer(tokens))).json()["key"]

    await api.put("/api/v1/auth/me/password", headers=bearer(tokens),
                  json={"current_password": "a-good-password",
                        "new_password": "a-different-password"})

    assert (await api.get("/api/v1/auth/me",
                          headers={"X-API-Key": key})).status_code == 200
