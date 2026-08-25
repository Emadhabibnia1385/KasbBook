"""Migrations, rehearsed on PostgreSQL with the tables already populated.

This file exists because of a specific bug. `ALTER TABLE ... ADD COLUMN NOT
NULL` is fine on an empty table and fine on SQLite, which rebuilds the table in
batch mode and applies the Python-side default. On PostgreSQL, against a table
that already has rows, it raises NotNullViolationError — and the only place that
combination occurs is production.

So this walks the revisions one at a time and seeds a row after each, which is
the shape production actually has when the next migration arrives.

Skipped unless KASBBOOK_TEST_POSTGRES_URL is set, so a laptop without Postgres
still runs the rest of the suite.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kasbbook.models import Base  # noqa: E402

RAW_URL = os.environ.get("KASBBOOK_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not RAW_URL,
    reason="set KASBBOOK_TEST_POSTGRES_URL to rehearse migrations on PostgreSQL",
)


def _sync_url() -> str:
    return RAW_URL.replace("+asyncpg", "").replace("postgresql+psycopg", "postgresql")


def _async_url() -> str:
    return RAW_URL if "+" in RAW_URL else RAW_URL.replace(
        "postgresql://", "postgresql+asyncpg://"
    )


def _config() -> Config:
    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "migrations"))
    config.set_main_option("sqlalchemy.url", _sync_url())
    return config


@pytest.fixture
def clean_database():
    """An empty schema, restored empty afterwards."""
    os.environ["KASBBOOK_DATABASE_URL"] = _async_url()
    engine = create_engine(_sync_url())

    def wipe():
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))

    wipe()
    try:
        yield engine
    finally:
        wipe()
        engine.dispose()


def _revisions():
    script = ScriptDirectory.from_config(_config())
    return list(reversed([revision.revision for revision in script.walk_revisions()]))


def _seed(engine) -> None:
    """Put a row in every table a later migration might have to alter.

    An empty table hides exactly the failure this file is here to catch.
    """
    tables = set(inspect(engine).get_table_names())
    if "users" not in tables:
        return

    with engine.begin() as connection:
        already = connection.execute(text("SELECT count(*) FROM users")).scalar()
        if already:
            return

        connection.execute(
            text(
                "INSERT INTO users (id, display_name, locale, timezone, is_active,"
                " created_at, updated_at)"
                " VALUES (:id, 'seed', 'fa', 'Asia/Tehran', true, now(), now())"
            ),
            {"id": str(uuid.uuid4())},
        )


def test_every_migration_applies_to_a_table_that_already_has_rows(clean_database):
    """The rehearsal that would have caught the notification-preferences bug."""
    engine = clean_database
    config = _config()

    for revision in _revisions():
        command.upgrade(config, revision)
        # Production is never empty when the next migration arrives.
        _seed(engine)

    with engine.connect() as connection:
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
    assert version == _revisions()[-1]


def test_the_seeded_row_survives_every_migration(clean_database):
    """A migration that drops data would pass a schema check and fail people."""
    engine = clean_database
    config = _config()

    for revision in _revisions():
        command.upgrade(config, revision)
        _seed(engine)

    with engine.connect() as connection:
        survivors = connection.execute(
            text("SELECT count(*) FROM users WHERE display_name = 'seed'")
        ).scalar()
    assert survivors >= 1


def test_new_columns_have_a_value_for_rows_that_predate_them(clean_database):
    """A NOT NULL column added later must not leave old rows unreadable."""
    engine = clean_database
    config = _config()

    for revision in _revisions():
        command.upgrade(config, revision)
        _seed(engine)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT digest_enabled, digest_hour, reminder_days"
                " FROM users WHERE display_name = 'seed' LIMIT 1"
            )
        ).one()

    assert row.digest_enabled is not None
    assert row.digest_hour is not None
    assert row.reminder_days is not None


def test_the_schema_matches_the_models_on_postgres(clean_database):
    """SQLite is forgiving about types; PostgreSQL is not."""
    engine = clean_database
    command.upgrade(_config(), "head")

    actual = set(inspect(engine).get_table_names()) - {"alembic_version"}
    expected = set(Base.metadata.tables)

    assert expected - actual == set(), f"missing on postgres: {expected - actual}"
    assert actual - expected == set(), f"unexpected on postgres: {actual - expected}"


def test_money_columns_are_numeric_with_the_right_scale(clean_database):
    """A float column would round rials away, quietly and forever."""
    engine = clean_database
    command.upgrade(_config(), "head")

    with engine.connect() as connection:
        wrong = connection.execute(
            text(
                "SELECT table_name, column_name, data_type"
                " FROM information_schema.columns"
                " WHERE column_name IN ('amount','converted_amount','original_amount',"
                " 'debit','credit','installment_amount')"
                " AND (data_type <> 'numeric' OR numeric_scale <> 4)"
            )
        ).all()

    assert not wrong, f"money stored imprecisely: {wrong}"


def test_migrations_roll_all_the_way_back_on_postgres(clean_database):
    engine = clean_database
    config = _config()

    command.upgrade(config, "head")
    _seed(engine)
    command.downgrade(config, "base")

    left = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert left == set(), f"downgrade left {left} behind"
