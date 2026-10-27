"""The loop that decides when to speak first.

Wiring only. `ReminderService` decides *what* to say and to whom; this decides
*when*, and hands it to the adapter. Keeping the two apart is what will let Bale
reuse every line of the reminder logic without reusing any of this file.

Sending twice is worse than not sending: a duplicate digest teaches people to
ignore the bot. Every send is recorded first, keyed by user and by *that
person's* day, so a restart mid-loop cannot repeat one — and neither can the
server's own date turning over in the middle of somebody's evening.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from kasbbook.bot.state import StateStore
from kasbbook.modules.identity.models import Provider, User
from kasbbook.modules.recurring.service import RecurringRun, RecurringService
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
        book_recurring: bool = True,
    ) -> None:
        self.database = database
        self.adapter = adapter
        self.state = state
        self.provider = provider
        self.book_recurring = book_recurring
        self._running = False

    async def _already_sent(self, kind: str, user_id, day: date) -> bool:
        return bool(await self.state.get(_sent_key(kind, user_id, day)))

    async def _mark_sent(self, kind: str, user_id, day: date) -> None:
        # Two days, so a late-evening send is still remembered past midnight.
        await self.state.set(_sent_key(kind, user_id, day), {"sent": True}, ttl=48 * 3600)

    async def tick(self, now: Optional[datetime] = None, today: Optional[date] = None) -> int:
        """One pass. Returns how many messages were sent."""
        moment = now or datetime.now(tz=ZoneInfo("UTC"))
        # Recurring rules belong to books, not to people, so they run on the
        # server's day. Everything addressed to a person below runs on theirs.
        server_day = today or moment.date()
        sent = 0

        async for session in self.database.session():
            from kasbbook.bot.delivery import deliver_invitations
            sent += await deliver_invitations(session, self.adapter, self.provider)
            service = ReminderService(session)
            recipients = await service.recipients(self.provider)

            # Recurring rules book here because this is the one loop that
            # runs whether or not anybody is talking to the bot. They used to
            # be booked by nothing at all. Committed before anyone is told,
            # so a failed send never undoes a booking.
            recurring = (
                await RecurringService(session).run_due(until=server_day)
                if self.book_recurring else RecurringRun()
            )
            await session.commit()
            chats = dict(recipients)
            for notice in await service.recurring_notices(recurring, today=server_day):
                external_id = chats.get(notice.user_id)
                if external_id is None:
                    # The owner is not on this messenger. Their own loop never
                    # sees this run, so the notice is lost — logged, not hidden.
                    logger.info("recurring notice for %s has no chat here", notice.user_id)
                    continue
                try:
                    await self.adapter.send_plain(external_id, notice.text)
                    sent += 1
                except Exception:
                    logger.warning("could not deliver the recurring notice to %s",
                                   notice.user_id, exc_info=True)

            for user_id, external_id in recipients:
                user = await session.get(User, user_id)
                if user is None or not user.is_active:
                    continue

                # At or after the hour they chose, never before it. "A due date
                # does not care what time it is" is true of the date and false
                # of the person: the warnings ignored the hour, so on the
                # server's day they went out on its first tick — half past
                # three in the morning in Tehran, every day, to somebody who
                # had asked to be spoken to at nine in the evening.
                #
                # `>=` rather than `==` because one missed tick at 21:00 — a
                # long recurring catch-up, a restart — used to cost the whole
                # day's digest in silence. The key below still holds it to one.
                if _local_hour(user, moment) < user.digest_hour:
                    continue

                # Their day, not the server's: the service owns that conversion
                # so the day a message is *about* and the day it is deduplicated
                # on cannot drift apart. See `ReminderService.today_for`.
                person_day = await service.today_for(user_id, today, moment)

                fresh = []
                for reminder in await service.for_user(user_id, today, moment):
                    if not await self._already_sent(reminder.kind, user_id, person_day):
                        fresh.append(reminder)
                if not fresh:
                    continue

                # One message, not three. Everything here fires in the same
                # tick, and three notifications in the same minute is noise
                # whatever they say — which is what teaches somebody to swipe
                # the bot away without reading it. Each kind keeps its own key,
                # so one that only becomes true later in the evening still
                # arrives on its own.
                #
                # Recorded before sending: a crash between the two costs one
                # missed reminder, which is cheaper than a duplicate.
                for reminder in fresh:
                    await self._mark_sent(reminder.kind, user_id, person_day)
                try:
                    await self.adapter.send_plain(
                        external_id, "\n\n".join(item.text for item in fresh)
                    )
                    sent += 1
                except Exception:
                    logger.warning(
                        "could not deliver %s to %s",
                        ", ".join(item.kind for item in fresh), user_id,
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
