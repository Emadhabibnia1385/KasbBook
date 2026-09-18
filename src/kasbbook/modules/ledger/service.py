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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import BalanceError, NotFound, PermissionDenied, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from ..identity.models import AuditEvent
from ..loans.models import LoanPayment
from ..payroll.models import FinancialPeriod, PeriodStatus, Payslip
from .categories import CategoryService
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
UNSET = object()


class LedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)
        self.categories = CategoryService(session)

    async def _require_open_date(self, book_id, on):
        periods = (await self.session.scalars(select(FinancialPeriod).where(
            FinancialPeriod.book_id == book_id, FinancialPeriod.starts_on <= on,
            FinancialPeriod.ends_on >= on
        ))).all()
        for period in periods:
            if period.status is not PeriodStatus.OPEN or await self.session.scalar(
                select(Payslip.id).where(Payslip.period_id == period.id).limit(1)
            ):
                raise PermissionDenied("این تاریخ در دورهٔ محاسبه‌شده یا بسته است؛ اصلاح را در دورهٔ باز ثبت کن.")

    @staticmethod
    def _description(value):
        if value is not None and len(value) > 500:
            raise ValidationError("توضیحات حداکثر ۵۰۰ حرف است.")
        return (value.strip() or None) if value is not None else None

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
        receipt_file_id: Optional[str] = None,
        receipt_provider: Optional[str] = None,
        receipt_kind: Optional[str] = None,
        receipt_file_name: Optional[str] = None,
        receipt_mime_type: Optional[str] = None,
    ) -> Transaction:
        """Record one transaction and its balanced journal entry."""
        needed = (
            Permission.RECORD_INCOME if flow is Flow.INCOME else Permission.RECORD_EXPENSE
        )
        await self.books.require(book_id, actor_user_id, needed)

        await self.categories.lock_book(book_id)

        book = await self.books.get_book(book_id)
        on = occurred_on or jalali.today_in(book.timezone)
        await self._require_open_date(book_id, on)
        category = self.categories.name(category)
        description = self._description(description)
        self._validate_receipt(receipt_file_id, receipt_provider, receipt_kind,
                               receipt_file_name, receipt_mime_type)
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

        converted = quantize(original * rate)
        if converted <= ZERO:
            raise BalanceError("an entry of zero moves nothing")
        category_row = await self.categories._ensure(book_id, category)
        transaction = Transaction(
            book_id=book_id,
            actor_user_id=actor_user_id,
            # The book's day, not the server's: see jalali.today_in.
            occurred_on=on,
            flow=flow,
            scope=scope,
            category=category.strip(),
            category_id=category_row.id,
            description=description,
            receipt_file_id=receipt_file_id,
            receipt_provider=receipt_provider if receipt_file_id else None,
            receipt_kind=receipt_kind if receipt_file_id else None,
            receipt_file_name=receipt_file_name if receipt_file_id else None,
            receipt_mime_type=receipt_mime_type if receipt_file_id else None,
            original_amount=original,
            original_currency=original_currency,
            base_currency=book.base_currency,
            conversion_rate=rate,
            # Frozen at record time: a report of last month never moves when
            # today's rate does.
            converted_amount=converted,
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

    async def recent_categories(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        flow: Flow,
        limit: int = 6,
    ) -> Sequence[str]:
        """The categories this book actually uses, most recent first.

        Ordered by last use rather than by count, because a shop's categories
        drift: what was typed most often last year is not what is being typed
        this week, and the point of offering them is to save typing the next
        one — not to be a historically accurate ranking.
        """
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)

        rows = (
            await self.session.execute(
                select(Transaction.category, func.max(Transaction.created_at))
                .where(Transaction.book_id == book_id, Transaction.flow == flow)
                .group_by(Transaction.category)
                .order_by(func.max(Transaction.created_at).desc())
                .limit(limit)
            )
        ).all()
        return [row[0] for row in rows]

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

    async def attach_receipt(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        transaction_id: uuid.UUID,
        file_id: Optional[str],
        provider: Optional[str],
        kind: Optional[str] = None,
        file_name: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Transaction:
        """Point a transaction at a receipt the messenger is already holding.

        Passing `file_id=None` detaches it. Every field goes with it — a name
        left behind on a transaction with no receipt is a screen confidently
        describing a file that is not there any more.
        """
        await self.books.require(book_id, user_id, Permission.EDIT_TRANSACTION)
        self._validate_receipt(file_id, provider, kind, file_name, mime_type)

        transaction = await self.session.get(Transaction, transaction_id)
        if transaction is None or transaction.book_id != book_id:
            raise NotFound("این تراکنش پیدا نشد")

        transaction.receipt_file_id = file_id
        transaction.receipt_provider = provider if file_id else None
        transaction.receipt_kind = kind if file_id else None
        transaction.receipt_file_name = (file_name or None) if file_id else None
        transaction.receipt_mime_type = (mime_type or None) if file_id else None
        await self.session.flush()
        return transaction

    async def get_transaction(
        self, book_id: uuid.UUID, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> Transaction:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)

        transaction = await self.session.get(Transaction, transaction_id)
        if transaction is None or transaction.book_id != book_id:
            raise NotFound("این تراکنش پیدا نشد")
        return transaction

    @staticmethod
    def _validate_receipt(file_id, provider, kind, file_name, mime_type):
        if not file_id:
            return
        if (len(file_id) > 256 or provider not in ("telegram", "bale", "rubika")
                or kind not in (None, "photo", "document", "voice", "other")
                or len(file_name or "") > 200 or len(mime_type or "") > 120):
            raise ValidationError("اطلاعات پیوست معتبر نیست.")

    async def update(
        self, book_id, actor_user_id, transaction_id, *, category=UNSET,
        amount=UNSET, description=UNSET,
    ) -> Transaction:
        await self.books.require(book_id, actor_user_id, Permission.EDIT_TRANSACTION)
        if all(value is UNSET for value in (category, amount, description)):
            raise ValidationError("یک تغییر معتبر بفرست.")
        if category is None or amount is None:
            raise ValidationError("دسته و مبلغ نمی‌تواند خالی باشد.")
        await self.categories.lock_book(book_id)
        tx = await self.session.scalar(select(Transaction).where(
            Transaction.id == transaction_id, Transaction.book_id == book_id
        ).with_for_update().execution_options(populate_existing=True))
        if tx is None:
            raise NotFound("این تراکنش پیدا نشد.")
        await self._require_open_date(book_id, tx.occurred_on)
        new_category = self.categories.name(category) if category is not UNSET else tx.category
        new_description = self._description(description) if description is not UNSET else tx.description
        original = quantize(amount) if amount is not UNSET else tx.original_amount
        if original <= ZERO:
            raise ValidationError("مبلغ باید بیشتر از صفر باشد.")
        if amount is not UNSET and await self.session.scalar(select(LoanPayment.id).where(
            LoanPayment.transaction_id == tx.id
        ).limit(1)):
            raise ValidationError("مبلغ پرداخت قسط از این صفحه قابل ویرایش نیست.")
        converted = quantize(original * tx.conversion_rate)
        if converted <= ZERO:
            raise ValidationError("مبلغ تبدیل‌شده باید بیشتر از صفر باشد.")
        entries = (await self.session.scalars(select(JournalEntry).where(
            JournalEntry.book_id == book_id, JournalEntry.transaction_id == tx.id
        ))).all()
        if (len(entries) != 1 or not entries[0].is_balanced
                or entries[0].total_debit != tx.converted_amount):
            raise BalanceError("سند این تراکنش معتبر نیست؛ ویرایش انجام نشد.")
        if amount is not UNSET:
            cash = await self.account(book_id, CASH)
            other = await self.account(book_id, INCOME if tx.flow is Flow.INCOME else EXPENSE)
        category_row = await self.categories._ensure(book_id, new_category)
        tx.category, tx.category_id = category_row.name, category_row.id
        tx.description = new_description
        if amount is not UNSET:
            # Rebuild through the one ledger writer using the frozen conversion
            # rate; neither client is allowed to write individual journal lines.
            await self.session.delete(entries[0])
            await self.session.flush()
            lines = ([(cash.id, converted, ZERO), (other.id, ZERO, converted)]
                     if tx.flow is Flow.INCOME else
                     [(other.id, converted, ZERO), (cash.id, ZERO, converted)])
            tx.original_amount, tx.converted_amount = original, converted
            await self.post_entry(book_id, tx.occurred_on, lines,
                                  memo=f"{tx.flow.value}: {tx.category}", transaction_id=tx.id)
        else:
            entries[0].memo = f"{tx.flow.value}: {tx.category}"
        self.session.add(AuditEvent(user_id=actor_user_id, action="transaction.updated", subject=str(tx.id)))
        await self.session.flush()
        return tx

    async def delete(
        self, book_id: uuid.UUID, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> None:
        """Remove a transaction and the journal entry that mirrors it.

        The entry exists only to make this transaction's totals provable, so it
        has no meaning once the transaction is gone. Removing a balanced entry
        whole keeps the book balanced — which is checked by a test, because
        removing only part of one would not.
        """
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)
        await self.categories.lock_book(book_id)

        transaction = await self.session.get(Transaction, transaction_id)
        if transaction is None or transaction.book_id != book_id:
            raise NotFound("این تراکنش پیدا نشد")

        await self._require_open_date(book_id, transaction.occurred_on)

        # journal_entries → transactions and journal_lines → journal_entries are
        # both ON DELETE CASCADE, so removing the transaction takes the whole
        # entry with it. Walking the tree by hand did the same thing twice and
        # warned that the second pass matched nothing.
        await self.session.delete(transaction)
        await self.session.flush()

