"""Adjustments are decided by whoever records them; nothing is left pending.

Revision ID: n7d1f4a0b925
Revises: m6c0e3f9a814
Create Date: 2026-11-08 20:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "n7d1f4a0b925"
down_revision: Union[str, None] = "m6c0e3f9a814"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pending ones never held back any amount (every adjustment already counted); they only said
    # "waiting". They now say who decided and when, as every new one does.
    op.execute(
        "UPDATE adjustments SET approved_at = created_at, approved_by = recorded_by "
        "WHERE approved_at IS NULL"
    )


def downgrade() -> None:
    # Nothing to restore: which ones were once pending is not worth keeping.
    pass
