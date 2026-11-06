"""Holdings valued at today's price, and financial notes with their entries.

Three new tables; nothing existing is touched.

Revision ID: h1d5f8e4b369
Revises: g9c4e7d3a258
Create Date: 2026-11-06 22:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h1d5f8e4b369"
down_revision: Union[str, None] = "g9c4e7d3a258"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONEY = sa.Numeric(precision=28, scale=4)
NOW = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.create_table(
        "holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("instrument", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("quantity", MONEY, nullable=False),
        sa.Column("cost", MONEY, nullable=True),
        sa.Column("unit_price", MONEY, nullable=True),
        sa.Column("acquired_on", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_holdings_book", "holdings", ["book_id"])

    op.create_table(
        "financial_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_book", "financial_notes", ["book_id"])

    op.create_table(
        "financial_note_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("amount", MONEY, nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["note_id"], ["financial_notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_note_entries_note", "financial_note_entries", ["note_id"])


def downgrade() -> None:
    op.drop_index("ix_note_entries_note", table_name="financial_note_entries")
    op.drop_table("financial_note_entries")
    op.drop_index("ix_notes_book", table_name="financial_notes")
    op.drop_table("financial_notes")
    op.drop_index("ix_holdings_book", table_name="holdings")
    op.drop_table("holdings")
