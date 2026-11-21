"""The bank account on a capital movement and on a recurring rule.

Revision ID: q0a4c7d3e258
Revises: p9f3b6c2d147
Create Date: 2026-11-21 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "q0a4c7d3e258"
down_revision: Union[str, None] = "p9f3b6c2d147"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, so every existing row stays as it was: no account, still on «نقد و بانک».
    with op.batch_alter_table("capital_movements", schema=None) as batch:
        batch.add_column(sa.Column("bank_account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_capital_bank_book", "bank_account_links", ["book_id", "bank_account_id"],
            ["book_id", "bank_account_id"], initially="DEFERRED", deferrable=True,
        )
    with op.batch_alter_table("recurring_rules", schema=None) as batch:
        batch.add_column(sa.Column("bank_account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_recurring_bank_book", "bank_account_links", ["book_id", "bank_account_id"],
            ["book_id", "bank_account_id"], initially="DEFERRED", deferrable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("recurring_rules", schema=None) as batch:
        batch.drop_constraint("fk_recurring_bank_book", type_="foreignkey")
        batch.drop_column("bank_account_id")
    with op.batch_alter_table("capital_movements", schema=None) as batch:
        batch.drop_constraint("fk_capital_bank_book", type_="foreignkey")
        batch.drop_column("bank_account_id")
