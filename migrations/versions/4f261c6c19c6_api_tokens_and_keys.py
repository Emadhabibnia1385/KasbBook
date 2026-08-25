"""Refresh tokens and API keys.

Both tables store a SHA-256 digest rather than the credential itself, so
neither can be replayed out of a database dump. Refresh tokens additionally
carry a family id and a replaced_by pointer, which is what makes rotation
detectable: presenting a token that has already been exchanged means a copy
exists somewhere, and the whole family is revoked rather than that one row.

Revision ID: 4f261c6c19c6
Revises: a1a1e98e89f1
Create Date: 2026-08-25 17:10:13.695176
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4f261c6c19c6'
down_revision: Union[str, None] = 'a1a1e98e89f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('api_keys',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('token_digest', sa.String(length=64), nullable=False),
    sa.Column('prefix', sa.String(length=12), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_api_keys_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_keys'))
    )
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.create_index('ix_api_keys_digest', ['token_digest'], unique=True)
        batch_op.create_index('ix_api_keys_user', ['user_id'], unique=False)

    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_digest', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.Uuid(), nullable=False),
    sa.Column('replaced_by_id', sa.Uuid(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_agent', sa.String(length=200), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens'))
    )
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.create_index('ix_refresh_tokens_digest', ['token_digest'], unique=True)
        batch_op.create_index('ix_refresh_tokens_family', ['family_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_index('ix_refresh_tokens_family')
        batch_op.drop_index('ix_refresh_tokens_digest')

    op.drop_table('refresh_tokens')
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.drop_index('ix_api_keys_user')
        batch_op.drop_index('ix_api_keys_digest')

    op.drop_table('api_keys')
