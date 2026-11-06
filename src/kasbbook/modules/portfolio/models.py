"""What a person holds, and notes on the things they have put money into.

Neither touches the ledger. A holding is a statement ("I have ten gold coins") valued by today's price;
a note is a running account of one thing (a plot of land, a renovation): what was put into it and what
it was worth at various times. They answer "how much do I have" and "how much did this cost me and
what did it become", which the books of income and expense are not for.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class Holding(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "holdings"
    __table_args__ = (Index("ix_holdings_book", "book_id"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    # A code from the catalog: gold18, coin_emami, XAU, USD, BTC, other…
    instrument: Mapped[str] = mapped_column(String(16), nullable=False)
    # The person's own name for it; required for "other".
    label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    quantity: Mapped[Money] = mapped_column(Money, nullable=False)
    # What all of it cost, in the book's currency, when known: the basis for profit and loss.
    cost: Mapped[Optional[Money]] = mapped_column(Money, nullable=True)
    # For "other", which has no feed: what one unit is worth, as the person says.
    unit_price: Mapped[Optional[Money]] = mapped_column(Money, nullable=True)
    acquired_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FinancialNote(UUIDPrimaryKey, Timestamped, Base):
    """One thing money was put into: a plot, a house, a business, a trip."""

    __tablename__ = "financial_notes"
    __table_args__ = (Index("ix_notes_book", "book_id"),)

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class NoteEntry(UUIDPrimaryKey, Timestamped, Base):
    """One line of a note: money put in ("spent"), what it was worth then ("value"), or just a remark."""

    __tablename__ = "financial_note_entries"
    __table_args__ = (Index("ix_note_entries_note", "note_id"),)

    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("financial_notes.id", ondelete="CASCADE"), nullable=False
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[Optional[Money]] = mapped_column(Money, nullable=True)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
