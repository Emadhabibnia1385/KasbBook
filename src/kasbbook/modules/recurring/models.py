"""Transactions that repeat.

Rent, salary, a subscription: defined once and booked on a schedule. The rule
carries its own next-due date rather than being derived from a start date and a
count, so catching up after downtime is a loop rather than a calculation.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money
from ..ledger.models import Flow


class Period(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"   # a Jalali month, not thirty days


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
