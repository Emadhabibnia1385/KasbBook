"""Income that follows a person from a team or business book into their own.

A member of a team book is paid out of it; a person with a business book earns from it. Either way the
money is theirs, and it belongs in their personal accounts. An `IncomeLink` says "write my income from
that book into this one of mine", how often (when I am paid, when the payroll period closes, or day,
week, month), and what to call it. Each income written is remembered by an `IncomeEntry`, keyed by what
it stands for, so a change in the source updates the entry in place and never writes it twice.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money

# When the income is written.
PAYMENT = "payment"    # each time the team pays me
PERIOD = "period"      # once, when a payroll period closes: my net pay
DAILY = "daily"        # my share of each day's net income, kept in step as the day's entries change
WEEKLY = "weekly"
MONTHLY = "monthly"
MODES = (PAYMENT, PERIOD, DAILY, WEEKLY, MONTHLY)
BUCKETS = (DAILY, WEEKLY, MONTHLY)


class IncomeLink(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "income_links"
    __table_args__ = (
        UniqueConstraint("source_book_id", "user_id", name="one_income_link_per_member_per_book"),
        Index("ix_income_links_source", "source_book_id", "is_active"),
    )

    source_book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    target_book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # What the income is filed under in the target book.
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    # Nothing before this day is written: switching the link on does not rewrite history unless asked.
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    # The target book's bank account the income arrives in, settled when the link is made (like a
    # recurring rule's): the book's default then, an account, or none.
    bank_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Also take the same amount out of the source book as the owner's draw, so what the book holds follows
    # what its owner took. Only for a business of one: a team pays its members through payroll instead.
    draws: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")


class IncomeEntry(UUIDPrimaryKey, Timestamped, Base):
    """One income written to the target book, and what it stands for.

    `ref` is what it stands for (`pay:<id>`, `period:<id>`, `day:2026-08-24`, `week:…`, `month:…`), so
    finding the entry for a source event is a lookup, not a guess. An entry with no transaction is one the
    target book refused (a closed period, a lost permission); `problem` says why, and a resync tries again.
    """

    __tablename__ = "income_entries"
    __table_args__ = (UniqueConstraint("link_id", "ref", name="one_entry_per_source_event"),)

    link_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("income_links.id", ondelete="CASCADE"), nullable=False
    )
    ref: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Removed with the transaction: the entry is only ever the record of one that exists, or of a refusal.
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True
    )
    problem: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    # The draw (or contribution) recorded in the source book alongside this entry, when the link takes draws.
    draw_movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("capital_movements.id", ondelete="SET NULL"), nullable=True
    )
