"""Income that follows a person from a team or business book into their own.

Revision ID: s2c6e9f5a470
Revises: r1b5d8e4f369
Create Date: 2026-11-22 14:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "s2c6e9f5a470"
down_revision: Union[str, None] = "r1b5d8e4f369"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "income_links",
        sa.Column("source_book_id", sa.Uuid(), nullable=False),
        sa.Column("target_book_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_book_id"], ["books.id"],
                                name=op.f("fk_income_links_source_book_id_books"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_book_id"], ["books.id"],
                                name=op.f("fk_income_links_target_book_id_books"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_income_links_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_income_links")),
        sa.UniqueConstraint("source_book_id", "user_id", name="one_income_link_per_member_per_book"),
    )
    op.create_index("ix_income_links_source", "income_links", ["source_book_id", "is_active"])
    op.create_table(
        "income_entries",
        sa.Column("link_id", sa.Uuid(), nullable=False),
        sa.Column("ref", sa.String(length=64), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=28, scale=4), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("problem", sa.String(length=300), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["link_id"], ["income_links.id"],
                                name=op.f("fk_income_entries_link_id_income_links"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"],
                                name=op.f("fk_income_entries_transaction_id_transactions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_income_entries")),
        sa.UniqueConstraint("link_id", "ref", name="one_entry_per_source_event"),
    )


def downgrade() -> None:
    op.drop_table("income_entries")
    op.drop_index("ix_income_links_source", table_name="income_links")
    op.drop_table("income_links")
