"""Recording money, and keeping the ledger provably balanced.

Recording a transaction is one operation: it writes the user-facing row *and*
its journal entry in the same flush. Nothing else in the system is allowed to
write journal lines, which is why "debits equal credits" is a property of the
data rather than a hope.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import BalanceError, NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from .models import (
    DEBIT_POSITIVE,
    Account,
    AccountType,
    Flow,
    JournalEntry,
    JournalLine,
    RateMode,
    Scope,
    Transaction,
)

# The minimum chart of accounts a book needs to record anything at all.
DEFAULT_ACCOUNTS = (
    ("1000", "نقد و بانک", AccountType.ASSET),
    ("4000", "درآمد", AccountType.INCOME),
    ("5000", "هزینه", AccountType.EXPENSE),
    ("2000", "بدهی", AccountType.LIABILITY),
    ("3000", "سرمایه", AccountType.EQUITY),
    ("1900", "خزانه", AccountType.ASSET),
)

CASH = "1000"
INCOME = "4000"
EXPENSE = "5000"


class LedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    # -------------------------------------------------------------- accounts
    async def ensure_chart_of_accounts(self, book_id: uuid.UUID) -> None:
        existing = {
            code
            for (code,) in (
                await self.session.execute(
                    select(Account.code).where(Account.book_id == book_id)
                )
            ).all()
        }
        for code, name, kind in DEFAULT_ACCOUNTS:
            if code not in existing:
                self.session.add(
                    Account(book_id=book_id, code=code, name=name, type=kind)
                )
        await self.session.flush()

    async def account(self, book_id: uuid.UUID, code: str) -> Account:
        stmt = select(Account).where(Account.book_id == book_id, Account.code == code)
        found = (await self.session.execute(stmt)).scalar_one_or_none()
        if found is None:
            raise NotFound(f"account {code}")
        return found

    # ---------------------------------------------------------- transactions
    async def record(
        self,
        book_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        flow: Flow,
        scope: Scope,
        category: str,
        amount,
        occurred_on: Optional[date] = None,
        description: Optional[str] = None,
        currency: Optional[str] = None,
        conversion_rate=None,
        rate_source: Optional[str] = None,
        rate_at: Optional[datetime] = None,
        rate_mode: RateMode = RateMode.MANUAL,
    ) -> Transaction:
        """Record one transaction and its balanced journal entry."""
        needed = (
            Permission.RECORD_INCOME if flow is Flow.INCOME else Permission.RECORD_EXPENSE
        )
        await self.books.require(book_id, actor_user_id, needed)

        book = await self.books.get_book(book_id)
        original = quantize(amount)
        if original < ZERO:
            raise ValidationError("an amount is never negative; use the other flow")

        original_currency = (currency or book.base_currency).upper()
        if original_currency == book.base_currency:
            rate = Decimal("1")
        else:
            if conversion_rate is None:
                raise ValidationError(
                    f"a {original_currency} amount needs a rate into {book.base_currency}"
                )
            rate = to_decimal(conversion_rate)
            if rate <= ZERO:
                raise ValidationError("a conversion rate must be positive")

        transaction = Transaction(
            book_id=book_id,
            actor_user_id=actor_user_id,
            occurred_on=occurred_on or date.today(),
            flow=flow,
            scope=scope,
            category=category.strip(),
            description=description,
            original_amount=original,
            original_currency=original_currency,
            base_currency=book.base_currency,
            conversion_rate=rate,
            # Frozen at record time: a report of last month never moves when
            # today's rate does.
            converted_amount=quantize(original * rate),
            rate_source=rate_source,
            rate_at=rate_at,
            rate_mode=rate_mode,
        )
        self.session.add(transaction)
        await self.session.flush()

        await self.ensure_chart_of_accounts(book_id)
        cash = await self.account(book_id, CASH)
        other = await self.account(
            book_id, INCOME if flow is Flow.INCOME else EXPENSE
        )

        if flow is Flow.INCOME:
            pairs = [(cash.id, transaction.converted_amount, ZERO),
                     (other.id, ZERO, transaction.converted_amount)]
        else:
            pairs = [(other.id, transaction.converted_amount, ZERO),
                     (cash.id, ZERO, transaction.converted_amount)]

        await self.post_entry(
            book_id=book_id,
            occurred_on=transaction.occurred_on,
            lines=pairs,
            memo=f"{flow.value}: {transaction.category}",
            transaction_id=transaction.id,
        )
        return transaction

    async def post_entry(
        self,
        book_id: uuid.UUID,
        occurred_on: date,
        lines: Sequence[Tuple[uuid.UUID, object, object]],
        memo: Optional[str] = None,
        transaction_id: Optional[uuid.UUID] = None,
    ) -> JournalEntry:
        """Write a journal entry, refusing anything that does not balance."""
        if len(lines) < 2:
            raise BalanceError("a journal entry needs at least two lines")

        entry = JournalEntry(
            book_id=book_id,
            occurred_on=occurred_on,
            memo=memo,
            transaction_id=transaction_id,
        )

        total_debit = ZERO
        total_credit = ZERO
        for account_id, debit, credit in lines:
            d, c = quantize(debit), quantize(credit)
            if d < ZERO or c < ZERO:
                raise BalanceError("a journal line is never negative")
            if d > ZERO and c > ZERO:
                raise BalanceError("a line is either a debit or a credit, not both")
            total_debit += d
            total_credit += c
            entry.lines.append(JournalLine(account_id=account_id, debit=d, credit=c))

        if total_debit != total_credit:
            raise BalanceError(
                f"debits {total_debit} do not equal credits {total_credit}"
            )
        if total_debit == ZERO:
            raise BalanceError("an entry of zero moves nothing")

        self.session.add(entry)
        await self.session.flush()
        return entry

    # -------------------------------------------------------------- reading
    async def transactions(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> Sequence[Transaction]:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)

        stmt = select(Transaction).where(Transaction.book_id == book_id)
        if since is not None:
            stmt = stmt.where(Transaction.occurred_on >= since)
        if until is not None:
            stmt = stmt.where(Transaction.occurred_on <= until)

        stmt = stmt.order_by(Transaction.occurred_on, Transaction.created_at)
        return (await self.session.execute(stmt)).scalars().all()

    async def totals(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        since: Optional[date] = None,
        until: Optional[date] = None,
    ) -> dict:
        rows = await self.transactions(book_id, user_id, since, until)

        income = sum(
            (t.converted_amount for t in rows if t.flow is Flow.INCOME), ZERO
        )
        expense = sum(
            (t.converted_amount for t in rows if t.flow is Flow.EXPENSE), ZERO
        )
        return {"income": income, "expense": expense, "net": income - expense}

    async def account_balance(self, account_id: uuid.UUID) -> Decimal:
        """Signed by the account's natural side, so a healthy balance is positive."""
        account = await self.session.get(Account, account_id)
        if account is None:
            raise NotFound("account")

        rows = (
            await self.session.execute(
                select(JournalLine).where(JournalLine.account_id == account_id)
            )
        ).scalars().all()

        debit = sum((line.debit for line in rows), ZERO)
        credit = sum((line.credit for line in rows), ZERO)
        return debit - credit if account.type in DEBIT_POSITIVE else credit - debit

    async def trial_balance(self, book_id: uuid.UUID) -> Tuple[Decimal, Decimal]:
        """Every debit and credit in the book. These must be equal, always."""
        rows = (
            await self.session.execute(
                select(JournalLine)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .where(JournalEntry.book_id == book_id)
            )
        ).scalars().all()

        return (
            sum((line.debit for line in rows), ZERO),
            sum((line.credit for line in rows), ZERO),
        )
