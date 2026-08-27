"""What a receipt actually is, alongside the id that points at it.

A provider's file id is opaque: it says nothing about whether the thing behind
it is a photograph of a till roll or a PDF invoice. Three nullable columns
carry that, so the detail screen can name the file and sending it back can pick
the right method instead of trying one and wearing the failure.

Nullable on purpose. Every transaction that already exists predates these, and
a NOT NULL column added to a populated table is the one migration shape that
passes on SQLite and fails on production PostgreSQL.

Revision ID: b99ff9d8e162
Revises: 4f261c6c19c6
Create Date: 2026-08-27 20:09:43.207483
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b99ff9d8e162'
down_revision: Union[str, None] = '4f261c6c19c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('receipt_kind', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('receipt_file_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('receipt_mime_type', sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_column('receipt_mime_type')
        batch_op.drop_column('receipt_file_name')
        batch_op.drop_column('receipt_kind')
