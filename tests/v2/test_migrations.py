"""The migration and the models must describe the same database.

The failure this guards against is quiet: someone adds a column to a model, the
tests pass because they build the schema straight from metadata, and the change
only surfaces in production where the schema comes from a migration that never
got the column. Comparing the two here turns that into a failing build.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kasbbook.models import Base  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _alembic_config(sync_url: str) -> Config:
    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "migrations"))
    config.set_main_option("sqlalchemy.url", sync_url)
    return config


@pytest.fixture
def migrated_db():
    """A database built the way production builds one: by running migrations."""
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)

    sync_url = f"sqlite:///{path}"
    previous = os.environ.get("KASBBOOK_DATABASE_URL")
    # env.py prefers the environment; point it at the same file.
    os.environ["KASBBOOK_DATABASE_URL"] = f"sqlite+aiosqlite:///{path}"
    try:
        command.upgrade(_alembic_config(sync_url), "head")
        yield sync_url, path
    finally:
        if previous is None:
            os.environ.pop("KASBBOOK_DATABASE_URL", None)
        else:
            os.environ["KASBBOOK_DATABASE_URL"] = previous
        os.unlink(path)


def test_the_migration_creates_every_table_the_models_declare(migrated_db):
    sync_url, _ = migrated_db
    engine = create_engine(sync_url)
    try:
        actual = set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()

    expected = set(Base.metadata.tables)
    assert expected - actual == set(), f"the migration is missing {expected - actual}"
    assert actual - expected == set(), f"the migration creates extra {actual - expected}"


def test_the_migration_and_the_models_have_not_drifted(migrated_db):
    """Autogenerate against the migrated database must find nothing to do."""
    sync_url, _ = migrated_db
    engine = create_engine(sync_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": False}
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    # Index ordering and SQLite's looser types produce noise; a real drift is a
    # added/removed table or column, which is what this looks for.
    real = [
        entry
        for entry in diff
        if isinstance(entry, tuple)
        and entry[0] in ("add_table", "remove_table", "add_column", "remove_column")
    ]
    assert not real, f"models and migration disagree: {real}"


def test_the_migration_rolls_all_the_way_back(migrated_db):
    sync_url, _ = migrated_db
    command.downgrade(_alembic_config(sync_url), "base")

    engine = create_engine(sync_url)
    try:
        left = set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()

    assert left == set(), f"downgrade left {left} behind"


def test_migrations_do_not_import_application_code():
    """A migration is history: it must still run after the app is refactored."""
    for script in (REPO / "migrations" / "versions").glob("*.py"):
        source = script.read_text(encoding="utf-8")
        assert "kasbbook" not in source, f"{script.name} depends on application code"


def test_money_columns_keep_their_precision():
    """A bare NUMERIC would silently round rials away on PostgreSQL."""
    versions = list((REPO / "migrations" / "versions").glob("*.py"))
    assert versions, "no migration has been generated"

    source = "\n".join(p.read_text(encoding="utf-8") for p in versions)
    assert "sa.Numeric(precision=28, scale=4)" in source
