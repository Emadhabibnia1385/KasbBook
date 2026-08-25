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
    """Autogenerate against the migrated database must find nothing to do.

    Run with the real `compare_type` hook from env.py, not with type comparison
    switched off, because that hook is itself a thing that can break. `Money`
    is a TypeDecorator over Numeric(28, 4); comparing the decorator class
    against the NUMERIC read back from the database reported a type change for
    every money column in the schema, on every autogenerate run. Thirty of
    them. On PostgreSQL each becomes an ALTER COLUMN TYPE that rewrites a whole
    table to the type it already has.

    Switching comparison off hides that, and hides a genuine type change too.
    """
    from migrations.comparators import compare_type

    sync_url, _ = migrated_db
    engine = create_engine(sync_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": compare_type}
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    changed = [
        entry
        for entry in diff
        if isinstance(entry, tuple)
        and entry[0] in ("add_table", "remove_table", "add_column", "remove_column")
    ]
    assert not changed, f"models and migration disagree: {changed}"

    # A type diff now means a real one, so it is no longer filtered away.
    retyped = [entry for entry in diff if isinstance(entry, tuple) and entry[0] == "modify_type"]
    assert not retyped, f"phantom or real type changes: {retyped}"


def test_money_is_not_reported_as_a_type_change(migrated_db):
    """The hook has to say 'unchanged' for Money over the NUMERIC it compiles to.

    Written against the hook directly rather than through autogenerate, so the
    thing being asserted is the rule itself.
    """
    import sqlalchemy as sa

    from migrations.comparators import compare_type
    from kasbbook.shared.money import Money

    same = compare_type(
        None, None, None, sa.Numeric(precision=28, scale=4), Money()
    )
    assert same is False, "Money over NUMERIC(28,4) is not a change"

    # A genuinely different scale still has to be reported.
    different = compare_type(
        None, None, None, sa.Numeric(precision=28, scale=2), Money()
    )
    assert different is True, "a changed scale must not be swallowed"

    # Anything that is not Money is left to Alembic's own judgement.
    assert compare_type(
        None, None, None, sa.String(10), sa.String(20)
    ) is None


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


def test_alembic_loads_the_new_package_and_not_the_legacy_one():
    """`kasbbook` names two packages, and only one of them is this project.

    The first-generation bot still sits at the repo root under the same name.
    Whichever path comes first in sys.path wins, and the loser is silent: the
    old package imports python-telegram-bot, which is no longer a dependency,
    so a wrong order shows up as ModuleNotFoundError for a module nobody
    mentioned. It has already happened twice — once in the service unit, once
    in env.py.

    Alembic is run here the way a deploy runs it, in its own process, because
    the failure is entirely about import order.
    """
    import subprocess

    database = REPO / ".test_import_order.db"
    database.unlink(missing_ok=True)
    environment = dict(os.environ)
    environment["KASBBOOK_DATABASE_URL"] = f"sqlite+aiosqlite:///{database}"

    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(REPO), env=environment, capture_output=True, text=True, timeout=180,
        )
    finally:
        database.unlink(missing_ok=True)

    combined = result.stdout + result.stderr
    assert "No module named 'telegram'" not in combined, (
        "the legacy package shadowed src/kasbbook:\n" + combined[-800:]
    )
    assert result.returncode == 0, combined[-800:]
