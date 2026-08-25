"""Running the bot, on whichever provider it was pointed at.

This module is wiring and nothing else: it builds an adapter, pulls updates,
hands each one to the shared conversation layer, and sends the reply back. It
names no provider — Telegram, Bale and Rubika all arrive through the same
`MessagingAdapter` contract, and which one runs is a setting.

Every update gets its own database session. One bad update rolls back its own
work and is logged; it never takes the loop down with it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]

# Order matters and is not cosmetic. The first-generation package at the repo
# root is also called `kasbbook`, so src/ has to win the name or `import
# kasbbook` silently loads the old bot. src goes to the front; the root is
# appended, only so `apps.bot.*` resolves when this runs as a script.
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import httpx  # noqa: E402

from kasbbook.adapters.bale import BaleAdapter  # noqa: E402
from kasbbook.adapters.base import MessagingAdapter  # noqa: E402
from kasbbook.adapters.rubika import RubikaAdapter  # noqa: E402
from kasbbook.adapters.telegram import TelegramAdapter  # noqa: E402
from kasbbook.bot.conversation import Conversation  # noqa: E402
from kasbbook.bot.state import MemoryStateStore, RedisStateStore, StateStore  # noqa: E402
from kasbbook.modules.identity.models import Provider  # noqa: E402
from kasbbook.shared.database import Database  # noqa: E402
from kasbbook.shared.settings import Settings  # noqa: E402

from apps.bot.reminders import ReminderLoop  # noqa: E402

logger = logging.getLogger("kasbbook.bot")

# httpx logs full request URLs at INFO, and every one of these APIs puts the
# bot token in the path. That is how a token ends up in the journal.
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


ADAPTERS = {
    Provider.TELEGRAM: TelegramAdapter,
    Provider.BALE: BaleAdapter,
    Provider.RUBIKA: RubikaAdapter,
}


def build_adapter(settings: Settings, client=None) -> MessagingAdapter:
    """The adapter for whichever provider this process was pointed at."""
    provider = settings.provider
    if provider not in ADAPTERS:
        raise RuntimeError(
            f"KASBBOOK_PROVIDER={provider.value} has no adapter. "
            f"Choose one of: {', '.join(p.value for p in ADAPTERS)}"
        )

    return ADAPTERS[provider](
        token=settings.require_token(),
        bot_username=settings.bot_username,
        webhook_secret=settings.webhook_secret,
        client=client or httpx.AsyncClient(timeout=60),
    )


class BotRunner:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        adapter: MessagingAdapter,
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
                # The adapter's own provider, not a setting: the two cannot
                # disagree, and a Bale update must never resolve to a Telegram
                # identity with the same external id.
                conversation = Conversation(session, self.state, self.adapter.provider)
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

        if reply.forward_file_id:
            await self.adapter.send_stored_file(reply.chat_id, reply.forward_file_id)

        if reply.document is not None:
            await self.adapter.send_file(
                reply.chat_id,
                reply.document.content,
                reply.document.filename,
                reply.document.caption,
            )

    async def poll_once(self, timeout: int = 25) -> int:
        """Fetch and process one batch. Returns how many updates were handled.

        The three outcomes get three different responses. An unreachable
        provider is usually a blip, so it retries soon. A refusal is a revoked
        token or a flood wait, so it backs off harder — hammering it makes both
        worse.
        """
        batch = await self.adapter.fetch_updates(self._offset, timeout)

        if batch.unreachable:
            logger.warning("could not reach the provider: %s", batch.refused)
            await asyncio.sleep(3)
            return 0

        if batch.refused:
            logger.error("the provider refused getUpdates: %s", batch.refused)
            await asyncio.sleep(5)
            return 0

        updates: List[Dict[str, Any]] = batch.updates
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
        await self.adapter.delete_webhook()

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

    database = Database(settings.database_url)
    adapter = build_adapter(settings)

    identity = await adapter.get_me()
    if identity is None:
        raise RuntimeError(f"{settings.provider.value} rejected the token")
    logger.info(
        "connected to %s as @%s",
        settings.provider.value,
        identity.get("username") or identity.get("bot", {}).get("username", "?"),
    )

    state = await build_state_store(settings)
    runner = BotRunner(settings, database, adapter, state)

    # Reminders run beside the poller rather than inside it, so a slow digest
    # cannot delay someone's next button press.
    reminders = ReminderLoop(database, adapter, state, provider=settings.provider)
    reminder_task = asyncio.create_task(reminders.run())

    try:
        await runner.run()
    finally:
        reminders.stop()
        reminder_task.cancel()
        await adapter.aclose()
        await database.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
