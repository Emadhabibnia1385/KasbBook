"""When an income link's weeks and months were last settled.

Revision ID: w6a0c3d9e814
Revises: v5f9b2c8d703
Create Date: 2026-11-22 22:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "w6a0c3d9e814"
down_revision: Union[str, None] = "v5f9b2c8d703"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("income_links", schema=None) as batch:
        batch.add_column(sa.Column("settled_on", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("income_links", schema=None) as batch:
        batch.drop_column("settled_on")
