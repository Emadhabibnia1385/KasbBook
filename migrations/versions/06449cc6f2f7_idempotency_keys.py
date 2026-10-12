"""Idempotency keys: a retried request that moves money is answered again, not done again.

A new table and nothing else, so it is safe on a populated database. Each row
is written in the same transaction as the request it guards and expires after
48 hours.

Revision ID: 06449cc6f2f7
Revises: 9e632756c0e3
Create Date: 2026-10-12 21:32:10.149884
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '06449cc6f2f7'
down_revision: Union[str, None] = '9e632756c0e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('idempotency_keys',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('method', sa.String(length=8), nullable=False),
    sa.Column('path', sa.String(length=255), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('status_code', sa.SmallInteger(), nullable=True),
    sa.Column('response_body', sa.Text(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_idempotency_keys_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_idempotency_keys'))
    )
    with op.batch_alter_table('idempotency_keys', schema=None) as batch_op:
        batch_op.create_index('ix_idempotency_keys_expires', ['expires_at'], unique=False)
        batch_op.create_index('ix_idempotency_keys_scope', ['user_id', 'key', 'method', 'path'], unique=True)



def downgrade() -> None:
    with op.batch_alter_table('idempotency_keys', schema=None) as batch_op:
        batch_op.drop_index('ix_idempotency_keys_scope')
        batch_op.drop_index('ix_idempotency_keys_expires')

    op.drop_table('idempotency_keys')
