"""Which generation of access tokens an account currently accepts.

An access token is a signed JWT that nothing looks up — cheap to verify, and
for the same reason impossible to revoke. Every token now carries the
generation it was minted under, and one whose generation is stale is refused.
Bumping this is what lets a password change end every session immediately
rather than within the token's remaining thirty minutes.

A counter rather than a timestamp: `iat` has one-second granularity, so a token
minted and a cutoff set in the same second compare equal and the old one slips
through. Equality on an integer has no such edge.

`server_default` because `users` is populated in production, and NOT NULL
without one is the migration shape that passes on SQLite and fails there.

Revision ID: f55f2e58ba86
Revises: b99ff9d8e162
Create Date: 2026-08-29 01:11:13.497655
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f55f2e58ba86'
down_revision: Union[str, None] = 'b99ff9d8e162'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_generation', sa.Integer(), server_default=sa.text('0'), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('token_generation')
