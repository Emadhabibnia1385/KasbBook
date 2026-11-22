"""The bank account on a payroll payment and on a currency conversion.

Revision ID: t3d7f0a6b581
Revises: s2c6e9f5a470
Create Date: 2026-11-22 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "t3d7f0a6b581"
down_revision: Union[str, None] = "s2c6e9f5a470"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All nullable, so every existing row stays as it was: no account, as before.
    with op.batch_alter_table("payroll_payments", schema=None) as batch:
        batch.add_column(sa.Column("book_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("bank_account_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("journal_entry_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_payroll_payments_journal_entry_id_journal_entries", "journal_entries",
            ["journal_entry_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_payment_bank_book", "bank_account_links", ["book_id", "bank_account_id"],
            ["book_id", "bank_account_id"], initially="DEFERRED", deferrable=True,
        )
    # The book a payment belongs to is its payslip's: filled in so the account can be tied to it.
    op.execute(
        "UPDATE payroll_payments SET book_id = "
        "(SELECT payslips.book_id FROM payslips WHERE payslips.id = payroll_payments.payslip_id)"
    )
    with op.batch_alter_table("currency_conversions", schema=None) as batch:
        batch.add_column(sa.Column("bank_account_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("journal_entry_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_currency_conversions_journal_entry_id_journal_entries", "journal_entries",
            ["journal_entry_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_conversion_bank_book", "bank_account_links", ["book_id", "bank_account_id"],
            ["book_id", "bank_account_id"], initially="DEFERRED", deferrable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("currency_conversions", schema=None) as batch:
        batch.drop_constraint("fk_conversion_bank_book", type_="foreignkey")
        batch.drop_constraint("fk_currency_conversions_journal_entry_id_journal_entries", type_="foreignkey")
        batch.drop_column("journal_entry_id")
        batch.drop_column("bank_account_id")
    with op.batch_alter_table("payroll_payments", schema=None) as batch:
        batch.drop_constraint("fk_payment_bank_book", type_="foreignkey")
        batch.drop_constraint("fk_payroll_payments_journal_entry_id_journal_entries", type_="foreignkey")
        batch.drop_column("journal_entry_id")
        batch.drop_column("bank_account_id")
        batch.drop_column("book_id")
