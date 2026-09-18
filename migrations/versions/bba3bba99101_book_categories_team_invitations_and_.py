"""Book-owned categories, consent-based team invitations and login proofs.

Backfill categories without normalising historical names or changing money.
The composite foreign key prevents cross-book category references. It is
deferred so deleting a complete book can cascade both categories and their
transactions regardless of cascade order, while standalone category deletion
cannot orphan a transaction.

Revision ID: bba3bba99101
Revises: f55f2e58ba86
Create Date: 2026-09-18 12:05:56.887933
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = 'bba3bba99101'
down_revision: Union[str, None] = 'f55f2e58ba86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('account_login_challenges',
    sa.Column('requester_identity_id', sa.Uuid(), nullable=False),
    sa.Column('source_user_id', sa.Uuid(), nullable=False),
    sa.Column('target_user_id', sa.Uuid(), nullable=True),
    sa.Column('destination_identity_id', sa.Uuid(), nullable=True),
    sa.Column('destination_digest', sa.String(length=64), nullable=False),
    sa.Column('token_digest', sa.String(length=64), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['requester_identity_id'], ['identities.id'], name=op.f('fk_account_login_challenges_requester_identity_id_identities'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_user_id'], ['users.id'], name=op.f('fk_account_login_challenges_source_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], name=op.f('fk_account_login_challenges_target_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['destination_identity_id'], ['identities.id'], name=op.f('fk_account_login_challenges_destination_identity_id_identities'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_account_login_challenges'))
    )
    with op.batch_alter_table('account_login_challenges', schema=None) as batch_op:
        batch_op.create_index('ix_account_login_requester', ['requester_identity_id', 'created_at'], unique=False)

    op.create_table('categories',
    sa.Column('book_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], name=op.f('fk_categories_book_id_books'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('book_id', 'id', name='category_book_identity'),
    sa.UniqueConstraint('book_id', 'name', name='one_category_name_per_book')
    )
    op.create_table('team_invitations',
    sa.Column('book_id', sa.Uuid(), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=False),
    sa.Column('recipient_user_id', sa.Uuid(), nullable=False),
    sa.Column('recipient_identity_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.Enum('OWNER', 'ADMIN', 'ACCOUNTANT', 'MEMBER', 'VIEWER', name='role', native_enum=False, length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_team_invitations_actor_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], name=op.f('fk_team_invitations_book_id_books'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_identity_id'], ['identities.id'], name=op.f('fk_team_invitations_recipient_identity_id_identities'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], name=op.f('fk_team_invitations_recipient_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_team_invitations'))
    )
    with op.batch_alter_table('team_invitations', schema=None) as batch_op:
        batch_op.create_index('ix_invitations_recipient', ['recipient_user_id', 'status'], unique=False)

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key('fk_transaction_category_book', 'categories', ['book_id', 'category_id'], ['book_id', 'id'], initially='DEFERRED', deferrable=True)

    connection = op.get_bind()
    transactions = sa.table('transactions', sa.column('book_id', sa.Uuid()),
                            sa.column('category', sa.String(80)), sa.column('category_id', sa.Uuid()))
    categories = sa.table('categories', sa.column('id', sa.Uuid()),
                          sa.column('book_id', sa.Uuid()), sa.column('name', sa.String(80)))
    for book_id, name in connection.execute(sa.select(
        transactions.c.book_id, transactions.c.category
    ).distinct()).all():
        category_id = uuid.uuid4()
        connection.execute(categories.insert().values(id=category_id, book_id=book_id, name=name))
        connection.execute(transactions.update().where(
            transactions.c.book_id == book_id, transactions.c.category == name
        ).values(category_id=category_id))


def downgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transaction_category_book', type_='foreignkey')
        batch_op.drop_column('category_id')

    with op.batch_alter_table('team_invitations', schema=None) as batch_op:
        batch_op.drop_index('ix_invitations_recipient')

    op.drop_table('team_invitations')
    op.drop_table('categories')
    with op.batch_alter_table('account_login_challenges', schema=None) as batch_op:
        batch_op.drop_index('ix_account_login_requester')

    op.drop_table('account_login_challenges')
