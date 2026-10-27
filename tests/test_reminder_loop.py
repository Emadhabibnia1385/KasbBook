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

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from apps.bot.reminders import ReminderLoop, _local_hour  # noqa: E402
from kasbbook.bot.state import MemoryStateStore  # noqa: E402
from kasbbook.modules.books.models import BookType  # noqa: E402
from kasbbook.modules.books.service import BookService  # noqa: E402
from kasbbook.modules.debts.models import Direction  # noqa: E402
from kasbbook.modules.debts.service import DebtService  # noqa: E402
from kasbbook.modules.identity.models import Provider  # noqa: E402
from kasbbook.modules.identity.service import IdentityService  # noqa: E402
from kasbbook.modules.ledger.models import Flow, Scope  # noqa: E402
from kasbbook.modules.ledger.service import LedgerService  # noqa: E402
from kasbbook.modules.loans.service import LoanService  # noqa: E402
from kasbbook.shared import jalali  # noqa: E402

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
async def test_the_day_a_reminder_belongs_to_is_the_persons_own_not_the_servers(db, session):
    """The server's date turns over at half past three in the morning in Tehran.

    Everything said to a person is dated and deduplicated on *their* day. On
    the server's, one Tehran day carried two keys — and a second key is a
    second copy of the same message — while the figures were read from whatever
    day the server happened to be on, which for those hours is yesterday.
    """
    user = await linked(session, digest_hour=0, timezone="Asia/Tehran")
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 250_000, occurred_on=NEXT_DAY
    )
    await session.commit()

    # 00:30 in Tehran on the 25th: the server is still on the 24th.
    just_after_midnight = datetime(2026, 8, 24, 21, 0, tzinfo=ZoneInfo("UTC"))
    # 04:00 in Tehran on the same 25th, and now the server agrees on the date.
    once_the_server_agrees = datetime(2026, 8, 25, 0, 30, tzinfo=ZoneInfo("UTC"))

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())

    # No `today` here on purpose: this is the path production actually runs.
    assert await loop.tick(now=just_after_midnight) == 1
    assert "250,000" in adapter.sent[0][1]
    assert jalali.to_text(NEXT_DAY) in adapter.sent[0][1]

    # The server's date rolling over is not a new day for this person.
    assert await loop.tick(now=once_the_server_agrees) == 0
    assert len(adapter.sent) == 1


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
async def test_a_warning_waits_for_the_hour_the_person_chose(db, session):
    """A due date does not care what time it is. The person does.

    The warnings used to go out on the first tick of the *server's* day, which
    is half past three in the morning in Tehran — every day, to a shopkeeper
    who had asked to be spoken to at nine in the evening. Three days of notice
    is what `reminder_days` is for; none of it is spent by waiting for a civil
    hour.
    """
    user = await linked(session, digest_enabled=False, reminder_days=3, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LoanService(session).create(
        book.id, user.id, "وام مسکن", 2_000_000, 24, NEXT_DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())

    assert await loop.tick(now=at_hour(4), today=DAY) == 0
    assert await loop.tick(now=at_hour(21), today=DAY) == 1
    assert "وام مسکن" in adapter.sent[0][1]


async def test_a_tick_missed_at_the_chosen_hour_still_speaks_later_that_day(db, session):
    """At or after the hour, not on it.

    One slow tick at 21:00 — a long recurring catch-up, a restart — used to
    cost the whole day's digest, silently. The once-a-day key still holds it
    to one message.
    """
    user = await linked(session, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())

    assert await loop.tick(now=at_hour(23), today=DAY) == 1
    assert await loop.tick(now=at_hour(23), today=DAY) == 0


async def test_everything_due_reaches_the_person_as_one_message(db, session):
    """Three notifications in the same minute is noise, whatever they say."""
    user = await linked(session, digest_hour=21)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 100, occurred_on=DAY
    )
    await DebtService(session).create(
        book.id, user.id, "علی", Direction.OWED_TO_ME, 500_000, due_on=NEXT_DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    assert await ReminderLoop(db, adapter, MemoryStateStore()).tick(
        now=at_hour(21), today=DAY
    ) == 1
    text = adapter.sent[0][1]
    assert "خلاصهٔ" in text and "علی" in text


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

    assert await loop.tick(now=at_hour(21), today=day) == 1
    assert await loop.tick(now=at_hour(22), today=day) == 0


async def test_the_users_own_warning_window_is_honoured(db, session):
    """One person wants three days' notice, another wants ten."""
    user = await linked(session, digest_enabled=False, reminder_days=1)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LoanService(session).create(
        book.id, user.id, "وام", 1_000, 6, date(2026, 9, 1)
    )
    await session.commit()

    loop = ReminderLoop(db, SpyAdapter(), MemoryStateStore())
    assert await loop.tick(now=at_hour(21), today=DAY) == 0

    user.reminder_days = 30
    await session.commit()
    assert await loop.tick(now=at_hour(21), today=DAY) == 1


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


# ---------------------------------------------------------------- recurring
async def test_the_loop_books_recurring_rules_that_came_due(db, session):
    """Rent defined once is booked when due — by this loop, which nothing did before.

    `RecurringService.run_due` existed, was tested, and had no caller, so not
    one recurring rule had ever been booked on a running bot.
    """
    from kasbbook.modules.recurring.models import Period
    from kasbbook.modules.recurring.service import RecurringService

    user = await linked(session, digest_enabled=False)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await RecurringService(session).create(
        book.id, user.id, Flow.EXPENSE, "اجاره", 9_000_000, Period.MONTHLY, DAY
    )
    await session.commit()

    adapter = SpyAdapter()
    assert await ReminderLoop(db, adapter, MemoryStateStore()).tick(
        now=at_hour(11), today=DAY
    ) == 0                                   # on time: the digest will show it

    async for check in db.session():
        rows = await LedgerService(check).transactions(book.id, user.id)
        assert [(r.category, r.converted_amount, r.occurred_on) for r in rows] == [
            ("اجاره", 9_000_000, DAY)
        ]
        assert await LedgerService(check).trial_balance(book.id) == (9_000_000, 9_000_000)


async def test_a_late_catch_up_is_told_to_the_owner_once(db, session):
    from datetime import timedelta

    from kasbbook.modules.recurring.models import Period
    from kasbbook.modules.recurring.service import RecurringService

    user = await linked(session, digest_enabled=False)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await RecurringService(session).create(
        book.id, user.id, Flow.EXPENSE, "قهوه", 100, Period.DAILY, DAY - timedelta(days=2)
    )
    await session.commit()

    adapter = SpyAdapter()
    loop = ReminderLoop(db, adapter, MemoryStateStore())
    assert await loop.tick(now=at_hour(11), today=DAY) == 1
    chat, text = adapter.sent[0]
    assert chat == "555001"
    assert "مغازه" in text and "قهوه" in text and "ثبت شد" in text

    # Nothing new came due, so nothing more is said.
    assert await loop.tick(now=at_hour(12), today=DAY) == 0


async def test_recurring_booking_switched_off_books_nothing_and_loses_nothing(db, session):
    """KASBBOOK_RECURRING=off holds rules where they are; on catches them all up."""
    from datetime import timedelta

    from kasbbook.modules.recurring.models import Period
    from kasbbook.modules.recurring.service import RecurringService

    user = await linked(session, digest_enabled=False)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await RecurringService(session).create(
        book.id, user.id, Flow.EXPENSE, "قهوه", 100, Period.DAILY, DAY - timedelta(days=2)
    )
    await session.commit()

    held = SpyAdapter()
    assert await ReminderLoop(db, held, MemoryStateStore(), book_recurring=False).tick(
        now=at_hour(11), today=DAY) == 0
    async for check in db.session():
        assert await LedgerService(check).transactions(book.id, user.id) == []

    resumed = SpyAdapter()
    assert await ReminderLoop(db, resumed, MemoryStateStore()).tick(
        now=at_hour(11), today=DAY) == 1
    async for check in db.session():
        assert len(await LedgerService(check).transactions(book.id, user.id)) == 3


async def test_a_long_catch_up_is_summarised_per_rule_and_fits_one_message(db, session):
    """A daily rule a year behind is one line, not 365 — or the send fails outright."""
    from datetime import timedelta

    from kasbbook.modules.recurring.models import Period
    from kasbbook.modules.recurring.service import MAX_CATCH_UP, RecurringService

    user = await linked(session, digest_enabled=False)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await RecurringService(session).create(
        book.id, user.id, Flow.EXPENSE, "قهوه", 100, Period.DAILY,
        DAY - timedelta(days=MAX_CATCH_UP - 1),
    )
    await session.commit()

    adapter = SpyAdapter()
    assert await ReminderLoop(db, adapter, MemoryStateStore()).tick(
        now=at_hour(11), today=DAY) == 1
    text = adapter.sent[0][1]
    # Telegram's limit is 4096 characters; Bale and Rubika's are no larger.
    assert len(text) < 1000
    assert f"{MAX_CATCH_UP - 1} بار" in text      # the late ones; today's is on time
    assert f"جمع {(MAX_CATCH_UP - 1) * 100:,}" in text


async def test_the_preview_reports_the_run_and_writes_nothing(db, session):
    from datetime import timedelta

    from apps.bot.recurring_preview import preview
    from kasbbook.modules.recurring.models import Period, RecurringRule
    from kasbbook.modules.recurring.service import RecurringService

    user = await linked(session, digest_enabled=False)
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    rule = await RecurringService(session).create(
        book.id, user.id, Flow.EXPENSE, "قهوه", 100, Period.DAILY, DAY - timedelta(days=2)
    )
    await session.commit()
    start = rule.next_run_on

    report = await preview(db, DAY)

    assert "would book: قهوه expense 100 x3" in report
    assert "Total: 3 transaction(s) booked" in report
    async for check in db.session():
        assert await LedgerService(check).transactions(book.id, user.id) == []
        assert await LedgerService(check).trial_balance(book.id) == (0, 0)
        assert (await check.get(RecurringRule, rule.id)).next_run_on == start


@pytest.mark.parametrize("raw,expected", [
    (None, True), ("on", True), ("ON", True), ("off", False), ("0", False), (" no ", False),
])
async def test_the_recurring_switch_reads_the_way_people_write_it(monkeypatch, raw, expected):
    from kasbbook.shared.settings import Settings

    if raw is None:
        monkeypatch.delenv("KASBBOOK_RECURRING", raising=False)
    else:
        monkeypatch.setenv("KASBBOOK_RECURRING", raw)
    assert Settings.from_env().recurring_booking is expected
