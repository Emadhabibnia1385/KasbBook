"""Paying a debt in parts: what has been paid so far, kept on the debt.

One defaulted column; existing debts have paid nothing.

Revision ID: f8b3d6c2e157
Revises: e7a2c5b1d946
Create Date: 2026-11-06 19:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8b3d6c2e157"
down_revision: Union[str, None] = "e7a2c5b1d946"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "debts",
        sa.Column("paid_amount", sa.Numeric(precision=28, scale=4), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("debts", "paid_amount")
