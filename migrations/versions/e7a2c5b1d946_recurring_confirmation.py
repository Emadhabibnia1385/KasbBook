"""Recurring rules that ask first, and the due dates waiting for an answer.

A new column on recurring_rules (existing rules keep recording on their own) and a new table.

Revision ID: e7a2c5b1d946
Revises: d6f1b4a8c935
Create Date: 2026-11-06 17:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a2c5b1d946"
down_revision: Union[str, None] = "d6f1b4a8c935"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recurring_rules",
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="auto"),
    )
    op.create_table(
        "recurring_occurrences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["rule_id"], ["recurring_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "due_on", name="one_occurrence_per_due_date"),
    )
    op.create_index("ix_occurrence_book_status", "recurring_occurrences", ["book_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_occurrence_book_status", table_name="recurring_occurrences")
    op.drop_table("recurring_occurrences")
    op.drop_column("recurring_rules", "mode")
