"""The loop that decides when the bot speaks first.

The dangerous failure here is not silence, it is repetition: a digest that
arrives twice teaches people to ignore the bot. Most of these tests are about
that.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from apps.bot.reminders import ReminderLoop, _local_hour  # noqa: E402
from kasbbook.bot.state import MemoryStateStore  # noqa: E402
from kasbbook.modules.books.models import BookType  # noqa: E402
from kasbbook.modules.books.service import BookService  # noqa: E402
from kasbbook.modules.identity.models import Provider  # noqa: E402
from kasbbook.modules.identity.service import IdentityService  # noqa: E402
from kasbbook.modules.ledger.models import Flow, Scope  # noqa: E402
from kasbbook.modules.ledger.service import LedgerService  # noqa: E402
from kasbbook.modules.loans.service import LoanService  # noqa: E402

pytestmark = pytest.mark.asyncio
TG = Provider.TELEGRAM

# Pinned, never date.today(): a test that reads the real clock is a test that
# fails on some future Tuesday for reasons nobody will remember.
DAY = date(2026, 8, 24)
NEXT_DAY = date(2026, 8, 25)


class SpyAdapter:
    """Records what would have been sent."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list = []
        self.fail = fail

    async def send_plain(self, chat_id: str, text: str):
        if self.fail:
            raise RuntimeError("telegram is down")
        self.sent.append((chat_id, text))
        return "1"


async def linked(session, name="عماد", external="555001", **prefs):
    identity = IdentityService(session)
    user = await identity.create_user(name)
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, external)

    for field, value in prefs.items():
        setattr(user, field, value)
    await session.flush()
    return user


def at_hour(hour: int, zone: str = "Asia/Tehran") -> datetime:
    """A UTC moment that reads as `hour` in the given zone."""
    local = datetime(DAY.year, DAY.month, DAY.day, hour, 30, tzinfo=ZoneInfo(zone))
    return local.astimezone(ZoneInfo("UTC"))


# ------------------------------------------------------------------- clock
async def test_the_hour_is_the_users_own_not_the_servers(session):
    user = await linked(session, timezone="Asia/Tehran")
    assert _local_hour(user, at_hour(21)) == 21


async def test_a_broken_timezone_falls_back_rather_than_crashing(session):
    user = await linked(session, timezone="Not/AZone")
    assert isinstance(_local_hour(user, at_hour(21)), int)


# ------------------------------------------------------------------ digest
async def test_the_digest_arrives_at_the_hour_the_user_chose(db, session):
    user = await linked(session, digest_enabled=True, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 250_000, occurred_on=DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())

    assert await loop.tick(now=at_hour(21), today=DAY) == 1
    assert "خلاصهٔ" in adapter.sent[0][1]
    assert "250,000" in adapter.sent[0][1]


async def test_nothing_arrives_at_the_wrong_hour(db, session):
    user = await linked(session, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())

    assert await loop.tick(now=at_hour(14), today=DAY) == 0
    assert adapter.sent == []


async def test_a_digest_is_never_sent_twice_in_one_day(db, session):
    """The failure that would teach people to ignore the bot."""
    user = await linked(session, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())
    when, day = at_hour(21), DAY

    assert await loop.tick(now=when, today=day) == 1
    assert await loop.tick(now=when, today=day) == 0
    assert await loop.tick(now=when, today=day) == 0
    assert len(adapter.sent) == 1


async def test_the_next_day_gets_its_own_digest(db, session):
    user = await linked(session, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    ledger = LedgerService(session)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100,
                        occurred_on=DAY)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 200,
                        occurred_on=NEXT_DAY)
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())

    assert await loop.tick(now=at_hour(21), today=DAY) == 1
    assert await loop.tick(now=at_hour(21), today=NEXT_DAY) == 1
    assert len(adapter.sent) == 2


async def test_switching_the_digest_off_silences_it(db, session):
    user = await linked(session, digest_enabled=False, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await session.commit()

    loop = ReminderLoop(db, SpyAdapter(), MemoryStateStore())
    assert await loop.tick(now=at_hour(21), today=DAY) == 0


async def test_a_quiet_day_produces_nothing_at_all(db, session):
    await linked(session, digest_hour=21)
    await session.commit()

    loop = ReminderLoop(db, SpyAdapter(), MemoryStateStore())
    assert await loop.tick(now=at_hour(21), today=DAY) == 0


# ------------------------------------------------------------- due warnings
async def test_an_installment_warning_does_not_wait_for_the_digest_hour(db, session):
    """A due date does not care what time it is."""
    user = await linked(session, digest_enabled=False, reminder_days=3)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LoanService(session).create(
        book.id, user.id, "وام مسکن", 2_000_000, 24, NEXT_DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())

    assert await loop.tick(now=at_hour(11), today=DAY) == 1
    assert "وام مسکن" in adapter.sent[0][1]


async def test_a_warning_is_also_only_sent_once_a_day(db, session):
    user = await linked(session, digest_enabled=False)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LoanService(session).create(
        book.id, user.id, "وام", 1_000, 6, NEXT_DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())
    day = DAY

    assert await loop.tick(now=at_hour(9), today=day) == 1
    assert await loop.tick(now=at_hour(10), today=day) == 0


async def test_the_users_own_warning_window_is_honoured(db, session):
    """One person wants three days' notice, another wants ten."""
    user = await linked(session, digest_enabled=False, reminder_days=1)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LoanService(session).create(
        book.id, user.id, "وام", 1_000, 6, date(2026, 9, 1)
    )
    await session.commit()

    loop = ReminderLoop(db, SpyAdapter(), MemoryStateStore())
    assert await loop.tick(now=at_hour(9), today=DAY) == 0

    user.reminder_days = 30
    await session.commit()
    assert await loop.tick(now=at_hour(9), today=DAY) == 1


# ------------------------------------------------------------- addressing
async def test_a_reminder_goes_to_that_persons_own_chat(db, session):
    first = await linked(session, "اول", "aaa", digest_hour=21)
    second = await linked(session, "دوم", "bbb", digest_hour=21)

    books = BookService(session)
    ledger = LedgerService(session)
    for user in (first, second):
        book = await books.create_book(user.id, f"دفتر {user.display_name}", BookType.BUSINESS)
        await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100,
                            occurred_on=DAY)
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())
    await loop.tick(now=at_hour(21), today=DAY)

    addressed = {chat for chat, _ in adapter.sent}
    assert addressed == {"aaa", "bbb"}

    for chat, text in adapter.sent:
        other = "دوم" if chat == "aaa" else "اول"
        assert f"دفتر {other}" not in text


async def test_a_person_with_no_messenger_is_simply_skipped(db, session):
    user = await IdentityService(session).create_user("بی‌پیام‌رسان")
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await session.commit()

    loop = ReminderLoop(db, SpyAdapter(), MemoryStateStore())
    assert await loop.tick(now=at_hour(21), today=DAY) == 0


async def test_a_deactivated_account_is_not_messaged(db, session):
    user = await linked(session, digest_hour=21, is_active=False)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await session.commit()

    loop = ReminderLoop(db, SpyAdapter(), MemoryStateStore())
    assert await loop.tick(now=at_hour(21), today=DAY) == 0


# -------------------------------------------------------------- resilience
async def test_a_delivery_failure_does_not_stop_the_pass(db, session):
    user = await linked(session, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await session.commit()

    loop = ReminderLoop(db, SpyAdapter(fail=True), MemoryStateStore())
    assert await loop.tick(now=at_hour(21), today=DAY) == 0  # nothing sent


async def test_a_failed_send_is_not_retried_the_same_day(db, session):
    """Deliberate: a duplicate is worse than a gap.

    The send is recorded before it is attempted, so a failure costs one missed
    reminder rather than risking the same message arriving twice.
    """
    user = await linked(session, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await session.commit()

    state = MemoryStateStore()
    await ReminderLoop(db, SpyAdapter(fail=True), state).tick(
        now=at_hour(21), today=DAY
    )

    working = SpyAdapter()
    assert await ReminderLoop(db, working, state).tick(
        now=at_hour(21), today=DAY
    ) == 0
