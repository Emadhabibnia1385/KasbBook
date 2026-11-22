"""Debts and receivables, kept apart from income and expense.

A credit sale is income you already recorded *and* money someone still owes
you. Only the first half is a transaction. If a debt also wrote an income or
an expense the sale would be counted twice, so a debt never does by itself.

Cash is different, and is its own thing: lending someone money, borrowing it,
being paid back, paying back. When a bank account is named for one of those,
the money really moved, and it is a `DebtMovement` with a journal entry on
that account against a receivable or payable account: never income, never an
expense. With no account it moved nothing (a credit sale), as before.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class Direction(str, enum.Enum):
    OWED_TO_ME = "owed_to_me"
    I_OWE = "i_owe"


class Debt(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "debts"
    __table_args__ = (
        Index("ix_debts_open", "book_id", "settled_at"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    person: Mapped[str] = mapped_column(String(80), nullable=False)
    direction: Mapped[Direction] = mapped_column(
        Enum(Direction, native_enum=False, length=16), nullable=False
    )
    amount: Mapped[Money] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="IRT")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Settled debts stay for history but leave the outstanding totals.
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # What has been paid towards it so far; the debt is settled when this reaches `amount`.
    paid_amount: Mapped[Money] = mapped_column(
        Money, nullable=False, default=0, server_default="0"
    )

    @property
    def remaining(self):
        """What is still outstanding."""
        return max(self.amount - (self.paid_amount or 0), 0)


INCREASE = "increase"   # more was lent or borrowed: the debt grew
PAYMENT = "payment"     # some was paid back or received back: the debt shrank


class DebtMovement(UUIDPrimaryKey, Timestamped, Base):
    """One thing that happened to a debt: it grew, or some of it was paid.

    `amount` and `paid_amount` on the debt are what these add up to (plus whatever was there before
    movements were kept), so the history of «added again, paid some, took again» is these rows.
    """

    __tablename__ = "debt_movements"
    __table_args__ = (
        Index("ix_debt_movements_debt", "debt_id", "occurred_on"),
        # The account must be one this very book is linked to; empty means no cash moved.
        ForeignKeyConstraint(
            ["book_id", "bank_account_id"],
            ["bank_account_links.book_id", "bank_account_links.bank_account_id"],
            name="fk_debt_movement_bank_book", deferrable=True, initially="DEFERRED",
        ),
    )

    debt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("debts.id", ondelete="CASCADE"), nullable=False
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[Money] = mapped_column(Money, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The account the cash went through, the entry that moved it, and its effect on the account's balance
    # (negative going out). All empty when no cash moved, or when it was recorded as an income or expense
    # instead (`transaction_id`), whose own entry then carries the cash.
    bank_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    journal_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    cash_delta: Mapped[Money] = mapped_column(Money, nullable=False, default=0, server_default="0")
