"""Test fixtures for the v2 core.

Each test gets its own in-memory database. SQLite is used here only — every
column type in the models behaves the same on PostgreSQL, which is what
production runs.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kasbbook.shared.database import Database  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db():
    # A named in-memory database shared across connections in this test only.
    database = Database("sqlite+aiosqlite://")
    await database.create_all()
    yield database
    await database.dispose()


@pytest.fixture
async def session(db):
    async for s in db.session():
        yield s
