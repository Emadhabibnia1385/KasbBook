"""The activity log: who did what, when, and through what.

Revision ID: l5b9d2e8f703
Revises: k4a8c1d7e692
Create Date: 2026-11-08 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l5b9d2e8f703"
down_revision: Union[str, None] = "k4a8c1d7e692"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_events",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("via", sa.String(length=8), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_user_time", "activity_events", ["user_id", "created_at"])
    op.create_index("ix_activity_book_time", "activity_events", ["book_id", "created_at"])
    op.create_index("ix_activity_category_time", "activity_events", ["category", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_activity_category_time", table_name="activity_events")
    op.drop_index("ix_activity_book_time", table_name="activity_events")
    op.drop_index("ix_activity_user_time", table_name="activity_events")
    op.drop_table("activity_events")
