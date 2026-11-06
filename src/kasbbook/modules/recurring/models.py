"""Transactions that repeat.

Rent, salary, a subscription: defined once and booked on a schedule. The rule
carries its own next-due date rather than being derived from a start date and a
count, so catching up after downtime is a loop rather than a calculation.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import DateTime, Date, Enum, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money
from ..ledger.models import Flow


class Period(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"   # a Jalali month, not thirty days


class Mode(str, enum.Enum):
    """What happens when a rule comes due."""

    ASK = "ask"    # nothing is recorded until somebody confirms that date
    AUTO = "auto"  # recorded on its own


class OccurrenceStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SKIPPED = "skipped"


class RecurringRule(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "recurring_rules"
    __table_args__ = (
        # The job asks one question: what is due? This is the index for it.
        Index("ix_recurring_due", "is_active", "next_run_on"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    flow: Mapped[Flow] = mapped_column(
        Enum(Flow, native_enum=False, length=16), nullable=False
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Money] = mapped_column(Money, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    period: Mapped[Period] = mapped_column(
        Enum(Period, native_enum=False, length=16), nullable=False
    )
    next_run_on: Mapped[date] = mapped_column(Date, nullable=False)
    last_run_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # How each due date is handled. Rules made before this existed keep recording on their own.
    mode: Mapped[Mode] = mapped_column(
        Enum(Mode, native_enum=False, length=16), nullable=False, default=Mode.AUTO,
        server_default=Mode.AUTO.value,
    )


class RecurringOccurrence(UUIDPrimaryKey, Timestamped, Base):
    """One due date of a rule that asks first: waiting, confirmed into a transaction, or skipped."""

    __tablename__ = "recurring_occurrences"
    __table_args__ = (
        # A date comes due once; running the job twice must not queue it twice.
        UniqueConstraint("rule_id", "due_on", name="one_occurrence_per_due_date"),
        Index("ix_occurrence_book_status", "book_id", "status"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recurring_rules.id", ondelete="CASCADE"), nullable=False
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[OccurrenceStatus] = mapped_column(
        Enum(OccurrenceStatus, native_enum=False, length=16), nullable=False,
        default=OccurrenceStatus.PENDING,
    )
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
