"""Every error the API returns has one shape, and every response carries its request id.

    {"detail": ..., "error": {"code", "message", "request_id", "fields"?}}

`detail` is what the API always returned and stays as it was; `error` is what
a program reads. Each test below checks the shape for one kind of failure, so a
handler that is skipped or bypassed shows up as a different body.
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.shared.settings import Settings
from tests.test_api_auth import SECRET, bearer, register

pytestmark = pytest.mark.asyncio

HEX_ID = re.compile(r"[0-9a-f]{32}")


@pytest.fixture
async def app(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    application = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())

    async def boom():
        raise RuntimeError("secret detail: the database password is hunter2")

    application.add_api_route("/__boom", boom)
    return application


@pytest.fixture
async def api(app):
    # raise_app_exceptions=False: an unhandled error becomes the 500 a real
    # client sees, rather than an exception in the test.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


def _shape(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"detail", "error"}, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert body["error"]["request_id"] == response.headers["X-Request-Id"]
    return body


# ------------------------------------------------------------- one shape each
async def test_401_names_the_scheme_and_has_the_shape(api):
    reply = await api.get("/api/v1/books")
    _shape(reply, 401, "auth_error")
    assert reply.headers["WWW-Authenticate"] == "Bearer"


async def test_403_has_the_shape(api):
    tokens = await register(api)
    key = (await api.post("/api/v1/auth/api-keys", json={"name": "k"},
                          headers=bearer(tokens))).json()["key"]
    reply = await api.get("/api/v1/auth/api-keys", headers={"X-API-Key": key})
    _shape(reply, 403, "permission_denied")


async def test_404_for_an_unknown_route_has_the_shape(api):
    _shape(await api.get("/api/v1/no-such-thing"), 404, "not_found")


async def test_405_has_the_shape(api):
    _shape(await api.delete("/api/v1/auth/register"), 405, "method_not_allowed")


async def test_422_validation_names_the_field_and_never_echoes_the_value(api):
    """The value someone typed can be a password; the error says where, not what."""
    reply = await api.post("/api/v1/auth/register", json={
        "display_name": "x", "email": "not-an-email", "password": "SECRET-PASSWORD-123",
    })
    body = _shape(reply, 422, "invalid_request")
    assert "SECRET-PASSWORD-123" not in reply.text
    assert "not-an-email" not in reply.text
    assert any(f["loc"] == "body.email" for f in body["error"]["fields"])
    assert all("input" not in item for item in body["detail"])


async def test_422_from_the_domain_has_the_shape(api):
    headers = bearer(await register(api))
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "مغازه", "type": "business"})).json()
    reply = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers,
                           json={"flow": "income", "category": "فروش",
                                 "amount": "1" + "0" * 29})
    body = _shape(reply, 422, "validation_error")
    assert body["detail"] == body["error"]["message"]


async def test_429_has_the_shape_and_says_when_to_return(api):
    await register(api)
    for _ in range(30):
        reply = await api.post("/api/v1/auth/login", json={
            "identifier": "emad@example.com", "password": "wrong-password"})
        if reply.status_code == 429:
            break
    _shape(reply, 429, "too_many_attempts")
    assert int(reply.headers["Retry-After"]) >= 1


async def test_500_has_the_shape_and_leaks_nothing(api, caplog):
    reply = await api.get("/__boom")
    body = _shape(reply, 500, "internal_error")
    assert "hunter2" not in reply.text and "secret detail" not in reply.text
    # The id in the answer is the one in the log line, so support can find it.
    assert any(body["error"]["request_id"] in record.getMessage() for record in caplog.records)


async def test_a_book_you_cannot_see_and_a_book_that_does_not_exist_look_the_same(api):
    owner = bearer(await register(api))
    stranger = bearer(await register(api, email="other@example.com"))
    book = (await api.post("/api/v1/books", headers=owner,
                           json={"name": "مغازه", "type": "business"})).json()

    hidden = await api.get(f"/api/v1/books/{book['id']}", headers=stranger)
    missing = await api.get(f"/api/v1/books/{uuid.uuid4()}", headers=stranger)

    a, b = _shape(hidden, 404, "not_found"), _shape(missing, 404, "not_found")
    a["error"].pop("request_id"), b["error"].pop("request_id")
    assert a == b


# --------------------------------------------------------------- request ids
async def test_every_response_carries_a_request_id_even_a_success(api):
    reply = await api.get("/healthz")
    assert reply.status_code == 200
    assert HEX_ID.fullmatch(reply.headers["X-Request-Id"])


async def test_a_well_formed_caller_id_is_kept_so_both_logs_line_up(api):
    reply = await api.get("/api/v1/books", headers={"X-Request-Id": "client-trace.0042"})
    assert reply.headers["X-Request-Id"] == "client-trace.0042"
    assert reply.json()["error"]["request_id"] == "client-trace.0042"


@pytest.mark.parametrize("offered", ["short", "x" * 65, "has spaces in it", "line\tbreak-attempt"])
async def test_an_unusable_caller_id_is_replaced_not_trusted(api, offered):
    reply = await api.get("/api/v1/books", headers={"X-Request-Id": offered})
    assert HEX_ID.fullmatch(reply.headers["X-Request-Id"])
    assert reply.headers["X-Request-Id"] != offered
