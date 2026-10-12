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


async def _attempt(database: Database, work) -> bool:
    """Run `work(session)` in its own session; True if it committed."""
    from kasbbook.shared.errors import KasbBookError

    async for session in database.session():
        try:
            await work(session)
            await session.commit()
            return True
        except KasbBookError:
            await session.rollback()
            return False


@needs_postgres
async def test_two_conversions_cannot_spend_the_same_tokens(pg):
    """Ten USDT, two conversions of six in flight: one wins, the wallet never goes below zero."""
    from kasbbook.modules.exchange.service import ExchangeService
    from kasbbook.modules.ledger.models import Scope

    async for session in pg.session():
        user = await IdentityService(session).create_user("عماد")
        book = await BookService(session).create_book(user.id, "کارگاه", BookType.BUSINESS, "IRT")
        await ExchangeService(session).set_enabled(user.id, book.id, "USDT", True)
        await LedgerService(session).record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش",
                                            "10", currency="USDT", conversion_rate="100000")
        await session.commit()
        user_id, book_id = user.id, book.id

    async def convert(session):
        await ExchangeService(session).convert(user_id, book_id, "USDT", "6", "IRT", "600000")

    results = await asyncio.gather(*(_attempt(pg, convert) for _ in range(2)))

    assert sorted(results) == [False, True]
    async for session in pg.session():
        assert await ExchangeService(session).balance_of(book_id, "USDT") == Decimal("4.0000")


@needs_postgres
async def test_two_payments_cannot_both_settle_one_payslip(pg):
    from kasbbook.modules.books.models import Role
    from kasbbook.modules.ledger.models import Scope
    from kasbbook.modules.payroll.models import ShareBasis
    from kasbbook.modules.payroll.service import PayrollService

    day = date(2026, 8, 24)
    async for session in pg.session():
        identity = IdentityService(session)
        owner = await identity.create_user("عماد")
        member = await identity.create_user("سارا")
        books = BookService(session)
        book = await books.create_book(owner.id, "تیم", BookType.TEAM)
        await books.add_member(owner.id, book.id, member.id, Role.MEMBER)
        await LedgerService(session).record(book.id, owner.id, Flow.INCOME, Scope.TEAM,
                                            "پروژه", "1000", occurred_on=day)
        payroll = PayrollService(session)
        await payroll.set_share(book.id, owner.id, member.id, ShareBasis.PERCENT, 100,
                                effective_from=day)
        period = await payroll.open_period(owner.id, book.id, "مرداد", day, day)
        slip = (await payroll.calculate(owner.id, period.id))[0]
        await session.commit()
        owner_id, slip_id = owner.id, slip.id

    async def pay(session):
        await PayrollService(session).pay(owner_id, slip_id, "1000")

    results = await asyncio.gather(*(_attempt(pg, pay) for _ in range(2)))

    assert sorted(results) == [False, True]


@needs_postgres
async def test_concurrent_retries_with_one_key_book_one_transaction(pg):
    """The client's retry arrives while the first request is still in flight."""
    from httpx import ASGITransport, AsyncClient

    from kasbbook.api.app import create_app
    from kasbbook.api.ratelimit import MemoryRateLimiter
    from kasbbook.shared.settings import Settings

    settings = Settings(database_url=POSTGRES_URL,
                        api_secret_key="a-test-signing-key-that-is-long-enough-to-be-real")
    app = create_app(settings=settings, database=pg, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
        async with app.router.lifespan_context(app):
            tokens = (await api.post("/api/v1/auth/register", json={
                "display_name": "Emad", "email": "race@example.com",
                "password": "a-good-password"})).json()
            headers = {"Authorization": f"Bearer {tokens['access_token']}",
                       "Idempotency-Key": "race-retry-0001"}
            book = (await api.post("/api/v1/books", headers=headers,
                                   json={"name": "shop", "type": "business"})).json()
            url = f"/api/v1/books/{book['id']}/transactions"
            body = {"flow": "income", "category": "sale", "amount": "250000"}

            replies = await asyncio.gather(*(api.post(url, headers=headers, json=body)
                                             for _ in range(4)))

    codes = sorted(r.status_code for r in replies)
    # One did the work; each other either waited and got its answer back, or
    # was told the first was still running. None booked a second time.
    assert codes.count(201) >= 1 and set(codes) <= {201, 409}, codes
    async for session in pg.session():
        from sqlalchemy import func, select

        from kasbbook.modules.ledger.models import Transaction
        count = await session.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.book_id == uuid.UUID(book["id"])))
        assert count == 1
        assert await LedgerService(session).trial_balance(uuid.UUID(book["id"])) == (
            Decimal("250000"), Decimal("250000"))
