"""Let a book say whether its costs come off before the split or out of the treasury.

Revision ID: ef1aef99404
Revises: ddf5ddf99303
"""

from alembic import op
import sqlalchemy as sa

revision = "ef1aef99404"
down_revision = "ddf5ddf99303"
branch_labels = None
depends_on = None


def upgrade():
    # NOT NULL with no server_default fails on a populated PostgreSQL, which is
    # the only place that combination occurs. The default is the old behaviour:
    # an existing team must not find its next payroll divided differently
    # because of a migration nobody asked to change anything.
    with op.batch_alter_table("books") as batch:
        batch.add_column(
            sa.Column(
                "cost_policy",
                sa.Enum(
                    "BEFORE_SPLIT",
                    "FROM_TREASURY",
                    name="costpolicy",
                    native_enum=False,
                    length=20,
                ),
                nullable=False,
                server_default="BEFORE_SPLIT",
            )
        )


def downgrade():
    with op.batch_alter_table("books") as batch:
        batch.drop_column("cost_policy")
