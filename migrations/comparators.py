"""How autogenerate decides whether a column type really changed.

Kept out of env.py because env.py only runs under Alembic — it reads
`context.config` at import time — and a rule this consequential should be
testable on its own.
"""

from __future__ import annotations

import sqlalchemy as sa


def compare_type(
    context, inspected_column, metadata_column, inspected_type, metadata_type
):
    """True when the type changed, False when it did not, None to let Alembic decide.

    `Money` is a TypeDecorator over Numeric(28, 4). Alembic compares the
    decorator against the NUMERIC it reads back from the database, sees two
    different classes, and reports a change — for every money column in the
    schema, on every autogenerate run.

    Those diffs are not harmless noise. On PostgreSQL each one becomes an
    ALTER COLUMN TYPE that rewrites the whole table to the type it already has.
    Comparing what Money actually *is* removes them, while still reporting a
    genuine change of precision or scale.
    """
    from kasbbook.shared.money import Money

    if isinstance(metadata_type, Money):
        return not (
            isinstance(inspected_type, sa.Numeric)
            and inspected_type.precision == metadata_type.impl.precision
            and inspected_type.scale == metadata_type.impl.scale
        )
    return None
