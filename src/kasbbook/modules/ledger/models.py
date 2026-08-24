"""Transactions and the double-entry ledger behind them.

Every transaction a user records also writes a balanced journal entry. The
transaction is what a shopkeeper reads; the journal is what makes the totals
provable. Debits always equal credits — enforced in the service, tested, and
impossible to bypass because nothing else may write journal lines.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
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


class Flow(str, enum.Enum):
    """Which way the money went, from the book's point of view."""

    INCOME = "income"
    EXPENSE = "expense"


class Scope(str, enum.Enum):
    """Whose money it is, inside a book that may hold more than one kind."""

    WORK = "work"
    PERSONAL = "personal"
    TEAM = "team"


class AccountType(str, enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"


# Which side of an account a debit sits on. Assets and expenses grow with a
# debit; everything else grows with a credit.
DEBIT_POSITIVE = {AccountType.ASSET, AccountType.EXPENSE}


class RateMode(str, enum.Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class Account(UUIDPrimaryKey, Timestamped, Base):
    """A ledger account inside one book."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("book_id", "code", name="one_account_code_per_book"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, native_enum=False, length=16), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="IRT")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Account {self.code} {self.type.value}>"


class Transaction(UUIDPrimaryKey, Timestamped, Base):
    """What the user actually entered.

    The multi-currency fields are all kept: what they typed, in what currency,
    at what rate, from what source, and when. A report of a past period is built
    from the rate recorded here, so it never changes when today's rate moves.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_tx_book_date", "book_id", "occurred_on"),
        Index("ix_tx_book_flow_date", "book_id", "flow", "occurred_on"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    # Who typed it, which is not always whose money it is.
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    flow: Mapped[Flow] = mapped_column(
        Enum(Flow, native_enum=False, length=12), nullable=False
    )
    scope: Mapped[Scope] = mapped_column(
        Enum(Scope, native_enum=False, length=12), nullable=False
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    original_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    original_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    conversion_rate: Mapped[Decimal] = mapped_column(Money, nullable=False)
    converted_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    rate_source: Mapped[Optional[str]] = mapped_column(String(40))
    rate_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rate_mode: Mapped[RateMode] = mapped_column(
        Enum(RateMode, native_enum=False, length=12),
        nullable=False,
        default=RateMode.MANUAL,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Transaction {self.flow.value} {self.converted_amount} {self.base_currency}>"


class JournalEntry(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (Index("ix_journal_book_date", "book_id", "occurred_on"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE")
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text)

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines), Decimal("0"))

    @property
    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines), Decimal("0"))

    @property
    def is_balanced(self) -> bool:
        return self.total_debit == self.total_credit


class JournalLine(UUIDPrimaryKey, Base):
    __tablename__ = "journal_lines"
    __table_args__ = (Index("ix_journal_lines_account", "account_id"),)

    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    debit: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))

    entry: Mapped[JournalEntry] = relationship(back_populates="lines", lazy="selectin")
