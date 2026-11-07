"""A category name is unique per kind of money, not per book: «فروش» may be an income and an expense.

Revision ID: k4a8c1d7e692
Revises: j3f7b0a6d581
Create Date: 2026-11-07 15:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "k4a8c1d7e692"
down_revision: Union[str, None] = "j3f7b0a6d581"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.drop_constraint("one_category_name_per_book", type_="unique")
        batch.create_unique_constraint("one_category_name_per_book_flow", ["book_id", "name", "flow"])


def downgrade() -> None:
    # Only possible while no book has the same name in both kinds.
    with op.batch_alter_table("categories") as batch:
        batch.drop_constraint("one_category_name_per_book_flow", type_="unique")
        batch.create_unique_constraint("one_category_name_per_book", ["book_id", "name"])
