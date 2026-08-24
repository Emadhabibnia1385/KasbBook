"""Debts and receivables — deliberately outside the ledger.

A credit sale is income you already recorded *and* money someone still owes
you. Only the first half is a transaction. If a debt also wrote to the ledger
the sale would be counted twice, so this keeps its own book and never touches
the journal.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text, Uuid
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
