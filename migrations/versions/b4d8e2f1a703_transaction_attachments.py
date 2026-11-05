"""Files attached to a transaction from the web panel.

New table only, so nothing here touches populated rows.

Revision ID: b4d8e2f1a703
Revises: a7c1d3e5f901
Create Date: 2026-11-06 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4d8e2f1a703"
down_revision: Union[str, None] = "a7c1d3e5f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("file_name", sa.String(length=120), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attachment_tx", "transaction_attachments", ["transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_attachment_tx", table_name="transaction_attachments")
    op.drop_table("transaction_attachments")
