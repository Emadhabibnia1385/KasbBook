"""Signing in to the web panel through the bot.

The property worth proving is not that the right person gets in, but that
nobody else can: a link alone signs no one in, a session is collected once and
only by the browser that asked, and a forged Mini App launch is refused.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.identity.models import Provider
from kasbbook.shared.settings import Settings

from tests.test_conversation import command, press

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"
BOT_TOKEN = "123456:test-token"


@pytest.fixture
async def api(db):
    settings = Settings(
        database_url="sqlite+aiosqlite://", api_secret_key=SECRET,
        telegram_bot_username="KasbBookTest", telegram_token=BOT_TOKEN,
    )
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def start(api):
    response = await api.post("/api/v1/auth/telegram/start")
    assert response.status_code == 201, response.text
    body = response.json()
    token = body["deep_link"].split("start=wl_")[1]
    return body["poll_secret"], token


async def bot_says(db, event):
    async for session in db.session():
        reply = await Conversation(session, MemoryStateStore(), Provider.TELEGRAM).handle(event)
        await session.commit()
        return reply


async def poll(api, secret):
    response = await api.post("/api/v1/auth/telegram/poll", json={"poll_secret": secret})
    assert response.status_code == 200, response.text
    return response.json()


async def test_approving_in_the_bot_gives_the_browser_a_session_once(api, db):
    secret, token = await start(api)
    assert (await poll(api, secret))["status"] == "pending"

    prompt = await bot_says(db, command("start", f"wl_{token}"))
    assert any(b.data == f"wl:ok:{token}" for row in prompt.buttons for b in row)
    # Opening the link signs nobody in; only the tap does.
    assert (await poll(api, secret))["status"] == "pending"

    await bot_says(db, press(f"wl:ok:{token}"))
    result = await poll(api, secret)
    assert result["status"] == "approved"
    me = await api.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {result['tokens']['access_token']}"})
    assert me.status_code == 200

    # The session is handed over exactly once.
    assert (await poll(api, secret))["status"] == "expired"


async def test_refusing_in_the_bot_ends_the_attempt(api, db):
    secret, token = await start(api)
    await bot_says(db, command("start", f"wl_{token}"))
    await bot_says(db, press(f"wl:no:{token}"))
    assert (await poll(api, secret))["status"] == "denied"
    # And the same link cannot be approved afterwards.
    await bot_says(db, press(f"wl:ok:{token}"))
    assert (await poll(api, secret))["status"] == "denied"


async def test_the_link_alone_cannot_collect_a_session(api, db):
    secret, token = await start(api)
    await bot_says(db, command("start", f"wl_{token}"))
    await bot_says(db, press(f"wl:ok:{token}"))
    # The token in the link is not the poll secret.
    assert (await poll(api, token))["status"] == "expired"
    assert (await poll(api, secret))["status"] == "approved"


async def test_an_unknown_poll_secret_learns_nothing(api):
    assert (await poll(api, "nope"))["status"] == "expired"


def signed_init_data(user: dict, token: str = BOT_TOKEN, age: int = 0) -> str:
    fields = {"auth_date": str(int(time.time()) - age), "user": json.dumps(user)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


async def test_a_genuine_mini_app_launch_signs_in(api):
    data = signed_init_data({"id": 777001, "first_name": "عماد"})
    first = await api.post("/api/v1/auth/telegram/webapp", json={"init_data": data})
    assert first.status_code == 200, first.text
    again = await api.post("/api/v1/auth/telegram/webapp", json={"init_data": data})
    me = lambda r: api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    # The same Telegram id is the same account, not a new one each launch.
    assert (await me(first)).json()["id"] == (await me(again)).json()["id"]


@pytest.mark.parametrize("data", [
    signed_init_data({"id": 1}, token="999:other-bot"),
    signed_init_data({"id": 1}, age=3 * 86400),
    "auth_date=1&user=%7B%22id%22%3A1%7D&hash=deadbeef",
])
async def test_a_forged_or_stale_launch_is_refused(api, data):
    response = await api.post("/api/v1/auth/telegram/webapp", json={"init_data": data})
    assert response.status_code == 422
