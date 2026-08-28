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

from apps.bot.runner import BotRunner, build_adapter  # noqa: E402
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
    runner = BotRunner(
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
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "flood wait"})

    adapter = TelegramAdapter(
        token="test", client=httpx.AsyncClient(transport=httpx.MockTransport(failing))
    )
    runner = BotRunner(
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


# ------------------------------------------------------- the systemd path
async def test_the_runner_loads_when_executed_as_a_script():
    """
    systemd runs `python apps/bot/runner.py`, not `-m`.

    Importing it as a module — which every other test here does — hides a
    relative import that has no parent package when it is a script. That
    difference took the bot down once; this is the test that would have caught
    it, so it runs the file the way the service does.
    """
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    repo = _Path(__file__).resolve().parents[2]
    import os as _os

    env = dict(_os.environ)
    env["KASBBOOK_DATABASE_URL"] = "sqlite+aiosqlite://"
    env.pop("TELEGRAM_BOT_TOKEN", None)

    result = subprocess.run(
        [_sys.executable, str(repo / "apps" / "bot" / "runner.py")],
        capture_output=True, text=True, timeout=60, env=env,
    )

    combined = result.stdout + result.stderr
    assert "ImportError" not in combined, combined[-600:]
    assert "ModuleNotFoundError" not in combined, combined[-600:]
    # It should get all the way to the one thing genuinely missing: a token.
    assert "BotFather" in combined, combined[-600:]


# ------------------------------------------------ the same loop, another app
#
# The point of the adapter layer is that this file's other tests describe
# Telegram only by accident. These run the identical loop against Bale, with
# nothing changed but a setting.

async def test_the_same_runner_drives_bale(db, session):
    """A whole conversation on Bale, through the same conversation layer."""
    from kasbbook.adapters.bale import BaleAdapter

    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.BALE)
    await identity.complete_link_from_messenger(issued.token, Provider.BALE, "555001")
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await session.commit()

    server = FakeTelegramServer([
        update(1, text="/start"),
        update(2, data=f"tx:book:{book.id}"),
        update(3, data="tx:flow:income"),
        update(4, text="فروش"),
        update(5, text="۲۵۰ک"),
    ])
    adapter = BaleAdapter(
        token="test", bot_username="KasbBookBot",
        client=httpx.AsyncClient(transport=server.transport()),
    )
    runner = BotRunner(
        Settings(database_url="sqlite+aiosqlite://", provider=Provider.BALE),
        db, adapter, MemoryStateStore(),
    )

    assert await runner.poll_once() == 5

    rows = await LedgerService(session).transactions(book.id, user.id)
    assert len(rows) == 1
    assert rows[0].converted_amount == Decimal("250000")
    assert any("ثبت شد" in text for text in server.texts())


async def test_a_bale_user_is_not_a_telegram_user_with_the_same_number(db, session):
    """The isolation the whole identity model exists to provide."""
    from kasbbook.adapters.bale import BaleAdapter

    identity = IdentityService(session)
    telegram_user = await identity.create_user("عماد تلگرام")
    issued = await identity.start_link_from_web(telegram_user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    # The same external id arrives from Bale. It is a stranger.
    server = FakeTelegramServer([update(1, text="/start")])
    runner = BotRunner(
        Settings(database_url="sqlite+aiosqlite://", provider=Provider.BALE), db,
        BaleAdapter(token="t", client=httpx.AsyncClient(transport=server.transport())),
        MemoryStateStore(),
    )
    await runner.poll_once()

    # Not greeted as the Telegram account: no books, and an invitation to link.
    assert not any("مغازه" in text for text in server.texts())


# ------------------------------------------------------- choosing a provider
async def test_the_provider_is_a_setting_not_a_code_change():
    from kasbbook.adapters.bale import BaleAdapter
    from kasbbook.adapters.rubika import RubikaAdapter
    from kasbbook.adapters.telegram import TelegramAdapter

    expected = {
        Provider.TELEGRAM: TelegramAdapter,
        Provider.BALE: BaleAdapter,
        Provider.RUBIKA: RubikaAdapter,
    }
    for provider, adapter_class in expected.items():
        settings = Settings(
            database_url="sqlite+aiosqlite://", provider=provider,
            telegram_token="t", bale_token="t", rubika_token="t",
        )
        assert isinstance(build_adapter(settings, client=httpx.AsyncClient()), adapter_class)


async def test_each_provider_reads_its_own_token():
    """A Bale process must not silently start with the Telegram token."""
    settings = Settings(
        database_url="sqlite+aiosqlite://", provider=Provider.BALE,
        telegram_token="TELEGRAM-SECRET", bale_token="BALE-SECRET",
    )
    assert settings.token == "BALE-SECRET"
    assert build_adapter(settings, client=httpx.AsyncClient()).token == "BALE-SECRET"


async def test_the_wrong_providers_token_is_a_startup_failure_naming_the_right_one():
    settings = Settings(
        database_url="sqlite+aiosqlite://", provider=Provider.BALE,
        telegram_token="TELEGRAM-SECRET",  # set, but not for this provider
    )
    with pytest.raises(RuntimeError) as caught:
        settings.require_token()

    assert "BALE_BOT_TOKEN" in str(caught.value)
    assert "Bale" in str(caught.value)


async def test_an_unknown_provider_name_is_refused_at_startup(monkeypatch):
    monkeypatch.setenv("KASBBOOK_PROVIDER", "whatsapp")
    with pytest.raises(RuntimeError) as caught:
        Settings.from_env()

    assert "telegram" in str(caught.value)


async def test_eitaa_is_named_but_has_no_adapter_yet_and_says_so():
    """Deliberately deferred. It must fail with the reason, not an AttributeError."""
    settings = Settings(
        database_url="sqlite+aiosqlite://", provider=Provider.EITAA, telegram_token="t"
    )
    with pytest.raises(RuntimeError) as caught:
        build_adapter(settings, client=httpx.AsyncClient())

    assert "no adapter" in str(caught.value)


async def test_the_signing_key_has_no_default():
    """A guessable key is worse than a missing one, because it starts."""
    with pytest.raises(RuntimeError) as caught:
        Settings(database_url="sqlite+aiosqlite://").require_secret_key()

    assert "KASBBOOK_SECRET_KEY" in str(caught.value)


# ------------------------------------------------------------- packaging
#
# `tomllib` is stdlib from 3.11, which is also this project's floor. Skipping on
# anything older keeps a developer on an old interpreter running the rest of the
# suite; CI is on 3.12, so these always run where it counts.
needs_tomllib = pytest.mark.skipif(
    sys.version_info < (3, 11), reason="tomllib arrived in 3.11"
)


@needs_tomllib
async def test_the_two_dependency_lists_agree():
    """pyproject.toml and requirements-v2.txt both name the runtime dependencies.

    Two lists is one more than ideal, but pip wants a requirements file and the
    package metadata wants its own. What is not acceptable is them disagreeing:
    an installed wheel that pulls a different set than a deployment does is a
    difference nobody discovers until something is missing in production.
    """
    import re
    import tomllib

    repo = Path(__file__).resolve().parents[2]

    def name_of(spec: str) -> str:
        # "uvicorn[standard]>=0.32" and "uvicorn>=0.30" are the same package.
        return re.split(r"[<>=!\[;]", spec.strip(), 1)[0].strip().lower()

    declared = {
        name_of(item)
        for item in tomllib.loads(
            (repo / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]["dependencies"]
    }
    required = {
        name_of(line)
        for line in (repo / "requirements-v2.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    }

    assert declared == required, (
        f"only in pyproject: {sorted(declared - required)}; "
        f"only in requirements: {sorted(required - declared)}"
    )


@needs_tomllib
async def test_the_console_entry_point_exists():
    """pyproject names `apps.bot.runner:run`; a typo there fails at install time."""
    import tomllib

    repo = Path(__file__).resolve().parents[2]
    scripts = tomllib.loads(
        (repo / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["scripts"]

    module_path, _, attribute = scripts["kasbbook-bot"].partition(":")
    module = __import__(module_path, fromlist=[attribute])
    assert callable(getattr(module, attribute))


# ------------------------------------------------- the incoming message goes
#
# `delete_message` existed on every adapter and was tested, and nothing ever
# called it. Wiring it is what the single-screen UX was missing, and it is also
# the precondition for the bot asking for a password at all: an undeleted one
# sits in the chat, on the device, and in every backup of both.

async def test_a_typed_message_is_removed_after_it_is_handled(db, session):
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    server, runner = await build(db, [update(1, text="سلام", message_id=77)])
    await runner.poll_once()

    deleted = [c for c in server.sent if c["method"] == "deleteMessage"]
    assert len(deleted) == 1
    assert deleted[0]["body"]["message_id"] == 77


async def test_a_password_never_stays_in_the_chat(db, session):
    """The one that matters. Nothing else here would notice if this regressed."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد", email="emad@example.com")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    server, runner = await build(db, [
        update(1, data="acc:pw"),
        update(2, text="a-good-password", message_id=91),
    ])
    await runner.poll_once()

    assert any(
        c["method"] == "deleteMessage" and c["body"]["message_id"] == 91
        for c in server.sent
    )


async def test_a_button_press_has_nothing_to_remove(db, session):
    """Its message is the bot's own screen, which is edited rather than replaced."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    server, runner = await build(db, [update(1, data="nav:home")])
    await runner.poll_once()

    assert not any(c["method"] == "deleteMessage" for c in server.sent)


async def test_a_message_that_cannot_be_removed_does_not_fail_the_update(db, session):
    """Older than the provider's window, or no permission in a group."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    server = FakeTelegramServer([update(1, text="/start")])
    original = server.transport()

    def refuse_deletes(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("deleteMessage"):
            return httpx.Response(200, json={"ok": False, "description": "too old"})
        return original.handler(request)

    adapter = TelegramAdapter(
        token="test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(refuse_deletes)),
    )
    runner = BotRunner(
        Settings(database_url="sqlite+aiosqlite://"), db, adapter, MemoryStateStore()
    )

    assert await runner.poll_once() == 1
    assert any("KasbBook" in text for text in server.texts())
