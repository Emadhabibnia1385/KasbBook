"""Races that only a real Redis or a real PostgreSQL can lose.

SQLite is single-writer and the in-memory state store runs on one event loop,
so the suite above cannot show two workers stepping on each other: it can only
show that the code *intends* not to. These run the same operations against
the real services, concurrently, and count what was written.

Skipped unless the service is named, the same way the migration rehearsal is:

    KASBBOOK_TEST_REDIS_URL=redis://127.0.0.1:6379/15
    KASBBOOK_TEST_POSTGRES_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/kasbbook_test

Both are wiped: point them at a scratch database, never a real one.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from kasbbook.bot.state import RedisStateStore
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.recurring.models import Period
from kasbbook.modules.recurring.service import RecurringService
from kasbbook.shared.database import Database

pytestmark = pytest.mark.asyncio

REDIS_URL = os.environ.get("KASBBOOK_TEST_REDIS_URL", "")
POSTGRES_URL = os.environ.get("KASBBOOK_TEST_POSTGRES_URL", "")

needs_redis = pytest.mark.skipif(not REDIS_URL, reason="set KASBBOOK_TEST_REDIS_URL")
needs_postgres = pytest.mark.skipif(not POSTGRES_URL, reason="set KASBBOOK_TEST_POSTGRES_URL")


# ------------------------------------------------------------------- redis
@pytest.fixture
async def redis_store():
    import redis.asyncio as aioredis

    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    prefix = f"kasbbook:test:{uuid.uuid4().hex}:"
    try:
        yield RedisStateStore(client, prefix=prefix)
    finally:
        keys = [key async for key in client.scan_iter(f"{prefix}*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


@needs_redis
async def test_only_one_of_many_concurrent_pops_gets_the_draft(redis_store):
    """The double tap, at the store: of every claim in flight, exactly one wins."""
    await redis_store.set("chat", {"flow": "quick", "amount": "100"})

    results = await asyncio.gather(*(redis_store.pop("chat") for _ in range(50)))

    winners = [result for result in results if result]
    assert winners == [{"flow": "quick", "amount": "100"}]
    assert await redis_store.get("chat") == {}


@needs_redis
async def test_pop_of_nothing_is_empty_and_set_still_expires(redis_store):
    assert await redis_store.pop("never-set") == {}

    await redis_store.set("short", {"a": 1}, ttl=1)
    assert await redis_store.get("short") == {"a": 1}
    await asyncio.sleep(1.5)
    assert await redis_store.get("short") == {}


# ---------------------------------------------------------------- postgres
@pytest.fixture
async def pg():
    from sqlalchemy import text

    database = Database(POSTGRES_URL)
    async with database._engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await database.create_all()
    try:
        yield database
    finally:
        async with database._engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        await database.dispose()


async def _run_and_commit(database: Database, until: date) -> int:
    async for session in database.session():
        run = await RecurringService(session).run_due(until=until)
        await session.commit()
        return len(run.booked)


@needs_postgres
async def test_two_reminder_loops_never_book_the_same_date_twice(pg):
    """Each messenger's process runs its own loop; both reach the same rules.

    Without the row lock both read `next_run_on`, both book the backlog, and
    every date is in the books twice.
    """
    day = date(2026, 8, 24)
    async for session in pg.session():
        user = await IdentityService(session).create_user("عماد")
        books = []
        for index in range(5):
            book = await BookService(session).create_book(user.id, f"دفتر {index}",
                                                          BookType.BUSINESS)
            await RecurringService(session).create(
                book.id, user.id, Flow.EXPENSE, "قهوه", 100, Period.DAILY,
                day - timedelta(days=9),
            )
            books.append(book)
        await session.commit()
        user_id = user.id

    booked = await asyncio.gather(*(_run_and_commit(pg, day) for _ in range(4)))

    assert sum(booked) == 5 * 10
    async for session in pg.session():
        ledger = LedgerService(session)
        for book in books:
            rows = await ledger.transactions(book.id, user_id)
            assert len(rows) == 10
            assert len({row.occurred_on for row in rows}) == 10
            assert await ledger.trial_balance(book.id) == (Decimal("1000"), Decimal("1000"))
