"""An asset may be priced by the market, and may be tied to a loan that already existed.

Two nullable/defaulted columns on `assets`; nothing existing changes meaning.

Revision ID: j3f7b0a6d581
Revises: i2e6a9f5c470
Create Date: 2026-11-07 14:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j3f7b0a6d581"
down_revision: Union[str, None] = "i2e6a9f5c470"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch:
        batch.add_column(sa.Column("instrument", sa.String(length=16), nullable=True))
        batch.add_column(
            sa.Column("loan_linked", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch:
        batch.drop_column("loan_linked")
        batch.drop_column("instrument")
