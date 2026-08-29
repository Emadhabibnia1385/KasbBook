"""Alembic environment.

The database URL comes from KASBBOOK_DATABASE_URL so the same migrations run
against a developer's throwaway database and against production without editing
a file that is under version control.
"""

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

import sqlalchemy as sa
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

ROOT = Path(__file__).resolve().parents[1]

# Alembic runs this file directly: src/ for `kasbbook`, the repo root for
# `migrations.comparators`.
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from kasbbook.models import Base  # noqa: E402
from migrations.comparators import compare_type  # noqa: E402

config = context.config
if config.config_file_name is not None:
    # `disable_existing_loggers` defaults to True, which switches off every
    # logger that already exists. That is invisible when alembic runs as its
    # own process, and silently fatal when something runs it in-process: the
    # application stops logging entirely and nothing says why. A test that
    # asserted a webhook was logged is what found this.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

url = os.environ.get("KASBBOOK_DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        render_item=render_item,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=compare_type,
    )
    with context.begin_transaction():
        context.run_migrations()


def render_item(type_, obj, autogen_context):
    """Render application types as plain SQLAlchemy ones.

    A migration is a historical record: it must keep applying years from now,
    after the class it was generated from has been renamed or moved. Emitting
    `sa.Numeric` instead of `kasbbook.shared.money.Money` keeps every migration
    self-contained.
    """
    if type_ == "type" and obj.__class__.__name__ == "Money":
        return "sa.Numeric(precision=28, scale=4)"
    return False  # fall back to Alembic's own rendering


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=render_item,
        compare_type=compare_type,
        # Needed for SQLite, harmless elsewhere: it lets ALTER-style changes
        # rebuild a table instead of failing.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
