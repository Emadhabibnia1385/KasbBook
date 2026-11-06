"""Loans: what is left, when it falls due, and recording a payment."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import calendars, jalali
from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import Flow, Scope, Transaction
from ..ledger.service import LedgerService
from .models import Loan, LoanPayment

INSTALLMENT_CATEGORY = "قسط"
INTEREST_CATEGORY = "سود وام"


@dataclass(frozen=True)
class LoanProgress:
    loan: Loan
    paid_count: int
    paid_amount: Decimal
    # Whose months the installments fall in: the book's own calendar.
    calendar: calendars.Calendar = calendars.JALALI

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
            self.calendar.add_months(self.loan.starts_on, offset)
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
            raise ValidationError("تعداد اقساط باید حداقل 1 باشد")

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

        # Counted from the payments themselves: an installment of a capital loan with no interest has
        # no transaction to join to, and would otherwise not be counted at all.
        count = int(await self._paid_count(loan))
        cal = calendars.of(await self.books.get_book(book_id))
        if loan.kind == "capital":
            # What was paid is the installments themselves, not a sum over the transactions that exist.
            paid = quantize(loan.installment_amount * count)
        else:
            summed = await self.session.scalar(
                select(func.coalesce(func.sum(Transaction.converted_amount), 0))
                .select_from(LoanPayment)
                .join(Transaction, Transaction.id == LoanPayment.transaction_id)
                .where(LoanPayment.loan_id == loan.id)
            )
            paid = quantize(to_decimal(summed))
        return LoanProgress(loan, count, paid, cal)

    async def _paid_count(self, loan: Loan) -> int:
        return int(await self.session.scalar(
            select(func.count(LoanPayment.id)).where(LoanPayment.loan_id == loan.id)
        ) or 0)

    async def record_payment(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        loan_id: uuid.UUID,
        on: Optional[date] = None,
        expected_paid_count: Optional[int] = None,
    ) -> Transaction:
        """One installment: a real expense in the ledger, linked back to the loan.

        A loan of two instalments took a third, and a fourth: nothing compared
        the count with the loan, and the progress screen clamped "remaining" to
        zero so the overpayment showed nowhere. Refused now.

        `expected_paid_count` is how many were paid on the screen the person
        pressed. Two presses of the same button both carry the same count, so
        the second finds the count moved and records nothing — while two
        instalments paid on purpose, one after the other, each carry their own.
        """
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        # Counted under the book lock, so two payments in flight see each other.
        await self.ledger.categories.lock_book(book_id)

        loan = await self._owned(book_id, loan_id)
        paid = await self._paid_count(loan)
        if expected_paid_count is not None and paid != expected_paid_count:
            raise ValidationError(
                "این صفحه قدیمی است؛ این قسط قبلاً ثبت شده. وضعیت تازهٔ وام را ببین."
            )
        if paid >= loan.installment_count:
            raise ValidationError("همهٔ اقساط این وام پرداخت شده است.")

        # The book's day, not the server's UTC one.
        paid_on = on or jalali.today_in((await self.books.get_book(book_id)).timezone)

        if loan.kind == "capital":
            return await self._pay_capital(loan, user_id, paid, paid_on)

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

    async def _pay_capital(self, loan: Loan, user_id: uuid.UUID, paid: int, paid_on: date):
        """An installment of a loan that bought something kept.

        Most of it repays the debt, which is not an expense; only what exceeds the share of the
        principal it carries is interest, and that is an ordinary personal expense. The shares are
        even, and the last installment takes whatever principal is left so the debt ends at zero.
        """
        from ..capital.posting import CASH, LOANS, post_movement

        principal = quantize(to_decimal(loan.principal or ZERO))
        count = int(loan.installment_count)
        share = quantize(principal / count)
        repaid = principal - share * paid if paid == count - 1 else share
        repaid = min(max(repaid, ZERO), quantize(to_decimal(loan.installment_amount)))
        interest = quantize(to_decimal(loan.installment_amount)) - repaid

        if repaid > ZERO:
            await post_movement(
                self.session, loan.book_id, user_id, paid_on, "loan_principal",
                [(LOANS, repaid, ZERO), (CASH, ZERO, repaid)],
                cash_delta=-repaid, memo=f"قسط وام: {loan.title}", loan_id=loan.id,
            )
        transaction = None
        if interest > ZERO:
            transaction = await self.ledger.record(
                book_id=loan.book_id, actor_user_id=user_id, flow=Flow.EXPENSE,
                scope=Scope.PERSONAL, category=INTEREST_CATEGORY, amount=interest,
                description=loan.title, occurred_on=paid_on,
            )
        self.session.add(
            LoanPayment(
                loan_id=loan.id,
                transaction_id=transaction.id if transaction is not None else None,
                paid_on=paid_on,
            )
        )
        await self.session.flush()
        return transaction

    async def delete(
        self, book_id: uuid.UUID, user_id: uuid.UUID, loan_id: uuid.UUID
    ) -> None:
        """Forget the loan, keep its payments: that money really moved.

        `loan_payments` links a loan to the transaction that paid an instalment.
        The link goes with the loan — the foreign key is ON DELETE CASCADE, so
        the database removes it — and the transaction stays, because it records
        money that actually left the account.
        """
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)

        loan = await self._owned(book_id, loan_id)
        if loan.kind == "capital":
            # Its debt is on the books with what it bought; forgetting only the loan would leave both.
            raise ValidationError("این وام به یک دارایی وصل است؛ از بخش دارایی‌ها حذفش کن.")
        await self.session.delete(loan)
        await self.session.flush()
