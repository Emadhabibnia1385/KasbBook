"""Running the Telegram bot.

This module is wiring and nothing else: it builds the adapter, pulls updates,
hands each one to the shared conversation layer, and sends the reply back. All
the behaviour being exercised lives in kasbbook/, which is why the same runner
shape will work for Bale and Rubika.

Every update gets its own database session. One bad update rolls back its own
work and is logged; it never takes the loop down with it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import httpx  # noqa: E402

from kasbbook.adapters.telegram import API_ROOT, TelegramAdapter  # noqa: E402
from kasbbook.bot.conversation import Conversation  # noqa: E402
from kasbbook.bot.state import MemoryStateStore, RedisStateStore, StateStore  # noqa: E402
from kasbbook.modules.identity.models import Provider  # noqa: E402
from kasbbook.shared.database import Database  # noqa: E402
from kasbbook.shared.settings import Settings  # noqa: E402

logger = logging.getLogger("kasbbook.telegram")

# httpx logs full request URLs at INFO, and a Telegram URL contains the token.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


async def build_state_store(settings: Settings) -> StateStore:
    """Redis when configured, otherwise in-process."""
    if not settings.redis_url:
        logger.info("conversation state: in-process (single worker only)")
        return MemoryStateStore()

    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning("REDIS_URL is set but the redis package is missing; using memory")
        return MemoryStateStore()

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await client.ping()
    logger.info("conversation state: redis")
    return RedisStateStore(client)


class TelegramRunner:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        adapter: TelegramAdapter,
        state: StateStore,
    ) -> None:
        self.settings = settings
        self.database = database
        self.adapter = adapter
        self.state = state
        self._offset: Optional[int] = None
        self._running = False

    async def handle_update(self, payload: Dict[str, Any]) -> None:
        """One update, one unit of work."""
        event = self.adapter.parse_event(payload)
        if event is None:
            return

        # Answer the button first so it stops spinning even if the work is slow.
        if event.callback_id:
            try:
                await self.adapter.answer_callback(event.callback_id)
            except Exception:
                logger.debug("could not answer callback", exc_info=True)

        async for session in self.database.session():
            try:
                conversation = Conversation(session, self.state, Provider.TELEGRAM)
                reply = await conversation.handle(event)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("update failed; the loop continues")
                return

        if reply.edit_message_id:
            await self.adapter.edit_message(reply)
        else:
            await self.adapter.send_message(reply)

        if reply.document is not None:
            await self.adapter.send_file(
                reply.chat_id,
                reply.document.content,
                reply.document.filename,
                reply.document.caption,
            )

    async def poll_once(self, timeout: int = 25) -> int:
        """Fetch and process one batch. Returns how many updates were handled."""
        params: Dict[str, Any] = {"timeout": timeout}
        if self._offset is not None:
            params["offset"] = self._offset

        try:
            response = await self.adapter._client.post(
                f"{API_ROOT}/bot{self.adapter.token}/getUpdates", json=params
            )
            body = response.json()
        except Exception:
            logger.warning("getUpdates failed; retrying", exc_info=True)
            await asyncio.sleep(3)
            return 0

        if not body.get("ok"):
            logger.error("Telegram refused getUpdates: %s", body.get("description"))
            await asyncio.sleep(5)
            return 0

        updates: List[Dict[str, Any]] = body.get("result", [])
        for update in updates:
            # Advance the offset before handling, so a repeatedly failing update
            # cannot wedge the bot in a loop on the same message.
            self._offset = update["update_id"] + 1
            await self.handle_update(update)

        return len(updates)

    async def run(self) -> None:
        self._running = True
        logger.info("KasbBook telegram bot started")

        # Polling and a webhook cannot both be active.
        await self.adapter._call("deleteWebhook")

        while self._running:
            await self.poll_once()

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    token = settings.require_telegram()
    database = Database(settings.database_url)
    adapter = TelegramAdapter(
        token=token,
        bot_username=settings.telegram_bot_username,
        webhook_secret=settings.telegram_webhook_secret,
        client=httpx.AsyncClient(timeout=60),
    )

    identity = await adapter._call("getMe")
    if identity is None:
        raise RuntimeError("Telegram rejected the token")
    logger.info("connected as @%s", identity.get("username"))

    state = await build_state_store(settings)
    runner = TelegramRunner(settings, database, adapter, state)

    try:
        await runner.run()
    finally:
        await adapter.aclose()
        await database.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
