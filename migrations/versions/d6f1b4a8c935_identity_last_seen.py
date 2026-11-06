"""When a messenger account last spoke to the bot.

One nullable column; nothing existing is touched.

Revision ID: d6f1b4a8c935
Revises: c5e9a3d71b24
Create Date: 2026-11-06 16:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6f1b4a8c935"
down_revision: Union[str, None] = "c5e9a3d71b24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "identities", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("identities", "last_seen_at")
