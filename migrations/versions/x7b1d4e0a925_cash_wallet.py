"""A bank account can be the owner's cash wallet.

Revision ID: x7b1d4e0a925
Revises: w6a0c3d9e814
Create Date: 2026-11-24 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "x7b1d4e0a925"
down_revision: Union[str, None] = "w6a0c3d9e814"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_accounts", schema=None) as batch:
        batch.add_column(sa.Column("kind", sa.String(length=8), nullable=False, server_default="bank"))
        batch.create_check_constraint("bank_account_kind", "kind in ('bank', 'cash')")
    op.create_index(
        "one_cash_wallet_per_owner_and_unit", "bank_accounts", ["owner_user_id", "currency"], unique=True,
        sqlite_where=sa.text("kind = 'cash'"), postgresql_where=sa.text("kind = 'cash'"),
    )


def downgrade() -> None:
    op.drop_index("one_cash_wallet_per_owner_and_unit", table_name="bank_accounts")
    with op.batch_alter_table("bank_accounts", schema=None) as batch:
        batch.drop_constraint("bank_account_kind", type_="check")
        batch.drop_column("kind")
