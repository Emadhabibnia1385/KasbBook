"""Persist the last transaction editor without erasing original authorship.

Revision ID: ddf5ddf99303
Revises: cce4cce99202
"""

from alembic import op
import sqlalchemy as sa

revision = "ddf5ddf99303"
down_revision = "cce4cce99202"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        # Earlier category backfills can queue deferred FK checks in the same
        # Alembic transaction. Validate them before DDL, then restore deferral.
        connection.execute(sa.text("SET CONSTRAINTS fk_transaction_category_book IMMEDIATE"))
        connection.execute(sa.text("SET CONSTRAINTS fk_transaction_category_book DEFERRED"))
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("last_edited_by_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("last_edited_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key("fk_transaction_last_editor", "users", ["last_edited_by_id"], ["id"], ondelete="SET NULL")
    transactions = sa.table("transactions", sa.column("id", sa.Uuid()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("last_edited_by_id", sa.Uuid()), sa.column("last_edited_at", sa.DateTime(timezone=True)))
    # Some historical receipt/category changes had no editor audit record.
    # Matching timestamp granularity alone cannot prove which edit was last.
    # Preserve the known modification time, never invent a historical editor.
    connection.execute(transactions.update().where(transactions.c.updated_at.is_not(None))
        .values(last_edited_at=transactions.c.updated_at))


def downgrade():
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("fk_transaction_last_editor", type_="foreignkey")
        batch.drop_column("last_edited_at")
        batch.drop_column("last_edited_by_id")
