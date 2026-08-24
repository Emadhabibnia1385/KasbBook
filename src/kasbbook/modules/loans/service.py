"""Loans: what is left, when it falls due, and recording a payment."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import Flow, Scope, Transaction
from ..ledger.service import LedgerService
from .models import Loan, LoanPayment

INSTALLMENT_CATEGORY = "قسط"


@dataclass(frozen=True)
class LoanProgress:
    loan: Loan
    paid_count: int
    paid_amount: Decimal

    @property
    def total_count(self) -> int:
        return self.loan.installment_count

    @property
    def total_amount(self) -> Decimal:
        return quantize(self.loan.installment_amount * self.total_count)

    @property
    def remaining_count(self) -> int:
        return max(0, self.total_count - self.paid_count)

    @property
    def remaining_amount(self) -> Decimal:
        return quantize(self.loan.installment_amount * self.remaining_count)

    @property
    def percent(self) -> int:
        return int(round(self.paid_count * 100 / self.total_count)) if self.total_count else 0

    @property
    def due_dates(self) -> List[date]:
        return [
            jalali.add_months(self.loan.starts_on, offset)
            for offset in range(self.total_count)
        ]

    @property
    def next_due(self) -> Optional[date]:
        """The date of the next installment still owed.

        Payments are counted, not matched to a particular month, so the Nth
        payment simply clears the Nth due date.
        """
        dates = self.due_dates
        return dates[self.paid_count] if self.paid_count < len(dates) else None


class LoanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)
        self.ledger = LedgerService(session)

    async def create(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
        installment_amount,
        installment_count: int,
        starts_on: date,
    ) -> Loan:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)

        title = (title or "").strip()
        if not title:
            raise ValidationError("نام وام لازم است")

        amount = quantize(to_decimal(installment_amount))
        if amount <= ZERO:
            raise ValidationError("مبلغ قسط باید بیشتر از صفر باشد")
        if installment_count <= 0:
            raise ValidationError("تعداد اقساط باید حداقل ۱ باشد")

        loan = Loan(
            book_id=book_id,
            title=title[:80],
            installment_amount=amount,
            installment_count=int(installment_count),
            starts_on=starts_on,
        )
        self.session.add(loan)
        await self.session.flush()
        return loan

    async def _owned(self, book_id: uuid.UUID, loan_id: uuid.UUID) -> Loan:
        loan = await self.session.get(Loan, loan_id)
        if loan is None or loan.book_id != book_id:
            raise NotFound("این وام پیدا نشد")
        return loan

    async def get(self, book_id: uuid.UUID, user_id: uuid.UUID, loan_id: uuid.UUID) -> Loan:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return await self._owned(book_id, loan_id)

    async def list_loans(self, book_id: uuid.UUID, user_id: uuid.UUID) -> Sequence[Loan]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(Loan)
                .where(Loan.book_id == book_id)
                .order_by(Loan.is_active.desc(), Loan.created_at.desc())
            )
        ).scalars().all()

    async def progress(
        self, book_id: uuid.UUID, user_id: uuid.UUID, loan: Loan
    ) -> LoanProgress:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)

        row = (
            await self.session.execute(
                select(
                    func.count(LoanPayment.id),
                    func.coalesce(func.sum(Transaction.converted_amount), 0),
                )
                .select_from(LoanPayment)
                .join(Transaction, Transaction.id == LoanPayment.transaction_id)
                .where(LoanPayment.loan_id == loan.id)
            )
        ).one()

        return LoanProgress(loan, int(row[0]), quantize(to_decimal(row[1])))

    async def record_payment(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        loan_id: uuid.UUID,
        on: Optional[date] = None,
    ) -> Transaction:
        """One installment: a real expense in the ledger, linked back to the loan."""
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)

        loan = await self._owned(book_id, loan_id)
        paid_on = on or date.today()

        transaction = await self.ledger.record(
            book_id=book_id,
            actor_user_id=user_id,
            flow=Flow.EXPENSE,
            scope=Scope.PERSONAL,
            category=INSTALLMENT_CATEGORY,
            amount=loan.installment_amount,
            description=loan.title,
            occurred_on=paid_on,
        )

        self.session.add(
            LoanPayment(
                loan_id=loan.id, transaction_id=transaction.id, paid_on=paid_on
            )
        )
        await self.session.flush()
        return transaction

    async def delete(
        self, book_id: uuid.UUID, user_id: uuid.UUID, loan_id: uuid.UUID
    ) -> None:
        """Forget the loan, keep its payments: that money really moved."""
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)

        loan = await self._owned(book_id, loan_id)
        for payment in (
            await self.session.execute(
                select(LoanPayment).where(LoanPayment.loan_id == loan.id)
            )
        ).scalars().all():
            await self.session.delete(payment)

        await self.session.delete(loan)
        await self.session.flush()
