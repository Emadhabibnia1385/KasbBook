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

# The whole registry, so `create_all` builds every table no matter which test
# file is running. Without it a single-file run only creates the tables that
# file happened to import, and the same test passes in a full run and fails on
# its own — which is the confusing direction for that to break in.
from kasbbook.models import Base  # noqa: E402

# Imported for the side effect, and named here so the linter reads the intent
# rather than a comment it ignores. Same reason src/kasbbook/models.py
# declares one.
__all__ = ["Base"]


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
