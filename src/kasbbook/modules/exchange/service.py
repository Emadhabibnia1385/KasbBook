"""What a book is allowed to hold, what it actually holds, and swapping between.

The balances here are derived, never stored. A stored balance is a second copy
of a number the transactions already contain, and the two drift the first time
anything is edited or deleted — which is the failure this project keeps having.
Summing on read costs a query; a wrong wallet costs trust.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import Flow, Transaction
from .models import CURRENCY_NAMES, OFFERED, BookCurrency, CurrencyConversion

@dataclass(frozen=True)
class CurrencyBalance:
    code: str
    amount: Decimal
    is_base: bool

    @property
    def name(self) -> str:
        return CURRENCY_NAMES.get(self.code, self.code)


@dataclass(frozen=True)
class CurrencyOption:
    code: str
    enabled: bool
    is_base: bool

    @property
    def name(self) -> str:
        return CURRENCY_NAMES.get(self.code, self.code)


class ExchangeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    # ------------------------------------------------------------ currencies
    async def allowed(self, book_id: uuid.UUID) -> List[str]:
        """Every currency this book may hold, its own first.

        No permission check: every caller has already passed one, and the
        ledger needs this while recording, inside a gate of its own.
        """
        book = await self.books.get_book(book_id)
        rows = (
            await self.session.execute(
                select(BookCurrency).where(
                    BookCurrency.book_id == book_id,
                    BookCurrency.is_active.is_(True),
                ).order_by(BookCurrency.code)
            )
        ).scalars().all()
        extra = [r.code for r in rows if r.code != book.base_currency]
        return [book.base_currency] + extra

    async def options(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID
    ) -> List[CurrencyOption]:
        """Every currency that could be ticked, and whether it is."""
        await self.books.require(book_id, actor_user_id, Permission.VIEW_REPORTS)
        book = await self.books.get_book(book_id)
        live = set(await self.allowed(book_id))
        codes = [book.base_currency] + [c for c in OFFERED if c != book.base_currency]
        return [
            CurrencyOption(code=c, enabled=c in live, is_base=c == book.base_currency)
            for c in codes
        ]

    async def set_enabled(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID, code: str, enabled: bool
    ) -> None:
        """Tick or untick one currency for this book."""
        await self.books.require(book_id, actor_user_id, Permission.MANAGE_TREASURY)
        book = await self.books.get_book(book_id)
        code = code.upper()

        if code == book.base_currency:
            raise ValidationError("ارز پایهٔ دفتر همیشه فعال است.")
        if code not in OFFERED:
            raise ValidationError(f"ارز {code} پشتیبانی نمی‌شود.")

        if not enabled:
            # Switching a currency off must not hide money. What the book holds
            # comes from its transactions, so the balance survives either way —
            # but letting a non-zero holding fall off the entry menu is how a
            # wallet quietly stops being reconciled.
            held = await self.balance_of(book_id, code)
            if held != ZERO:
                raise ValidationError(
                    f"هنوز {held} {CURRENCY_NAMES.get(code, code)} در کیف پول هست؛ "
                    "اول تبدیلش کن."
                )

        row = (
            await self.session.execute(
                select(BookCurrency).where(
                    BookCurrency.book_id == book_id, BookCurrency.code == code
                )
            )
        ).scalar_one_or_none()

        if row is None:
            self.session.add(
                BookCurrency(book_id=book_id, code=code, is_active=enabled)
            )
        else:
            row.is_active = enabled
        await self.session.flush()

    # -------------------------------------------------------------- balances
    async def balance_of(self, book_id: uuid.UUID, code: str) -> Decimal:
        """What the book holds of one currency. No permission check — internal."""
        for balance in await self._balances(book_id):
            if balance.code == code.upper():
                return balance.amount
        return ZERO

    async def balances(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID
    ) -> List[CurrencyBalance]:
        await self.books.require(book_id, actor_user_id, Permission.VIEW_REPORTS)
        return await self._balances(book_id)

    async def _balances(self, book_id: uuid.UUID) -> List[CurrencyBalance]:
        book = await self.books.get_book(book_id)
        totals: dict = {code: ZERO for code in await self.allowed(book_id)}

        def add(code: str, amount: Decimal) -> None:
            totals[code] = totals.get(code, ZERO) + amount

        # Only the three columns, summed in Python. func.sum() over a Money
        # column returns a float on SQLite, where the type is stored as text —
        # exactly the loss shared/money.py exists to prevent.
        rows = (
            await self.session.execute(
                select(
                    Transaction.original_currency,
                    Transaction.original_amount,
                    Transaction.flow,
                ).where(Transaction.book_id == book_id)
            )
        ).all()
        for code, amount, flow in rows:
            add(code, to_decimal(amount) if flow is Flow.INCOME else -to_decimal(amount))

        swaps = (
            await self.session.execute(
                select(
                    CurrencyConversion.from_currency,
                    CurrencyConversion.from_amount,
                    CurrencyConversion.to_currency,
                    CurrencyConversion.to_amount,
                ).where(CurrencyConversion.book_id == book_id)
            )
        ).all()
        for from_code, from_amount, to_code, to_amount in swaps:
            add(from_code, -to_decimal(from_amount))
            add(to_code, to_decimal(to_amount))

        order = await self.allowed(book_id)
        return [
            CurrencyBalance(
                code=code,
                amount=quantize(totals[code]),
                is_base=code == book.base_currency,
            )
            for code in sorted(totals, key=lambda c: (c not in order, order.index(c) if c in order else 0))
        ]

    async def require_funds(
        self, book_id: uuid.UUID, code: str, amount: Decimal
    ) -> None:
        """Refuse to spend a currency the book does not hold.

        The base currency is exempt. Its "balance" here is income minus expense,
        not a bank balance — nothing records an opening balance or a transfer in
        from outside — so enforcing it would refuse the first expense of every
        new book. A held token is different: it only exists here because it was
        recorded arriving.
        """
        book = await self.books.get_book(book_id)
        code = code.upper()
        if code == book.base_currency:
            return

        held = await self.balance_of(book_id, code)
        if amount > held:
            name = CURRENCY_NAMES.get(code, code)
            raise ValidationError(
                f"موجودی {name} کافی نیست: {held} در کیف پول هست و {amount} خواسته شد."
            )

    # ----------------------------------------------------------- conversions
    async def convert(
        self,
        actor_user_id: uuid.UUID,
        book_id: uuid.UUID,
        from_currency: str,
        from_amount,
        to_currency: str,
        to_amount,
        base_value=None,
        occurred_on: Optional[date] = None,
        note: Optional[str] = None,
    ) -> CurrencyConversion:
        """Move value from one of the book's currencies into another."""
        await self.books.require(book_id, actor_user_id, Permission.MANAGE_TREASURY)
        book = await self.books.get_book(book_id)

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        if from_currency == to_currency:
            raise ValidationError("مبدأ و مقصد تبدیل یکی است.")

        allowed = await self.allowed(book_id)
        for code in (from_currency, to_currency):
            if code not in allowed:
                raise ValidationError(
                    f"این دفتر {CURRENCY_NAMES.get(code, code)} را پشتیبانی نمی‌کند."
                )

        out_amount = quantize(from_amount)
        in_amount = quantize(to_amount)
        if out_amount <= ZERO or in_amount <= ZERO:
            raise ValidationError("مقدار تبدیل باید بیشتر از صفر باشد.")

        await self.require_funds(book_id, from_currency, out_amount)

        if to_currency == book.base_currency:
            base = in_amount
        elif from_currency == book.base_currency:
            base = out_amount
        elif base_value is None:
            raise ValidationError(
                f"ارزش این تبدیل به {CURRENCY_NAMES.get(book.base_currency, book.base_currency)} را وارد کن."
            )
        else:
            base = quantize(base_value)
            if base <= ZERO:
                raise ValidationError("ارزش تبدیل باید بیشتر از صفر باشد.")

        conversion = CurrencyConversion(
            book_id=book_id,
            actor_user_id=actor_user_id,
            occurred_on=occurred_on or jalali.today_in(book.timezone),
            from_currency=from_currency,
            from_amount=out_amount,
            to_currency=to_currency,
            to_amount=in_amount,
            base_value=base,
            base_currency=book.base_currency,
            note=(note.strip() or None) if note else None,
        )
        self.session.add(conversion)
        await self.session.flush()
        return conversion

    async def conversions(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID, limit: int = 20
    ) -> Sequence[CurrencyConversion]:
        await self.books.require(book_id, actor_user_id, Permission.VIEW_TRANSACTIONS)
        return (
            await self.session.execute(
                select(CurrencyConversion)
                .where(CurrencyConversion.book_id == book_id)
                .order_by(CurrencyConversion.occurred_on.desc(),
                          CurrencyConversion.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
