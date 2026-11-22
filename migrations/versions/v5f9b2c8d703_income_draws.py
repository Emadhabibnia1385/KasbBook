"""An income link can take the same amount out of the source business as the owner's draw.

Revision ID: v5f9b2c8d703
Revises: u4e8a1b7c692
Create Date: 2026-11-22 20:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "v5f9b2c8d703"
down_revision: Union[str, None] = "u4e8a1b7c692"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Off for every link that exists: a link made before draws existed behaves as it did.
    with op.batch_alter_table("income_links", schema=None) as batch:
        batch.add_column(sa.Column("draws", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("income_entries", schema=None) as batch:
        batch.add_column(sa.Column("draw_movement_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_income_entries_draw_movement_id_capital_movements", "capital_movements",
            ["draw_movement_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("income_entries", schema=None) as batch:
        batch.drop_constraint("fk_income_entries_draw_movement_id_capital_movements", type_="foreignkey")
        batch.drop_column("draw_movement_id")
    with op.batch_alter_table("income_links", schema=None) as batch:
        batch.drop_column("draws")
