"""Who owes whom, kept apart from income and expense on purpose.

A debt never writes an income or an expense by itself: a credit sale is already income. What it can
write, when a bank account is named, is the cash that really moved: lending, borrowing, being paid back,
paying back. That is a journal entry on the account against a receivable or payable account (see
`models.py`), so the account's balance is true and no report of income or expense moves.

`bank_account_id` here means: left out, no cash moved (a debt from a credit sale moved none); an id, the
account the cash went through; `None`, none. It is the opposite of the other flows' default on purpose:
guessing "cash moved" for a credit sale would count the same money twice.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..banks.service import UNSET, BankService
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import JournalEntry, Transaction
from .models import INCREASE, PAYMENT, Debt, DebtMovement, Direction

# Where the other side of the cash sits: money lent is a receivable (an asset), money borrowed a payable.
RECEIVABLE = "1710"
PAYABLE = "2100"


@dataclass(frozen=True)
class DebtTotals:
    owed_to_me: Decimal
    i_owe: Decimal

    @property
    def net(self) -> Decimal:
        return self.owed_to_me - self.i_owe


class DebtService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    # ------------------------------------------------------------- movements
    async def _cash(self, debt: Debt, kind: str, value: Decimal, on: date, note, user_id, bank_account_id):
        """Write what happened to a debt, and the cash with it when an account is named."""
        book = await self.books.get_book(debt.book_id)
        link = None
        if bank_account_id is not UNSET and bank_account_id is not None:
            link = await BankService(self.session).resolve(
                debt.book_id, bank_account_id, in_base_currency=debt.currency == book.base_currency
            )
        movement = DebtMovement(
            debt_id=debt.id, book_id=debt.book_id, kind=kind, amount=value, occurred_on=on,
            note=(note or "").strip()[:300] or None, actor_user_id=user_id,
        )
        if link is not None:
            from ..ledger.service import LedgerService

            ledger = LedgerService(self.session)
            await ledger._require_open_date(debt.book_id, on)
            await ledger.ensure_chart_of_accounts(debt.book_id)
            counter = await ledger.account(
                debt.book_id, RECEIVABLE if debt.direction is Direction.OWED_TO_ME else PAYABLE
            )
            bank = await ledger._money_account(debt.book_id, link)
            # Lending and paying a debt of mine take cash out; borrowing and being paid back bring it in.
            out = (debt.direction is Direction.OWED_TO_ME) == (kind == INCREASE)
            lines = ([(counter.id, value, ZERO), (bank.id, ZERO, value)] if out
                     else [(bank.id, value, ZERO), (counter.id, ZERO, value)])
            entry = await ledger.post_entry(debt.book_id, on, lines, memo=f"debt {kind}")
            movement.bank_account_id = link.bank_account_id
            movement.journal_entry_id = entry.id
            movement.cash_delta = -value if out else value
        self.session.add(movement)
        await self.session.flush()
        return movement

    async def create(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        person: str,
        direction: Direction,
        amount,
        note: Optional[str] = None,
        due_on: Optional[date] = None,
        bank_account_id=UNSET,
        occurred_on: Optional[date] = None,
    ) -> Debt:
        await self.books.require(book_id, user_id, Permission.RECORD_INCOME)

        person = (person or "").strip()
        if not person:
            raise ValidationError("نام طرف حساب لازم است")

        value = quantize(to_decimal(amount))
        # Zero was let through while loans and recurring rules refused it, and a
        # debt of nothing sat in the list as a position.
        if value <= ZERO:
            raise ValidationError("مبلغ باید بیشتر از صفر باشد؛ مثلاً 500 هزار.")

        book = await self.books.get_book(book_id)
        debt = Debt(
            book_id=book_id,
            person=person[:80],
            direction=direction,
            amount=value,
            currency=book.base_currency,
            note=note,
            due_on=due_on,
        )
        self.session.add(debt)
        await self.session.flush()
        # Its first entry in the history, so the history adds up to the debt from the start.
        await self._cash(
            debt, INCREASE, value, occurred_on or jalali.today_in(book.timezone), None, user_id,
            bank_account_id,
        )
        return debt

    async def _owned(self, book_id: uuid.UUID, debt_id: uuid.UUID) -> Debt:
        debt = await self.session.get(Debt, debt_id)
        if debt is None or debt.book_id != book_id:
            raise NotFound("این مورد پیدا نشد")
        return debt

    async def increase(
        self, book_id: uuid.UUID, user_id: uuid.UUID, debt_id: uuid.UUID, amount,
        occurred_on: Optional[date] = None, note: Optional[str] = None, bank_account_id=UNSET,
    ) -> Debt:
        """It grew: more was lent to them, or more was borrowed from them. A settled debt that grows is open again."""
        await self.books.require(book_id, user_id, Permission.RECORD_INCOME)
        debt = await self._owned(book_id, debt_id)
        value = quantize(to_decimal(amount))
        if value <= ZERO:
            raise ValidationError("مبلغ باید بیشتر از صفر باشد.")
        book = await self.books.get_book(book_id)
        await self._cash(
            debt, INCREASE, value, occurred_on or jalali.today_in(book.timezone), note, user_id,
            bank_account_id,
        )
        debt.amount = quantize(to_decimal(debt.amount) + value)
        debt.settled_at = None
        await self.session.flush()
        return debt

    async def settle(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        debt_id: uuid.UUID,
        record_transaction: bool = False,
        amount=None,
        occurred_on: Optional[date] = None,
        note: Optional[str] = None,
        bank_account_id=UNSET,
    ) -> Debt:
        """Pay the debt, in whole or in part, and — only when asked — record the money moving.

        With no `amount` the whole of what is left is paid and the debt closes.
        A smaller amount is a part payment: the debt stays open with less left.

        Whether settling is income or expense depends on what was recorded
        when the debt arose: if the sale on credit, or the purchase, is already
        in the books, booking the payment as well counts it twice. The service
        cannot know, so it does not guess; the caller asks the person (owner
        decision D-2) and the default is to close the debt only.

        A payment with a bank account is cash that really moved: it takes the money off or puts it on
        that account and is neither income nor expense. `record_transaction` is the other way to say
        the money moved, as income or an expense, and then the account is the transaction's.
        """
        await self.books.require(book_id, user_id, Permission.RECORD_INCOME)

        debt = await self._owned(book_id, debt_id)
        if debt.settled_at is not None:
            # A second press must not record the money a second time.
            raise ValidationError(f"«{debt.person}» قبلاً تسویه شده است.")

        remaining = quantize(debt.remaining)
        value = remaining if amount is None else quantize(to_decimal(amount))
        if value <= ZERO:
            raise ValidationError("مبلغ باید بیشتر از صفر باشد")
        if value > remaining:
            raise ValidationError("این مبلغ از باقی‌ماندهٔ بدهی بیشتر است.")
        book = await self.books.get_book(book_id)
        on = occurred_on or jalali.today_in(book.timezone)

        recorded = None
        if record_transaction:
            if bank_account_id is not UNSET and bank_account_id is not None:
                # Checked before anything is written; the ledger resolves it again when it records.
                await BankService(self.session).resolve(
                    book_id, bank_account_id, in_base_currency=debt.currency == book.base_currency
                )
            from ..ledger.models import Flow
            from ..ledger.service import LedgerService
            from ..recurring.service import SCOPE_FOR_BOOK

            received = debt.direction is Direction.OWED_TO_ME
            recorded = await LedgerService(self.session).record(
                book_id=book_id,
                actor_user_id=user_id,
                flow=Flow.INCOME if received else Flow.EXPENSE,
                scope=SCOPE_FOR_BOOK[book.type],
                category="تسویه طلب" if received else "تسویه بدهی",
                amount=value,
                description=f"تسویه با {debt.person}",
                occurred_on=on,
                # Left out is the book's default account, as for any income or expense; null is none.
                bank_account_id=bank_account_id,
            )
            movement = await self._cash(debt, PAYMENT, value, on, note, user_id, UNSET)
            movement.transaction_id = recorded.id
        else:
            await self._cash(debt, PAYMENT, value, on, note, user_id, bank_account_id)

        debt.paid_amount = quantize(to_decimal(debt.paid_amount or 0) + value)
        if value == remaining:
            debt.settled_at = datetime.now(timezone.utc)
        await self.session.flush()
        return debt

    async def with_cash(self, debt_ids: Sequence[uuid.UUID]) -> set:
        """Which of these debts have real cash in their history (no permission check: the caller already
        listed them)."""
        if not debt_ids:
            return set()
        return set((await self.session.scalars(
            select(DebtMovement.debt_id).where(
                DebtMovement.debt_id.in_(list(debt_ids)),
                (DebtMovement.journal_entry_id.is_not(None)) | (DebtMovement.transaction_id.is_not(None)),
            ).distinct()
        )).all())

    async def movements(
        self, book_id: uuid.UUID, user_id: uuid.UUID, debt_id: uuid.UUID
    ) -> List[DebtMovement]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        await self._owned(book_id, debt_id)
        return list((await self.session.scalars(
            select(DebtMovement).where(DebtMovement.debt_id == debt_id)
            .order_by(DebtMovement.occurred_on.desc(), DebtMovement.created_at.desc())
        )).all())

    async def void_movement(
        self, book_id: uuid.UUID, user_id: uuid.UUID, debt_id: uuid.UUID, movement_id: uuid.UUID
    ) -> Debt:
        """Take one back: a payment that was a mistake, or an amount added by mistake.

        Its cash goes with it (the entry, or the income or expense it was recorded as), so the account
        is where it was. A debt cannot be taken below what was already paid, or to nothing: that is
        deleting the debt.
        """
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)
        debt = await self._owned(book_id, debt_id)
        movement = await self.session.get(DebtMovement, movement_id)
        if movement is None or movement.debt_id != debt.id:
            raise NotFound("این مورد پیدا نشد")
        amount = to_decimal(movement.amount)
        if movement.kind == INCREASE:
            after = quantize(to_decimal(debt.amount) - amount)
            if after <= ZERO or after < quantize(to_decimal(debt.paid_amount or 0)):
                raise ValidationError(
                    "با برداشتن این مبلغ، بدهی از آنچه تاکنون پرداخت شده کمتر می‌شود؛ اول پرداخت‌ها را برگردان یا خود بدهی را حذف کن."
                )
            debt.amount = after
        else:
            debt.paid_amount = quantize(to_decimal(debt.paid_amount or 0) - amount)
            debt.settled_at = None
        if movement.journal_entry_id is not None:
            from ..ledger.service import LedgerService

            await LedgerService(self.session)._require_open_date(book_id, movement.occurred_on)
            entry = await self.session.get(JournalEntry, movement.journal_entry_id)
            if entry is not None:
                await self.session.delete(entry)
        if movement.transaction_id is not None:
            from ..ledger.service import LedgerService

            tx = await self.session.get(Transaction, movement.transaction_id)
            if tx is not None:
                await LedgerService(self.session).delete(book_id, user_id, tx.id)
        await self.session.flush()
        await self.session.delete(movement)
        await self.session.flush()
        return debt

    async def delete(
        self, book_id: uuid.UUID, user_id: uuid.UUID, debt_id: uuid.UUID, undo_cash: bool = False
    ) -> None:
        """Forget a debt. If real cash moved on it, that has to be said: forgetting it leaves the accounts
        as they are, so it is refused; `undo_cash` takes the cash back too, as if it never happened."""
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)

        debt = await self._owned(book_id, debt_id)
        cash = (await self.session.scalars(select(DebtMovement).where(
            DebtMovement.debt_id == debt.id,
            (DebtMovement.journal_entry_id.is_not(None)) | (DebtMovement.transaction_id.is_not(None)),
        ))).all()
        if cash and not undo_cash:
            # Real cash is in its history: forgetting the debt would leave an account without the reason.
            raise ValidationError(
                "روی این مورد پول واقعی جابه‌جا شده؛ برای حذف باید پولش هم از حساب‌ها برگردد."
            )
        if cash:
            from ..ledger.service import LedgerService

            ledger = LedgerService(self.session)
            for movement in cash:
                if movement.journal_entry_id is not None:
                    await ledger._require_open_date(book_id, movement.occurred_on)
                    entry = await self.session.get(JournalEntry, movement.journal_entry_id)
                    if entry is not None:
                        await self.session.delete(entry)
                if movement.transaction_id is not None:
                    await ledger.delete(book_id, user_id, movement.transaction_id)
            await self.session.flush()
        await self.session.delete(debt)
        await self.session.flush()

    async def list_debts(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        include_settled: bool = False,
    ) -> Sequence[Debt]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)

        stmt = select(Debt).where(Debt.book_id == book_id)
        if not include_settled:
            stmt = stmt.where(Debt.settled_at.is_(None))

        stmt = stmt.order_by(Debt.due_on.is_(None), Debt.due_on, Debt.created_at.desc())
        return (await self.session.execute(stmt)).scalars().all()

    async def totals(self, book_id: uuid.UUID, user_id: uuid.UUID) -> DebtTotals:
        """Only open debts count: a settled one is history, not a position."""
        owed = ZERO
        mine = ZERO

        for debt in await self.list_debts(book_id, user_id, include_settled=False):
            # What is still outstanding, not what it started as.
            left = debt.remaining
            if debt.direction is Direction.OWED_TO_ME:
                owed += left
            else:
                mine += left

        return DebtTotals(quantize(owed), quantize(mine))
