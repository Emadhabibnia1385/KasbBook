"""A team member added by name only, with no account yet.

Revision ID: m6c0e3f9a814
Revises: l5b9d2e8f703
Create Date: 2026-11-08 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m6c0e3f9a814"
down_revision: Union[str, None] = "l5b9d2e8f703"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_placeholder", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_placeholder")
