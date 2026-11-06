"""Money that changes shape: assets, rotating funds, and loans that bought something kept.

Two columns on loans, one made nullable on loan_payments, and three new tables.
Nothing existing is rewritten: every loan so far is a consumer loan.

Revision ID: g9c4e7d3a258
Revises: f8b3d6c2e157
Create Date: 2026-11-06 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g9c4e7d3a258"
down_revision: Union[str, None] = "f8b3d6c2e157"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("loans", sa.Column("kind", sa.String(length=16), nullable=False, server_default="consumer"))
    op.add_column("loans", sa.Column("principal", sa.Numeric(precision=28, scale=4), nullable=True))
    with op.batch_alter_table("loan_payments") as batch:
        batch.alter_column("transaction_id", existing_type=sa.Uuid(), nullable=True)

    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("cost", sa.Numeric(precision=28, scale=4), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=4), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("loan_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sold_on", sa.Date(), nullable=True),
        sa.Column("sold_for", sa.Numeric(precision=28, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_book", "assets", ["book_id"])

    op.create_table(
        "funds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("monthly_amount", sa.Numeric(precision=28, scale=4), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("payout_amount", sa.Numeric(precision=28, scale=4), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("turn_month", sa.Integer(), nullable=True),
        sa.Column("paid_months", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim", sa.Numeric(precision=28, scale=4), nullable=False, server_default="0"),
        sa.Column("owed", sa.Numeric(precision=28, scale=4), nullable=False, server_default="0"),
        sa.Column("received_on", sa.Date(), nullable=True),
        sa.Column("received_amount", sa.Numeric(precision=28, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_funds_book", "funds", ["book_id"])

    op.create_table(
        "capital_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("amount", sa.Numeric(precision=28, scale=4), nullable=False),
        sa.Column("cash_delta", sa.Numeric(precision=28, scale=4), nullable=False, server_default="0"),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("fund_id", sa.Uuid(), nullable=True),
        sa.Column("loan_id", sa.Uuid(), nullable=True),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_capital_book_date", "capital_movements", ["book_id", "occurred_on"])


def downgrade() -> None:
    op.drop_index("ix_capital_book_date", table_name="capital_movements")
    op.drop_table("capital_movements")
    op.drop_index("ix_funds_book", table_name="funds")
    op.drop_table("funds")
    op.drop_index("ix_assets_book", table_name="assets")
    op.drop_table("assets")
    with op.batch_alter_table("loan_payments") as batch:
        batch.alter_column("transaction_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("loans", "principal")
    op.drop_column("loans", "kind")
