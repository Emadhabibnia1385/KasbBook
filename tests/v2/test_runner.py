"""The polling loop, driven against a fake Telegram.

This is as close to the real thing as it gets without a token: real update
payloads, the real adapter, the real conversation layer and a real database —
only the HTTP boundary is replaced.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest

APPS = Path(__file__).resolve().parents[2]
if str(APPS) not in sys.path:
    sys.path.insert(0, str(APPS))

from apps.telegram_bot.runner import TelegramRunner  # noqa: E402
from kasbbook.adapters.telegram import TelegramAdapter  # noqa: E402
from kasbbook.bot.state import MemoryStateStore  # noqa: E402
from kasbbook.modules.books.models import BookType  # noqa: E402
from kasbbook.modules.books.service import BookService  # noqa: E402
from kasbbook.modules.identity.models import Provider  # noqa: E402
from kasbbook.modules.identity.service import IdentityService  # noqa: E402
from kasbbook.modules.ledger.service import LedgerService  # noqa: E402
from kasbbook.shared.settings import Settings  # noqa: E402

pytestmark = pytest.mark.asyncio


class FakeTelegramServer:
    """Serves queued updates and records everything the bot sends back."""

    def __init__(self, updates: List[Dict[str, Any]]) -> None:
        self.pending = list(updates)
        self.sent: List[Dict[str, Any]] = []
        self._next_id = 1000

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            method = request.url.path.rsplit("/", 1)[-1]
            body = json.loads(request.content) if request.content else {}

            if method == "getUpdates":
                batch, self.pending = self.pending, []
                return httpx.Response(200, json={"ok": True, "result": batch})

            self.sent.append({"method": method, "body": body})
            self._next_id += 1
            return httpx.Response(
                200, json={"ok": True, "result": {"message_id": self._next_id}}
            )

        return httpx.MockTransport(handle)

    def texts(self) -> List[str]:
        return [c["body"].get("text", "") for c in self.sent if "text" in c["body"]]


def update(update_id: int, *, text=None, data=None, message_id=10, user_id=555001):
    """A Telegram update shaped exactly as the real API sends it."""
    if data is not None:
        return {
            "update_id": update_id,
            "callback_query": {
                "id": f"cb{update_id}",
                "from": {"id": user_id, "username": "emad", "first_name": "عماد"},
                "data": data,
                "message": {"message_id": message_id, "chat": {"id": user_id}},
            },
        }
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "from": {"id": user_id, "username": "emad", "first_name": "عماد"},
            "chat": {"id": user_id},
            "text": text,
        },
    }


async def build(db, updates):
    server = FakeTelegramServer(updates)
    adapter = TelegramAdapter(
        token="test", bot_username="KasbBookTest",
        client=httpx.AsyncClient(transport=server.transport()),
    )
    runner = TelegramRunner(
        Settings(database_url="sqlite+aiosqlite://"), db, adapter, MemoryStateStore()
    )
    return server, runner


# ---------------------------------------------------------------- the loop
async def test_a_full_conversation_runs_through_the_loop(db, session):
    """From /start to a saved transaction, through real update payloads."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await session.commit()

    server, runner = await build(db, [
        update(1, text="/start"),
        update(2, data=f"tx:book:{book.id}"),
        update(3, data="tx:flow:income"),
        update(4, text="فروش"),
        update(5, text="۲۵۰ک"),
    ])

    handled = await runner.poll_once()
    assert handled == 5

    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].converted_amount == Decimal("250000")
    assert any("ثبت شد" in text for text in server.texts())


async def test_button_presses_are_answered_so_they_stop_spinning(db, session):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    server, runner = await build(db, [update(1, data="nav:home")])
    await runner.poll_once()

    assert any(c["method"] == "answerCallbackQuery" for c in server.sent)


async def test_a_button_press_edits_the_screen_instead_of_adding_one(db, session):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    server, runner = await build(db, [update(1, data="book:list")])
    await runner.poll_once()

    methods = [c["method"] for c in server.sent]
    assert "editMessageText" in methods
    assert "sendMessage" not in methods


async def test_the_offset_advances_so_updates_are_not_replayed(db, session):
    server, runner = await build(db, [update(7, text="/start"), update(8, text="/start")])
    await runner.poll_once()
    assert runner._offset == 9


async def test_one_failing_update_does_not_stop_the_others(db, session):
    """A bad update is logged and skipped; the loop keeps its promise."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    server, runner = await build(db, [
        # A book id that is not a UUID blows up inside the conversation.
        update(1, data="tx:book:not-a-uuid"),
        update(2, text="/start"),
    ])

    handled = await runner.poll_once()
    assert handled == 2
    # The second update still produced a screen.
    assert any("KasbBook" in text for text in server.texts())


async def test_an_update_the_bot_ignores_costs_nothing(db, session):
    server, runner = await build(db, [{"update_id": 1, "channel_post": {"message_id": 3}}])
    handled = await runner.poll_once()

    assert handled == 1
    assert server.sent == []


async def test_a_telegram_error_does_not_crash_the_poller(db, session):
    server = FakeTelegramServer([])

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "flood wait"})

    adapter = TelegramAdapter(
        token="test", client=httpx.AsyncClient(transport=httpx.MockTransport(failing))
    )
    runner = TelegramRunner(
        Settings(database_url="sqlite+aiosqlite://"), db, adapter, MemoryStateStore()
    )

    assert await runner.poll_once(timeout=0) == 0


# --------------------------------------------------------------- settings
async def test_a_missing_token_fails_loudly_at_startup():
    settings = Settings(database_url="sqlite+aiosqlite://", telegram_token=None)
    with pytest.raises(RuntimeError) as caught:
        settings.require_telegram()

    assert "BotFather" in str(caught.value)


async def test_settings_default_to_sqlite_so_a_dev_can_just_run_it(monkeypatch):
    for name in ("KASBBOOK_DATABASE_URL", "TELEGRAM_BOT_TOKEN", "REDIS_URL"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()
    assert settings.database_url.startswith("sqlite")
    assert not settings.uses_postgres
    assert settings.telegram_token is None
