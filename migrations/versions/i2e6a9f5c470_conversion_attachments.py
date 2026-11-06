"""Files kept with a currency conversion.

One new table; nothing existing is touched.

Revision ID: i2e6a9f5c470
Revises: h1d5f8e4b369
Create Date: 2026-11-07 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i2e6a9f5c470"
down_revision: Union[str, None] = "h1d5f8e4b369"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.create_table(
        "conversion_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("conversion_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("file_name", sa.String(length=120), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversion_id"], ["currency_conversions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversion_attachment", "conversion_attachments", ["conversion_id"])


def downgrade() -> None:
    op.drop_index("ix_conversion_attachment", table_name="conversion_attachments")
    op.drop_table("conversion_attachments")
