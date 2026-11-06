"""Money that changes shape without being earned or spent.

Buying gold, paying into a rotating savings fund, taking a loan to buy something: each moves value
from one form to another. None of it is income and none of it is an expense, so none of it is a
`Transaction`: reports of income and expense are built from transactions and must not see it.
What these records do is post balanced journal entries between the cash account and an asset or
a liability account, so the books stay provable and the wallet's cash follows.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Date, Enum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class AssetKind(str, enum.Enum):
    GOLD = "gold"
    SAVINGS = "savings"
    PROPERTY = "property"
    OTHER = "other"


class Asset(UUIDPrimaryKey, Timestamped, Base):
    """Something held that is worth money: gold, a deposit, a car. Bought, not spent."""

    __tablename__ = "assets"
    __table_args__ = (Index("ix_assets_book", "book_id"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[AssetKind] = mapped_column(
        Enum(AssetKind, native_enum=False, length=16), nullable=False
    )
    # What it cost, in the book's currency. The asset is carried at this until it is sold.
    cost: Mapped[Money] = mapped_column(Money, nullable=False)
    # Optional: ten grams, three coins. Information only; no figure is derived from it.
    quantity: Mapped[Optional[Money]] = mapped_column(Money, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    acquired_on: Mapped[date] = mapped_column(Date, nullable=False)
    # The loan that paid for it, when one did. Severed, not cascaded, if the loan is ever removed.
    loan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True
    )
    # True when the loan was one already made under the instalments and was tied to this purchase, so removing
    # the purchase gives the loan back as it was instead of deleting it.
    loan_linked: Mapped[bool] = mapped_column(default=False, nullable=False, server_default=sa.false())
    # What it is, when it is something with a market price (gold, a coin, a currency): then it is valued at
    # today's price beside what it cost. Empty for a house or a car, which are carried at their cost.
    instrument: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sold_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sold_for: Mapped[Optional[Money]] = mapped_column(Money, nullable=True)


class Fund(UUIDPrimaryKey, Timestamped, Base):
    """A rotating savings circle: everyone pays in each month and each member's turn pays out the pool.

    Before the turn, what has been paid in is a claim on the fund (an asset). The turn pays out the
    pool: it settles that claim, and anything beyond what was paid in is owed back through the
    remaining months (a liability). Nothing in it is income or an expense.
    """

    __tablename__ = "funds"
    __table_args__ = (Index("ix_funds_book", "book_id"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    monthly_amount: Mapped[Money] = mapped_column(Money, nullable=False)
    months: Mapped[int] = mapped_column(Integer, nullable=False)
    # What the turn pays out, as agreed with the fund.
    payout_amount: Mapped[Money] = mapped_column(Money, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    # Which month's draw is this person's, when it is known; information only.
    turn_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    paid_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Paid in and not yet settled by a payout: the claim on the fund.
    claim: Mapped[Money] = mapped_column(Money, nullable=False, default=0)
    # Received beyond what was paid in, still to be paid back through the remaining months.
    owed: Mapped[Money] = mapped_column(Money, nullable=False, default=0)
    received_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    received_amount: Mapped[Optional[Money]] = mapped_column(Money, nullable=True)


class CapitalMovement(UUIDPrimaryKey, Timestamped, Base):
    """One posting of such money: which journal entry it wrote and how much cash it moved."""

    __tablename__ = "capital_movements"
    __table_args__ = (Index("ix_capital_book_date", "book_id", "occurred_on"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Money] = mapped_column(Money, nullable=False)
    # The effect on the wallet's cash in the book's currency: negative going out, positive coming in, zero when none.
    cash_delta: Mapped[Money] = mapped_column(Money, nullable=False, default=0)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    fund_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("funds.id", ondelete="SET NULL"), nullable=True
    )
    loan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True
    )
    journal_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )
