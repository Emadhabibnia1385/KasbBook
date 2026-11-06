"""Every route that names a book refuses somebody who is not in it.

Written from the OpenAPI document rather than from a list, so a route added
tomorrow is covered without anyone remembering to add it here. The check is the
coarse, important one: a stranger never gets a success from a book that is not
theirs, whatever the route does and whatever it would have returned.
"""

from __future__ import annotations

import re
import uuid

import pytest

from tests.test_api_auth import api, bearer, register  # noqa: F401  (the api fixture)

pytestmark = pytest.mark.asyncio

SUCCESS = {200, 201, 202, 204}
# A route the caller is not meant to need membership for, even though it names a book.
OPEN = set()


def book_routes(spec):
    for path, methods in spec["paths"].items():
        if "{book_id}" not in path:
            continue
        for method in methods:
            if method in {"get", "post", "put", "patch", "delete"}:
                yield method, path


def fill(path, book_id):
    out = path.replace("{book_id}", book_id)
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), out)


async def test_a_stranger_gets_nothing_from_any_book_route(api):
    owner = await register(api)
    stranger = await register(api, email="stranger@example.com")
    book = (await api.get("/api/v1/books", headers=bearer(owner))).json()[0]
    spec = (await api.get("/openapi.json")).json()

    leaks = []
    for method, path in book_routes(spec):
        if (method, path) in OPEN:
            continue
        response = await api.request(
            method.upper(), fill(path, book["id"]), headers=bearer(stranger), json={}
        )
        if response.status_code in SUCCESS:
            leaks.append(f"{method.upper()} {path} -> {response.status_code}")

    assert not leaks, "a stranger was answered with success:\n" + "\n".join(leaks)


async def test_no_book_route_answers_without_signing_in(api):
    owner = await register(api)
    book = (await api.get("/api/v1/books", headers=bearer(owner))).json()[0]
    spec = (await api.get("/openapi.json")).json()

    open_doors = []
    for method, path in book_routes(spec):
        response = await api.request(method.upper(), fill(path, book["id"]), json={})
        if response.status_code in SUCCESS:
            open_doors.append(f"{method.upper()} {path} -> {response.status_code}")

    assert not open_doors, "answered without a token:\n" + "\n".join(open_doors)


# The routes that may be reached without signing in, and why. Anything else that appears here is a hole.
PUBLIC = {
    ("POST", "/api/v1/auth/guest"),           # a throwaway account for looking around
    ("POST", "/api/v1/auth/demo"),            # the same, with a year of made-up books to look at
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),          # an unknown token is simply signed out
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/telegram/poll"),   # carries its own secret
    ("POST", "/api/v1/auth/telegram/start"),
    ("POST", "/api/v1/auth/telegram/webapp"),  # proves itself with Telegram's signed data
    ("POST", "/api/v1/webhooks/{provider}/{secret}"),  # the secret is in the path
    ("GET", "/healthz"),
    ("GET", "/readyz"),
}


async def test_only_the_expected_routes_can_be_reached_without_signing_in(api):
    spec = (await api.get("/openapi.json")).json()

    open_doors = []
    for path, methods in spec["paths"].items():
        for method in methods:
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            url = re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)
            response = await api.request(method.upper(), url, json={})
            if response.status_code not in (401, 403) and (method.upper(), path) not in PUBLIC:
                open_doors.append(f"{method.upper()} {path} -> {response.status_code}")

    assert not open_doors, "reachable without a token:\n" + "\n".join(open_doors)
