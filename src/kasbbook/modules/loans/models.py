"""Loans and the installments that pay them down.

A payment is a real expense, so it is a real transaction in the ledger. The
link between the two lives in its own table rather than as a column on
`transactions`: loans are optional, and an optional feature should not widen
the table every book depends on.

Deleting a loan therefore keeps its payments. That money moved.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class Loan(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "loans"
    __table_args__ = (
        Index("ix_loans_book", "book_id", "is_active"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    installment_amount: Mapped[Money] = mapped_column(Money, nullable=False)
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class LoanPayment(UUIDPrimaryKey, Timestamped, Base):
    """One installment, tied to the transaction that recorded the money."""

    __tablename__ = "loan_payments"
    __table_args__ = (
        Index("ix_loan_payments_loan", "loan_id"),
    )

    loan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("loans.id", ondelete="CASCADE"), nullable=False
    )
    # The transaction outlives the loan, so this link is severed rather than
    # cascading when a loan is deleted.
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
