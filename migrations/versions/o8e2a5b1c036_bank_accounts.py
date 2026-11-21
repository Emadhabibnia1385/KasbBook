"""Bank accounts, linked to any number of books, and the account a transaction used.

Revision ID: o8e2a5b1c036
Revises: n7d1f4a0b925
Create Date: 2026-11-21 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "o8e2a5b1c036"
down_revision: Union[str, None] = "n7d1f4a0b925"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_accounts",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("bank_name", sa.String(length=80), nullable=False),
        sa.Column("holder_name", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("card_number", sa.String(length=16), nullable=True),
        sa.Column("account_number", sa.String(length=32), nullable=True),
        sa.Column("sheba", sa.String(length=26), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("opening_balance", sa.Numeric(precision=28, scale=4), nullable=False,
                  server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"],
                                name=op.f("fk_bank_accounts_owner_user_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_accounts")),
    )
    op.create_table(
        "bank_account_links",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_account_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"],
                                name=op.f("fk_bank_account_links_book_id_books"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"],
                                name=op.f("fk_bank_account_links_bank_account_id_bank_accounts"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ledger_account_id"], ["accounts.id"],
                                name=op.f("fk_bank_account_links_ledger_account_id_accounts"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_account_links")),
        sa.UniqueConstraint("book_id", "bank_account_id", name="one_link_per_book_and_bank"),
    )
    op.create_index(
        "one_default_bank_per_book", "bank_account_links", ["book_id"], unique=True,
        sqlite_where=sa.text("is_default"), postgresql_where=sa.text("is_default"),
    )
    # Nullable, so the rows that exist stay as they are: no account, still on «نقد و بانک».
    with op.batch_alter_table("transactions", schema=None) as batch:
        batch.add_column(sa.Column("bank_account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_transaction_bank_book", "bank_account_links", ["book_id", "bank_account_id"],
            ["book_id", "bank_account_id"], initially="DEFERRED", deferrable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch:
        batch.drop_constraint("fk_transaction_bank_book", type_="foreignkey")
        batch.drop_column("bank_account_id")
    op.drop_index("one_default_bank_per_book", table_name="bank_account_links")
    op.drop_table("bank_account_links")
    op.drop_table("bank_accounts")
