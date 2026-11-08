"""Holdings valued at today's price, and the running account of what was put into one thing."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from ...rates import quote as quoting
from ..exchange.catalog import BY_CODE as CURRENCIES
from .catalog import BY_CODE
from ..capital.models import Asset
from .models import FinancialNote, Holding, NoteEntry
from .pricing import Price, price_table, to_book_currency

ENTRY_KINDS = ("spent", "value", "note")


@dataclass
class HoldingView:
    id: uuid.UUID
    kind: str                       # "holding" (written down) or "asset" (bought and kept)
    instrument: str
    name: str
    unit: str
    group: str
    quantity: Decimal
    cost: Optional[Decimal]
    acquired_on: Optional[date]
    note: Optional[str]
    price: Optional[Decimal]        # one unit, in the book's currency
    value: Optional[Decimal]
    profit: Optional[Decimal]
    profit_percent: Optional[Decimal]
    source: str
    exact: bool
    as_of: Optional[datetime]
    loan_id: Optional[uuid.UUID] = None
    sold_on: Optional[date] = None
    sold_for: Optional[Decimal] = None


@dataclass
class PortfolioView:
    currency: str
    rows: List[HoldingView]
    total_value: Decimal
    total_cost: Decimal
    total_profit: Decimal
    unpriced: int


@dataclass
class NoteView:
    note: FinancialNote
    entries: List[NoteEntry]
    spent: Decimal
    value: Optional[Decimal]
    value_on: Optional[date]
    gain: Optional[Decimal]


def describe(code: str) -> Optional[tuple]:
    """(name, unit, group) of something that can be held: a catalog instrument or any currency the app knows."""
    item = BY_CODE.get(code)
    if item is not None:
        return item.name, item.unit, item.group
    coin = CURRENCIES.get(code)
    if coin is not None:
        return coin.name, coin.name, "crypto" if coin.kind == "crypto" else "currency"
    return None


def _positive(value, message: str) -> Decimal:
    amount = quantize(to_decimal(value))
    if amount <= ZERO:
        raise ValidationError(message)
    return amount


class PortfolioService:
    def __init__(self, session: AsyncSession, metals=None, rates=None, fiat=None) -> None:
        self.session = session
        self.books = BookService(session)
        self.metals, self.rates, self.fiat = metals, rates, fiat

    # ----------------------------------------------------------------- prices
    async def prices(self) -> Dict[str, Price]:
        if self.metals is None or self.rates is None or self.fiat is None:
            return {}
        return await price_table(self.metals, self.rates, self.fiat)

    # --------------------------------------------------------------- holdings
    async def view(self, book_id: uuid.UUID, user_id: uuid.UUID) -> PortfolioView:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        book = await self.books.get_book(book_id)
        table = await self.prices()
        factor: Optional[Decimal] = Decimal("1")
        if book.base_currency != "IRT" and self.rates is not None and self.fiat is not None:
            factor = to_book_currency(
                book.base_currency, await self.rates.prices(), await self.fiat.per_usd(),
                self.rates.fetched_at, self.fiat.fetched_at,
            )
        holdings = (
            await self.session.execute(
                select(Holding).where(Holding.book_id == book_id).order_by(Holding.created_at)
            )
        ).scalars().all()

        async def market_price(code: str):
            """(price in the book's currency, source, exact, as_of) for an instrument, or None."""
            found = table.get(code)
            if found is None and code in CURRENCIES and self.rates is not None and self.fiat is not None:
                # Any currency the app knows can be held, not only the few in the instrument list.
                asked = quoting.quote(
                    await self.rates.prices(), await self.fiat.per_usd(), code, "IRT",
                    self.rates.fetched_at, self.fiat.fetched_at,
                )
                if asked is not None:
                    found = Price(code, asked.value, asked.source, asked.exact, asked.fetched_at)
            if found is not None and found.value is not None and factor is not None:
                return quantize(found.value * factor), found.source, found.exact, found.as_of
            return None

        rows: List[HoldingView] = []
        total_value = total_cost = ZERO
        unpriced = 0

        def profit_of(value, cost):
            if value is None or cost is None:
                return None, None
            profit = quantize(value - cost)
            return profit, (quantize(profit * 100 / cost) if cost > ZERO else None)

        for holding in holdings:
            described = describe(holding.instrument)
            name = holding.label or (described[0] if described else holding.instrument)
            price: Optional[Decimal] = None
            source, exact, as_of = "", False, None
            if holding.unit_price is not None:
                price, source, exact = to_decimal(holding.unit_price), "manual", True
            else:
                priced = await market_price(holding.instrument)
                if priced is not None:
                    price, source, exact, as_of = priced
            value = quantize(to_decimal(holding.quantity) * price) if price is not None else None
            cost = to_decimal(holding.cost) if holding.cost is not None else None
            profit, percent = profit_of(value, cost)
            if value is None:
                unpriced += 1
            else:
                total_value += value
            if cost is not None:
                total_cost += cost
            rows.append(HoldingView(
                id=holding.id, kind="holding", instrument=holding.instrument, name=name,
                unit=described[1] if described else "", group=described[2] if described else "other",
                quantity=to_decimal(holding.quantity), cost=cost, acquired_on=holding.acquired_on,
                note=holding.note, price=price, value=value, profit=profit, profit_percent=percent,
                source=source, exact=exact, as_of=as_of,
            ))

        # What was bought and is kept (gold, a car, a house) is the same kind of thing: a priced one is
        # valued at today's price, any other at what it cost. A sold one is listed, and counts for nothing.
        assets = (
            await self.session.execute(
                select(Asset).where(Asset.book_id == book_id)
                .order_by(Asset.sold_on.is_not(None), Asset.acquired_on.desc(), Asset.created_at.desc())
            )
        ).scalars().all()
        for asset in assets:
            described = describe(asset.instrument) if asset.instrument else None
            cost = to_decimal(asset.cost)
            quantity = to_decimal(asset.quantity) if asset.quantity is not None else Decimal("1")
            price = value = None
            source, exact, as_of = "", False, None
            if asset.sold_on is None:
                if asset.instrument:
                    priced = await market_price(asset.instrument)
                    if priced is not None:
                        price, source, exact, as_of = priced
                        value = quantize(quantity * price)
                    else:
                        unpriced += 1
                else:
                    value, source, exact = cost, "cost", True
                total_cost += cost
                if value is not None:
                    total_value += value
                profit, percent = profit_of(value, cost) if asset.instrument else (None, None)
            else:
                profit, percent = (
                    profit_of(to_decimal(asset.sold_for), cost) if asset.sold_for is not None else (None, None)
                )
            rows.append(HoldingView(
                id=asset.id, kind="asset", instrument=asset.instrument or "", name=asset.name,
                unit=asset.unit or (described[1] if described else ""),
                group=described[2] if described else "other", quantity=quantity, cost=cost,
                acquired_on=asset.acquired_on, note=asset.note, price=price, value=value,
                profit=profit, profit_percent=percent, source=source, exact=exact, as_of=as_of,
                loan_id=asset.loan_id, sold_on=asset.sold_on, sold_for=asset.sold_for,
            ))
        # Profit is only over what has both a cost and a price: anything else would be a guess.
        total_profit = quantize(sum(
            (row.profit for row in rows if row.profit is not None and row.sold_on is None), ZERO
        ))
        return PortfolioView(
            currency=book.base_currency, rows=rows, total_value=quantize(total_value),
            total_cost=quantize(total_cost), total_profit=total_profit, unpriced=unpriced,
        )

    async def _holding(self, book_id: uuid.UUID, holding_id: uuid.UUID) -> Holding:
        row = await self.session.get(Holding, holding_id)
        if row is None or row.book_id != book_id:
            raise NotFound("این مورد پیدا نشد")
        return row

    @staticmethod
    def _checked(instrument: str, label: Optional[str], unit_price) -> tuple:
        item = BY_CODE.get(instrument)
        if item is None and instrument not in CURRENCIES:
            raise ValidationError("این نوع سرمایه شناخته نشد")
        name = (label or "").strip() or None
        price = quantize(to_decimal(unit_price)) if unit_price is not None else None
        if item is not None and item.source == "manual":
            if name is None:
                raise ValidationError("برای این مورد نام بنویس")
            if price is None or price <= ZERO:
                raise ValidationError("قیمت هر واحد را بنویس")
        else:
            price = None  # a priced instrument takes its price from the feed
        return name, price

    async def add_holding(
        self, book_id: uuid.UUID, user_id: uuid.UUID, instrument: str, quantity,
        cost=None, acquired_on: Optional[date] = None, label: Optional[str] = None,
        unit_price=None, note: Optional[str] = None,
    ) -> Holding:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        name, price = self._checked(instrument, label, unit_price)
        holding = Holding(
            book_id=book_id, instrument=instrument, label=name,
            quantity=_positive(quantity, "مقدار باید بیشتر از صفر باشد"),
            cost=quantize(to_decimal(cost)) if cost is not None else None,
            unit_price=price, acquired_on=acquired_on, note=(note or None),
        )
        self.session.add(holding)
        await self.session.flush()
        return holding

    async def update_holding(
        self, book_id: uuid.UUID, user_id: uuid.UUID, holding_id: uuid.UUID,
        quantity=None, cost=None, unit_price=None, label: Optional[str] = None,
        note: Optional[str] = None, acquired_on: Optional[date] = None,
    ) -> Holding:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        holding = await self._holding(book_id, holding_id)
        if quantity is not None:
            holding.quantity = _positive(quantity, "مقدار باید بیشتر از صفر باشد")
        if cost is not None:
            holding.cost = quantize(to_decimal(cost))
        kept = BY_CODE.get(holding.instrument)
        if unit_price is not None and kept is not None and kept.source == "manual":
            holding.unit_price = _positive(unit_price, "قیمت هر واحد را بنویس")
        if label is not None:
            holding.label = label.strip() or None
        if note is not None:
            holding.note = note or None
        if acquired_on is not None:
            holding.acquired_on = acquired_on
        await self.session.flush()
        return holding

    async def delete_holding(self, book_id: uuid.UUID, user_id: uuid.UUID, holding_id: uuid.UUID) -> None:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        await self.session.delete(await self._holding(book_id, holding_id))
        await self.session.flush()

    # ------------------------------------------------------------------ notes
    async def notes(self, book_id: uuid.UUID, user_id: uuid.UUID) -> List[NoteView]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        notes = (
            await self.session.execute(
                select(FinancialNote).where(FinancialNote.book_id == book_id)
                .order_by(FinancialNote.created_at.desc())
            )
        ).scalars().all()
        entries = (
            await self.session.execute(
                select(NoteEntry).where(NoteEntry.book_id == book_id)
                .order_by(NoteEntry.occurred_on, NoteEntry.created_at)
            )
        ).scalars().all()
        by_note: Dict[uuid.UUID, List[NoteEntry]] = {}
        for entry in entries:
            by_note.setdefault(entry.note_id, []).append(entry)
        return [self._note_view(note, by_note.get(note.id, [])) for note in notes]

    @staticmethod
    def _note_view(note: FinancialNote, entries: Sequence[NoteEntry]) -> NoteView:
        spent = quantize(sum((to_decimal(e.amount) for e in entries if e.kind == "spent" and e.amount is not None), ZERO))
        values = [e for e in entries if e.kind == "value" and e.amount is not None]
        latest = values[-1] if values else None  # entries are in date order
        value = quantize(to_decimal(latest.amount)) if latest is not None else None
        gain = quantize(value - spent) if value is not None and spent > ZERO else None
        return NoteView(note=note, entries=list(entries), spent=spent, value=value,
                        value_on=latest.occurred_on if latest is not None else None, gain=gain)

    async def _note(self, book_id: uuid.UUID, note_id: uuid.UUID) -> FinancialNote:
        row = await self.session.get(FinancialNote, note_id)
        if row is None or row.book_id != book_id:
            raise NotFound("این یادداشت پیدا نشد")
        return row

    async def add_note(
        self, book_id: uuid.UUID, user_id: uuid.UUID, title: str, text: Optional[str] = None
    ) -> FinancialNote:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        title = (title or "").strip()
        if not title:
            raise ValidationError("عنوان یادداشت لازم است")
        note = FinancialNote(book_id=book_id, title=title[:120], text=(text or None))
        self.session.add(note)
        await self.session.flush()
        return note

    async def update_note(
        self, book_id: uuid.UUID, user_id: uuid.UUID, note_id: uuid.UUID,
        title: Optional[str] = None, text: Optional[str] = None,
    ) -> FinancialNote:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        note = await self._note(book_id, note_id)
        if title is not None:
            title = title.strip()
            if not title:
                raise ValidationError("عنوان یادداشت لازم است")
            note.title = title[:120]
        if text is not None:
            note.text = text or None
        await self.session.flush()
        return note

    async def delete_note(self, book_id: uuid.UUID, user_id: uuid.UUID, note_id: uuid.UUID) -> None:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        await self.session.delete(await self._note(book_id, note_id))
        await self.session.flush()

    async def add_entry(
        self, book_id: uuid.UUID, user_id: uuid.UUID, note_id: uuid.UUID, kind: str,
        occurred_on: date, amount=None, memo: Optional[str] = None,
    ) -> NoteEntry:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        note = await self._note(book_id, note_id)
        if kind not in ENTRY_KINDS:
            raise ValidationError("نوع ردیف باید خرج، ارزش یا توضیح باشد")
        value = None
        if kind in ("spent", "value"):
            value = _positive(amount, "مبلغ باید بیشتر از صفر باشد")
        elif not (memo or "").strip():
            raise ValidationError("متن توضیح را بنویس")
        entry = NoteEntry(
            note_id=note.id, book_id=book_id, kind=kind, amount=value,
            occurred_on=occurred_on, memo=(memo or None),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def update_entry(
        self, book_id: uuid.UUID, user_id: uuid.UUID, note_id: uuid.UUID, entry_id: uuid.UUID,
        occurred_on: Optional[date] = None, amount=None, memo: Optional[str] = None,
    ) -> NoteEntry:
        """Correct a line already written: its day, its amount, its words."""
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        entry = await self.session.get(NoteEntry, entry_id)
        if entry is None or entry.book_id != book_id or entry.note_id != note_id:
            raise NotFound("این ردیف پیدا نشد")
        if occurred_on is not None:
            entry.occurred_on = occurred_on
        if amount is not None:
            if entry.kind == "note":
                raise ValidationError("این ردیف مبلغ ندارد")
            entry.amount = _positive(amount, "مبلغ باید بیشتر از صفر باشد")
        if memo is not None:
            if entry.kind == "note" and not memo.strip():
                raise ValidationError("متن توضیح را بنویس")
            entry.memo = memo or None
        await self.session.flush()
        return entry

    async def delete_entry(
        self, book_id: uuid.UUID, user_id: uuid.UUID, note_id: uuid.UUID, entry_id: uuid.UUID
    ) -> None:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        entry = await self.session.get(NoteEntry, entry_id)
        if entry is None or entry.book_id != book_id or entry.note_id != note_id:
            raise NotFound("این ردیف پیدا نشد")
        await self.session.delete(entry)
        await self.session.flush()
