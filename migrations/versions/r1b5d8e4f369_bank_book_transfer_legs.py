"""Money moved between two books: one leg in each.

Revision ID: r1b5d8e4f369
Revises: q0a4c7d3e258
Create Date: 2026-11-22 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "r1b5d8e4f369"
down_revision: Union[str, None] = "q0a4c7d3e258"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_book_transfer_legs",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("pair_id", sa.Uuid(), nullable=False),
        sa.Column("other_book_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=28, scale=4), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("direction in ('in', 'out')", name=op.f("ck_bank_book_transfer_legs_leg_direction")),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"],
                                name=op.f("fk_bank_book_transfer_legs_book_id_books"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"],
                                name=op.f("fk_bank_book_transfer_legs_actor_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entry_id"], ["journal_entries.id"],
                                name=op.f("fk_bank_book_transfer_legs_entry_id_journal_entries"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id", "bank_account_id"],
                                ["bank_account_links.book_id", "bank_account_links.bank_account_id"],
                                name="fk_book_transfer_leg_bank_book", initially="DEFERRED", deferrable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_book_transfer_legs")),
    )
    op.create_index("ix_book_transfer_legs_book_day", "bank_book_transfer_legs", ["book_id", "occurred_on"])
    op.create_index("ix_book_transfer_legs_pair", "bank_book_transfer_legs", ["pair_id"])


def downgrade() -> None:
    op.drop_index("ix_book_transfer_legs_pair", table_name="bank_book_transfer_legs")
    op.drop_index("ix_book_transfer_legs_book_day", table_name="bank_book_transfer_legs")
    op.drop_table("bank_book_transfer_legs")
