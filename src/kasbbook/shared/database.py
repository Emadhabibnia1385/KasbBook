"""Async database access.

PostgreSQL is the production target; SQLite is used only by the test suite, so
every column type here has to behave identically on both. `sqlalchemy.Uuid` and
`Numeric` do — native on PostgreSQL, emulated on SQLite — which is why money
never touches a float anywhere in this codebase.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import AsyncIterator, Optional

from sqlalchemy import DateTime, MetaData, Uuid, event, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming so Alembic autogenerate produces stable, reviewable names
# instead of database-assigned ones that differ between engines.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKey:
    """A UUID primary key.

    Internal ids are UUIDs on purpose: a Telegram user id, a phone number or an
    email must never be the identity of an account, because any of them can be
    detached from it later.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class Database:
    """Owns the engine and hands out sessions.

    Kept as an object rather than module globals so tests can spin up an
    isolated database per test without touching process-wide state.
    """

    def __init__(self, url: str, echo: bool = False) -> None:
        self._engine = create_async_engine(url, echo=echo, future=True)

        if url.startswith("sqlite"):
            # SQLite ships with foreign keys switched OFF, per connection.
            # Without this the test suite enforces none of them: a CASCADE
            # never fires, a RESTRICT never refuses, and orphaned rows are
            # left behind silently. PostgreSQL enforces all of it, so the
            # tests would be describing a database that is not the one in
            # production — which is exactly how the NOT NULL migration bug
            # reached it.
            @event.listens_for(self._engine.sync_engine, "connect")
            def _enforce_foreign_keys(connection, record):  # pragma: no cover
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    @property
    def engine(self):
        return self._engine

    async def create_all(self) -> None:
        """Only for tests. Production schema comes from Alembic migrations."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            yield session
