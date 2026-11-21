"""Transfers between two of a book's bank accounts.

Revision ID: p9f3b6c2d147
Revises: o8e2a5b1c036
Create Date: 2026-11-21 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "p9f3b6c2d147"
down_revision: Union[str, None] = "o8e2a5b1c036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_transfers",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("from_bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("to_bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=28, scale=4), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("from_bank_account_id != to_bank_account_id",
                           name=op.f("ck_bank_transfers_transfer_between_two_accounts")),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"],
                                name=op.f("fk_bank_transfers_book_id_books"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"],
                                name=op.f("fk_bank_transfers_actor_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entry_id"], ["journal_entries.id"],
                                name=op.f("fk_bank_transfers_entry_id_journal_entries"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id", "from_bank_account_id"],
                                ["bank_account_links.book_id", "bank_account_links.bank_account_id"],
                                name="fk_transfer_from_book", initially="DEFERRED", deferrable=True),
        sa.ForeignKeyConstraint(["book_id", "to_bank_account_id"],
                                ["bank_account_links.book_id", "bank_account_links.bank_account_id"],
                                name="fk_transfer_to_book", initially="DEFERRED", deferrable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_transfers")),
    )
    op.create_index("ix_bank_transfers_book_day", "bank_transfers", ["book_id", "occurred_on"])


def downgrade() -> None:
    op.drop_index("ix_bank_transfers_book_day", table_name="bank_transfers")
    op.drop_table("bank_transfers")
