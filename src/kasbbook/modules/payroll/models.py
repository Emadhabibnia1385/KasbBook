"""Financial periods, member shares, performance, and what each person is paid.

The chain the spec describes, as data:

    gross income − direct costs − fees − tax − treasury  =  distributable
    distributable × member share                          =  base share
    base share + bonuses + overtime − shortfall − penalty − advance = net pay

Every step is snapshotted onto the payslip. Once a period is locked, corrections
are new adjustments in a later period rather than edits to a paid one.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class PeriodStatus(str, enum.Enum):
    OPEN = "open"
    CALCULATING = "calculating"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    PAID = "paid"
    LOCKED = "locked"


# The only moves allowed. Anything else is a bug, not a decision.
PERIOD_TRANSITIONS = {
    PeriodStatus.OPEN: {PeriodStatus.CALCULATING},
    PeriodStatus.CALCULATING: {PeriodStatus.AWAITING_APPROVAL, PeriodStatus.OPEN},
    PeriodStatus.AWAITING_APPROVAL: {PeriodStatus.APPROVED, PeriodStatus.CALCULATING},
    PeriodStatus.APPROVED: {PeriodStatus.PAID, PeriodStatus.AWAITING_APPROVAL},
    PeriodStatus.PAID: {PeriodStatus.LOCKED},
    PeriodStatus.LOCKED: set(),
}


class ShareBasis(str, enum.Enum):
    PERCENT = "percent"
    FIXED = "fixed"
    HOURS = "hours"
    DAYS = "days"
    POINTS = "points"
    PROJECT = "project"


class AdjustmentKind(str, enum.Enum):
    BONUS = "bonus"
    OVERTIME = "overtime"
    PENALTY = "penalty"
    SHORTFALL = "shortfall"
    ADVANCE = "advance"
    CORRECTION = "correction"


class AdjustmentMode(str, enum.Enum):
    PERCENT = "percent"   # of the base share
    AMOUNT = "amount"     # a flat figure


class FinancialPeriod(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "financial_periods"
    __table_args__ = (
        UniqueConstraint("book_id", "label", name="one_period_label_per_book"),
        Index("ix_periods_book_status", "book_id", "status"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PeriodStatus] = mapped_column(
        Enum(PeriodStatus, native_enum=False, length=20),
        nullable=False,
        default=PeriodStatus.OPEN,
    )
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    @property
    def is_editable(self) -> bool:
        return self.status in (PeriodStatus.OPEN, PeriodStatus.CALCULATING)


class ShareRule(UUIDPrimaryKey, Timestamped, Base):
    """One member's cut, valid for a date range.

    Effective dating is what stops a raise agreed today from silently rewriting
    what the same person was paid last spring.
    """

    __tablename__ = "share_rules"
    __table_args__ = (Index("ix_share_rules_book_user", "book_id", "user_id"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    basis: Mapped[ShareBasis] = mapped_column(
        Enum(ShareBasis, native_enum=False, length=16), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def applies_on(self, day: date) -> bool:
        if not self.is_active or day < self.effective_from:
            return False
        return self.effective_to is None or day <= self.effective_to


class PerformanceRecord(UUIDPrimaryKey, Timestamped, Base):
    """What a member actually did in a period."""

    __tablename__ = "performance_records"
    __table_args__ = (
        UniqueConstraint("period_id", "user_id", name="one_record_per_member_per_period"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    hours_worked: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    days_worked: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    overtime_hours: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    absence_days: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    leave_days: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    mission_days: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    late_count: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    points: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))


class Adjustment(UUIDPrimaryKey, Timestamped, Base):
    """A plus or a minus on one member's pay, with a reason and a paper trail."""

    __tablename__ = "adjustments"
    __table_args__ = (Index("ix_adjustments_period_user", "period_id", "user_id"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[AdjustmentKind] = mapped_column(
        Enum(AdjustmentKind, native_enum=False, length=16), nullable=False
    )
    mode: Mapped[AdjustmentMode] = mapped_column(
        Enum(AdjustmentMode, native_enum=False, length=12), nullable=False
    )
    # Signed: negative is a deduction. One field beats a second "direction"
    # column that could disagree with it.
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)

    recorded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Payslip(UUIDPrimaryKey, Timestamped, Base):
    """One member's pay for one period, with the inputs frozen alongside it."""

    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("period_id", "user_id", name="one_payslip_per_member_per_period"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    distributable_snapshot: Mapped[Decimal] = mapped_column(Money, nullable=False)
    share_basis_snapshot: Mapped[ShareBasis] = mapped_column(
        Enum(ShareBasis, native_enum=False, length=16), nullable=False
    )
    share_value_snapshot: Mapped[Decimal] = mapped_column(Money, nullable=False)

    base_share: Mapped[Decimal] = mapped_column(Money, nullable=False)
    adjustments_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    net_pay: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="payslip", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def paid_total(self) -> Decimal:
        return sum((p.amount for p in self.payments), Decimal("0"))

    @property
    def remaining(self) -> Decimal:
        return self.net_pay - self.paid_total

    @property
    def is_settled(self) -> bool:
        return self.remaining <= Decimal("0")


class Payment(UUIDPrimaryKey, Timestamped, Base):
    """Money actually handed over — possibly in instalments, possibly in another currency."""

    __tablename__ = "payroll_payments"
    __table_args__ = (Index("ix_payments_payslip", "payslip_id"),)

    payslip_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    conversion_rate: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("1")
    )
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(80))
    note: Mapped[Optional[str]] = mapped_column(Text)

    payslip: Mapped[Payslip] = relationship(back_populates="payments", lazy="selectin")
