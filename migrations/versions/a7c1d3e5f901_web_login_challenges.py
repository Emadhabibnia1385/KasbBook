"""A browser can ask a messenger to vouch for it.

New table only, so nothing here touches populated rows.

Revision ID: a7c1d3e5f901
Revises: 9e632756c0e3
Create Date: 2026-11-05 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c1d3e5f901"
down_revision: Union[str, None] = "9e632756c0e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "web_login_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("poll_digest", sa.String(length=64), nullable=False),
        sa.Column("requester_ip", sa.String(length=64), nullable=True),
        sa.Column("requester_agent", sa.String(length=200), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_web_login_token", "web_login_challenges", ["token_digest"], unique=True)
    op.create_index("ix_web_login_poll", "web_login_challenges", ["poll_digest"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_web_login_poll", table_name="web_login_challenges")
    op.drop_index("ix_web_login_token", table_name="web_login_challenges")
    op.drop_table("web_login_challenges")
