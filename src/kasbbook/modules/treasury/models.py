"""Treasury: the slice of income a team keeps before anyone is paid.

A book can hold several funds — the working treasury, an emergency reserve, a
tax set-aside — and each one is fed by rules the manager writes. What those
rules produced for a given period is snapshotted, so re-reading an old payroll
never re-runs today's rules against last year's income.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class FundKind(str, enum.Enum):
    MAIN = "main"
    EMERGENCY = "emergency"
    TAX = "tax"
    DEVELOPMENT = "development"
    EQUIPMENT = "equipment"
    BONUS = "bonus"


class RuleBasis(str, enum.Enum):
    """What the rule's `value` means."""

    GROSS_PERCENT = "gross_percent"   # % of gross income
    NET_PERCENT = "net_percent"       # % of income minus direct costs
    FIXED = "fixed"                   # a flat amount per period


class TreasuryFund(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "treasury_funds"
    __table_args__ = (
        UniqueConstraint("book_id", "kind", name="one_fund_of_each_kind_per_book"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[FundKind] = mapped_column(
        Enum(FundKind, native_enum=False, length=16), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TreasuryRule(UUIDPrimaryKey, Timestamped, Base):
    """How much of a period's income this fund takes.

    Rules are effective-dated: changing the cut for next quarter must not move
    what last quarter already paid out.
    """

    __tablename__ = "treasury_rules"
    __table_args__ = (Index("ix_treasury_rules_book", "book_id", "is_active"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    fund_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("treasury_funds.id", ondelete="CASCADE"), nullable=False
    )
    basis: Mapped[RuleBasis] = mapped_column(
        Enum(RuleBasis, native_enum=False, length=20), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Optional narrowing: only income in this category feeds the fund.
    category: Mapped[Optional[str]] = mapped_column(String(80))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    fund: Mapped[TreasuryFund] = relationship(lazy="selectin")

    def applies_on(self, day: date) -> bool:
        if not self.is_active or day < self.effective_from:
            return False
        return self.effective_to is None or day <= self.effective_to


class TreasuryAllocation(UUIDPrimaryKey, Timestamped, Base):
    """What a rule actually took, for one period. Written once, never recomputed."""

    __tablename__ = "treasury_allocations"
    __table_args__ = (Index("ix_alloc_period", "period_id"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    fund_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("treasury_funds.id", ondelete="RESTRICT"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    basis_snapshot: Mapped[RuleBasis] = mapped_column(
        Enum(RuleBasis, native_enum=False, length=20), nullable=False
    )
    value_snapshot: Mapped[Decimal] = mapped_column(Money, nullable=False)
