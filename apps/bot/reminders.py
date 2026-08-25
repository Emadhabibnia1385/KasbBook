"""The loop that decides when to speak first.

Wiring only. `ReminderService` decides *what* to say and to whom; this decides
*when*, and hands it to the adapter. Keeping the two apart is what will let Bale
reuse every line of the reminder logic without reusing any of this file.

Sending twice is worse than not sending: a duplicate digest teaches people to
ignore the bot. Every send is recorded first, keyed by user and day, so a
restart mid-loop cannot repeat one.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from kasbbook.bot.state import StateStore
from kasbbook.modules.identity.models import Provider, User
from kasbbook.modules.reminders.service import ReminderService
from kasbbook.shared.database import Database

logger = logging.getLogger("kasbbook.reminders")

# Checked every fifteen minutes: often enough that an hour set to 21 arrives
# close to 21, cheap enough that it costs nothing when there is nothing to do.
TICK_SECONDS = 15 * 60


def _local_hour(user: User, now: Optional[datetime] = None) -> int:
    """The user's own hour, not the server's.

    A shopkeeper in Tehran asked for nine in the evening, not nine wherever the
    machine happens to be racked.
    """
    moment = now or datetime.now(tz=ZoneInfo("UTC"))
    try:
        return moment.astimezone(ZoneInfo(user.timezone)).hour
    except Exception:
        return moment.astimezone(ZoneInfo("Asia/Tehran")).hour


def _sent_key(kind: str, user_id, day: date) -> str:
    return f"sent:{kind}:{user_id}:{day.isoformat()}"


class ReminderLoop:
    def __init__(
        self,
        database: Database,
        adapter,
        state: StateStore,
        provider: Provider = Provider.TELEGRAM,
    ) -> None:
        self.database = database
        self.adapter = adapter
        self.state = state
        self.provider = provider
        self._running = False

    async def _already_sent(self, kind: str, user_id, day: date) -> bool:
        return bool(await self.state.get(_sent_key(kind, user_id, day)))

    async def _mark_sent(self, kind: str, user_id, day: date) -> None:
        # Two days, so a late-evening send is still remembered past midnight.
        await self.state.set(_sent_key(kind, user_id, day), {"sent": True}, ttl=48 * 3600)

    async def tick(self, now: Optional[datetime] = None, today: Optional[date] = None) -> int:
        """One pass. Returns how many messages were sent."""
        moment = now or datetime.now(tz=ZoneInfo("UTC"))
        day = today or moment.date()
        sent = 0

        async for session in self.database.session():
            service = ReminderService(session)
            recipients = await service.recipients(self.provider)

            for user_id, external_id in recipients:
                user = await session.get(User, user_id)
                if user is None or not user.is_active:
                    continue

                # The digest waits for the hour the user chose; the warnings do
                # not, because a due date does not care what time it is.
                due = []
                if user.digest_enabled and _local_hour(user, moment) == user.digest_hour:
                    digest = await service.daily_digest(user_id, day)
                    if digest is not None:
                        due.append(digest)

                for reminder in (
                    await service.due_installments(user_id, user.reminder_days, today=day),
                    await service.due_debts(user_id, user.reminder_days, today=day),
                ):
                    if reminder is not None:
                        due.append(reminder)

                for reminder in due:
                    if await self._already_sent(reminder.kind, user_id, day):
                        continue

                    # Recorded before sending: a crash between the two costs one
                    # missed reminder, which is cheaper than a duplicate.
                    await self._mark_sent(reminder.kind, user_id, day)
                    try:
                        await self.adapter.send_plain(external_id, reminder.text)
                        sent += 1
                    except Exception:
                        logger.warning(
                            "could not deliver %s to %s", reminder.kind, user_id,
                            exc_info=True,
                        )

            await session.commit()

        if sent:
            logger.info("sent %s reminder(s)", sent)
        return sent

    async def run(self) -> None:
        self._running = True
        logger.info("reminder loop started")

        while self._running:
            try:
                await self.tick()
            except Exception:
                logger.exception("reminder tick failed; the loop continues")
            await asyncio.sleep(TICK_SECONDS)

    def stop(self) -> None:
        self._running = False
