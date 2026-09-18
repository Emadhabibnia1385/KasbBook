"""Explicit income/expense category classification; preserve legacy history.

Revision ID: cce4cce99202
Revises: bba3bba99101
"""

from alembic import op
import sqlalchemy as sa

revision = "cce4cce99202"
down_revision = "bba3bba99101"
branch_labels = None
depends_on = None


def upgrade():
    # Legacy categories may have both income and expense transactions. Leave
    # them unclassified until an authorized user explicitly chooses the type.
    with op.batch_alter_table("categories") as batch:
        batch.add_column(sa.Column("flow", sa.Enum("INCOME", "EXPENSE", name="flow",
                                                  native_enum=False, length=12), nullable=True))


def downgrade():
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("flow")
