"""Receiving updates by webhook instead of polling.

Polling holds an outbound connection and needs nothing reachable from outside.
A webhook needs a public HTTPS endpoint, and it drops updates that arrive while
the API is restarting. Which one runs is a setting, so going back is one line
and a restart — these tests are mostly about the ways that switch can be got
wrong.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"
PATH = "an-unguessable-path-segment"


class FakeTelegram:
    """Records what the webhook handler sent back."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def client(self) -> httpx.AsyncClient:
        def handle(request: httpx.Request) -> httpx.Response:
            self.calls.append({
                "method": str(request.url).rsplit("/", 1)[-1],
                "body": json.loads(request.content) if request.content else {},
            })
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})

        return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def update(update_id=1, *, text=None, data=None, message_id=10, user_id=555001):
    if data is not None:
        return {"update_id": update_id, "callback_query": {
            "id": f"cb{update_id}",
            "from": {"id": user_id, "first_name": "عماد"},
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": user_id}}}}
    return {"update_id": update_id, "message": {
        "message_id": message_id,
        "from": {"id": user_id, "first_name": "عماد"},
        "chat": {"id": user_id}, "text": text}}


def webhook_settings(**over):
    base = dict(
        database_url="sqlite+aiosqlite://", api_secret_key=SECRET,
        provider=Provider.TELEGRAM, telegram_token="t",
        update_mode="webhook", api_base_url="https://kasbbook.example.com",
        webhook_path_secret=PATH,
    )
    base.update(over)
    return Settings(**base)


@pytest.fixture
async def served(db):
    """The API in webhook mode, with a fake Telegram behind the adapter."""
    fake = FakeTelegram()
    app = create_app(settings=webhook_settings(), database=db,
                     limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            app.state.adapters["telegram"]._client = fake.client()
            app.state.state_store = MemoryStateStore()
            yield client, fake


async def linked(session, external_id="555001"):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, external_id)
    await session.commit()
    return user


# ------------------------------------------------------------- the switch
async def test_polling_is_the_default(monkeypatch):
    for name in ("KASBBOOK_UPDATE_MODE", "KASBBOOK_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert Settings.from_env().uses_webhook is False


async def test_webhook_without_a_public_url_is_refused_at_startup():
    """A provider cannot be told where to deliver if nobody said where."""
    with pytest.raises(RuntimeError) as caught:
        webhook_settings(api_base_url="").require_webhook()
    assert "KASBBOOK_API_URL" in str(caught.value)


async def test_a_plain_http_webhook_is_refused():
    """Every update carries somebody's messages."""
    with pytest.raises(RuntimeError) as caught:
        webhook_settings(api_base_url="http://kasbbook.example.com").require_webhook()
    assert "https" in str(caught.value)


async def test_a_missing_path_secret_is_refused_with_the_command_to_fix_it():
    with pytest.raises(RuntimeError) as caught:
        webhook_settings(webhook_path_secret="").require_webhook()
    assert "KASBBOOK_WEBHOOK_PATH" in str(caught.value)
    assert "token_urlsafe" in str(caught.value)


async def test_the_registered_url_is_the_one_the_route_serves():
    """These are built in two places, and a mismatch is a silent 404 forever."""
    url = webhook_settings().require_webhook()
    assert url == f"https://kasbbook.example.com/api/v1/webhooks/telegram/{PATH}"


# ------------------------------------------------------------- delivering
async def test_a_message_arriving_by_webhook_is_handled(served, session, db):
    client, fake = served
    user = await linked(session)
    await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await session.commit()

    response = await client.post(
        f"/api/v1/webhooks/telegram/{PATH}", json=update(1, text="/start")
    )

    assert response.status_code == 200
    assert any(c["method"] == "sendMessage" for c in fake.calls)


async def test_a_typed_message_is_removed_here_too(served, session):
    """Without this, switching to webhook would quietly stop deleting passwords."""
    client, fake = served
    await linked(session)

    await client.post(f"/api/v1/webhooks/telegram/{PATH}",
                      json=update(1, text="سلام", message_id=77))

    deleted = [c for c in fake.calls if c["method"] == "deleteMessage"]
    assert len(deleted) == 1
    assert deleted[0]["body"]["message_id"] == 77


async def test_a_button_press_is_answered_and_edits_in_place(served, session):
    client, fake = served
    await linked(session)

    await client.post(f"/api/v1/webhooks/telegram/{PATH}",
                      json=update(1, data="nav:home"))

    methods = [c["method"] for c in fake.calls]
    assert "answerCallbackQuery" in methods
    assert "editMessageText" in methods
    assert "deleteMessage" not in methods    # its message is the bot's own screen


# ------------------------------------------------------------------ locked
async def test_a_wrong_path_secret_is_refused(served):
    client, _ = served
    response = await client.post("/api/v1/webhooks/telegram/not-the-secret",
                                 json=update(1, text="/start"))
    assert response.status_code == 404


async def test_an_unconfigured_provider_looks_the_same_as_a_wrong_secret(served):
    """Neither should tell a prober which of the two they got wrong."""
    client, _ = served
    a = await client.post(f"/api/v1/webhooks/bale/{PATH}", json=update(1, text="/start"))
    b = await client.post("/api/v1/webhooks/telegram/wrong", json=update(1, text="/start"))
    assert a.status_code == b.status_code == 404


async def test_polling_mode_serves_no_webhook_at_all(db):
    """The default has to be closed, not merely unused."""
    app = create_app(settings=Settings(database_url="sqlite+aiosqlite://",
                                       api_secret_key=SECRET),
                     database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            response = await client.post(f"/api/v1/webhooks/telegram/{PATH}",
                                         json=update(1, text="/start"))
    assert response.status_code == 404


# ------------------------------------------------------------- resilience
async def test_a_failing_update_is_still_acknowledged(served, session):
    """A provider that gets an error retries, and retrying a poisoned update
    forever is worse than dropping it and logging why."""
    client, _ = served
    await linked(session)

    response = await client.post(
        f"/api/v1/webhooks/telegram/{PATH}",
        json=update(1, data="tx:book:not-a-uuid"),
    )
    assert response.status_code == 200


async def test_an_update_nobody_acts_on_is_acknowledged_cheaply(served):
    client, fake = served
    response = await client.post(f"/api/v1/webhooks/telegram/{PATH}",
                                 json={"update_id": 1, "channel_post": {"message_id": 3}})
    assert response.status_code == 200
    assert fake.calls == []


# --------------------------------------------------------------- the unit
async def test_the_api_unit_does_not_log_request_paths():
    """A webhook path contains the secret that guards it.

    nginx is the access log and knows to skip that path; uvicorn's version does
    not, and would write the credential to the journal on every update. This is
    asserted against the unit file because the leak is a deployment property,
    not something any request-level test would see.
    """
    from pathlib import Path

    unit = (Path(__file__).resolve().parents[1]
            / "deploy" / "kasbbook-api.service").read_text(encoding="utf-8")
    assert "--no-access-log" in unit
