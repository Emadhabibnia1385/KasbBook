"""What happened to a debt: it grew, or some of it was paid, and which account the cash used.

Revision ID: u4e8a1b7c692
Revises: t3d7f0a6b581
Create Date: 2026-11-22 16:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "u4e8a1b7c692"
down_revision: Union[str, None] = "t3d7f0a6b581"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New table only: a debt that exists keeps its `amount` and `paid_amount`, and the history starts here.
    op.create_table(
        "debt_movements",
        sa.Column("debt_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("amount", sa.Numeric(precision=28, scale=4), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("bank_account_id", sa.Uuid(), nullable=True),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("cash_delta", sa.Numeric(precision=28, scale=4), nullable=False, server_default="0"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["debt_id"], ["debts.id"],
                                name=op.f("fk_debt_movements_debt_id_debts"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"],
                                name=op.f("fk_debt_movements_book_id_books"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"],
                                name=op.f("fk_debt_movements_actor_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"],
                                name=op.f("fk_debt_movements_journal_entry_id_journal_entries"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"],
                                name=op.f("fk_debt_movements_transaction_id_transactions"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["book_id", "bank_account_id"],
                                ["bank_account_links.book_id", "bank_account_links.bank_account_id"],
                                name="fk_debt_movement_bank_book", initially="DEFERRED", deferrable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_debt_movements")),
    )
    op.create_index("ix_debt_movements_debt", "debt_movements", ["debt_id", "occurred_on"])


def downgrade() -> None:
    op.drop_index("ix_debt_movements_debt", table_name="debt_movements")
    op.drop_table("debt_movements")
