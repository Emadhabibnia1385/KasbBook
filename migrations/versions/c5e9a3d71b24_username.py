"""A username for the web login, and a flag for guest accounts.

Two new columns on users (one nullable, one defaulted) and a unique index; nothing existing is touched.

Revision ID: c5e9a3d71b24
Revises: b4d8e2f1a703
Create Date: 2026-11-06 14:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5e9a3d71b24"
down_revision: Union[str, None] = "b4d8e2f1a703"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.add_column(
        "users",
        sa.Column("is_guest", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "is_guest")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
