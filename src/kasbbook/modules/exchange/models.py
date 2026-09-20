"""Which currencies a book may hold, and moving value between them.

A book keeps what it receives in the currency it received it. Ten tethers paid
in are ten tethers held, not a toman figure fixed at that day's rate — the
toman figure is recorded too, frozen on the transaction, but it is the
valuation, not the holding. The holding only changes when money comes in, goes
out, or is converted.

Conversions are deliberately not transactions. `compute_distribution` sums
income and expense to decide what everyone is paid, so a conversion recorded as
an expense in one currency and income in another would inflate both sides and
move every member's share — for a swap that earned the book nothing. Keeping
them in their own table is what makes that impossible rather than merely
discouraged.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money, ZERO


# What the bot offers to tick, and what each is called in Persian. These live
# on the model rather than the service so screens can name a currency without
# importing anything that talks to a database.
CURRENCY_NAMES = {
    "IRT": "تومان",
    "IRR": "ریال",
    "USDT": "تتر",
    "TON": "تون",
    "TRX": "ترون",
}
OFFERED = ("USDT", "TON", "TRX")


class BookCurrency(UUIDPrimaryKey, Timestamped, Base):
    """One currency, beyond the base one, that this book is allowed to hold.

    The base currency is never a row here. It is always allowed, so there is no
    way to switch it off by accident and no backfill was needed for the books
    that existed before this table.
    """

    __tablename__ = "book_currencies"
    __table_args__ = (
        UniqueConstraint("book_id", "code", name="one_row_per_currency_per_book"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CurrencyConversion(UUIDPrimaryKey, Timestamped, Base):
    """Value leaving one currency of a book's wallet and arriving in another."""

    __tablename__ = "currency_conversions"
    __table_args__ = (Index("ix_conversions_book_day", "book_id", "occurred_on"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)

    from_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    from_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    to_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    to_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)

    # What the swap was worth in the book's own currency, frozen here the way a
    # transaction freezes its rate: a report of last month must not move when
    # today's price does.
    base_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False)

    note: Mapped[Optional[str]] = mapped_column(Text)

    @property
    def from_rate(self) -> Decimal:
        """What one unit of the outgoing currency was worth in base currency."""
        return self.base_value / self.from_amount if self.from_amount else ZERO

    @property
    def to_rate(self) -> Decimal:
        return self.base_value / self.to_amount if self.to_amount else ZERO
