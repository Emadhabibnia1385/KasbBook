"""Reports over a book, on the Jalali calendar.

Every figure here is read from what was recorded, using the rate that was in
force at the time. A report of last spring does not move when today's rate does
— that is the whole reason the rate is stored on the transaction.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.money import ZERO, quantize
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import Flow, Transaction


@dataclass(frozen=True)
class Period:
    """A named stretch of time, already resolved to Gregorian bounds."""

    label: str
    starts_on: date
    ends_on: date
    spec: str  # what a button carries to reopen this exact period


def month(year: int, number: int) -> Period:
    start, end = jalali.month_range(year, number)
    return Period(f"{jalali.month_name(number)} {year}", start, end, f"m:{year}:{number:02d}")


def year(number: int) -> Period:
    start, end = jalali.year_range(number)
    return Period(f"سال {number}", start, end, f"y:{number}")


def week(today: Optional[date] = None, offset: int = 0) -> Period:
    start, end = jalali.week_range(today, offset)
    label = "این هفته" if offset == 0 else "هفتهٔ گذشته"
    return Period(label, start, end, f"w:{offset}")


def parse_spec(spec: str, today: Optional[date] = None) -> Optional[Period]:
    """Turn a button's payload back into the period it names."""
    parts = (spec or "").split(":")
    kind = parts[0] if parts else ""

    try:
        if kind == "m" and len(parts) >= 3:
            return month(int(parts[1]), int(parts[2]))
        if kind == "y" and len(parts) >= 2:
            return year(int(parts[1]))
        if kind == "w":
            return week(today, int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, TypeError):
        return None
    return None


@dataclass
class Summary:
    income: Decimal = ZERO
    expense: Decimal = ZERO

    @property
    def net(self) -> Decimal:
        return self.income - self.expense


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    async def _rows(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period: Optional[Period]
    ) -> Sequence[Transaction]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)

        stmt = select(Transaction).where(Transaction.book_id == book_id)
        if period is not None:
            stmt = stmt.where(
                Transaction.occurred_on >= period.starts_on,
                Transaction.occurred_on <= period.ends_on,
            )
        stmt = stmt.order_by(Transaction.occurred_on, Transaction.created_at)
        return (await self.session.execute(stmt)).scalars().all()

    async def summary(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period: Optional[Period] = None
    ) -> Summary:
        result = Summary()
        for tx in await self._rows(book_id, user_id, period):
            if tx.flow is Flow.INCOME:
                result.income += tx.converted_amount
            else:
                result.expense += tx.converted_amount

        return Summary(quantize(result.income), quantize(result.expense))

    async def by_category(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period: Optional[Period] = None
    ) -> dict:
        """Per-category totals, biggest first, split by direction."""
        buckets: dict = {Flow.INCOME: {}, Flow.EXPENSE: {}}
        counts: dict = {Flow.INCOME: {}, Flow.EXPENSE: {}}

        for tx in await self._rows(book_id, user_id, period):
            buckets[tx.flow][tx.category] = (
                buckets[tx.flow].get(tx.category, ZERO) + tx.converted_amount
            )
            counts[tx.flow][tx.category] = counts[tx.flow].get(tx.category, 0) + 1

        return {
            flow: sorted(
                (
                    (name, quantize(total), counts[flow][name])
                    for name, total in totals.items()
                ),
                key=lambda row: row[1],
                reverse=True,
            )
            for flow, totals in buckets.items()
        }

    async def years_with_data(
        self, book_id: uuid.UUID, user_id: uuid.UUID
    ) -> List[int]:
        """Jalali years that actually contain something, newest first."""
        rows = await self._rows(book_id, user_id, None)
        if not rows:
            return []

        years = {jalali.to_parts(tx.occurred_on)[0] for tx in rows}
        return sorted(years, reverse=True)

    async def trend(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        months: int = 6,
        today: Optional[date] = None,
    ) -> List[Tuple[str, Decimal]]:
        """Net figure per Jalali month, oldest first."""
        out: List[Tuple[str, Decimal]] = []
        for y, m in jalali.recent_months(months, today):
            summary = await self.summary(book_id, user_id, month(y, m))
            out.append((f"{jalali.month_name(m)} {y}", summary.net))
        return out

    async def compare(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period: Period
    ) -> Optional[Tuple[Period, Summary, Summary]]:
        """This period against the one before it, when there is one."""
        previous = self._previous(period)
        if previous is None:
            return None

        before = await self.summary(book_id, user_id, previous)
        if before.income == ZERO and before.expense == ZERO:
            return None

        return previous, before, await self.summary(book_id, user_id, period)

    def _previous(self, period: Period) -> Optional[Period]:
        parts = period.spec.split(":")
        if parts[0] == "m":
            y, m = int(parts[1]), int(parts[2])
            return month(y - 1, 12) if m == 1 else month(y, m - 1)
        if parts[0] == "y":
            return year(int(parts[1]) - 1)
        if parts[0] == "w":
            return week(offset=int(parts[1]) + 1)
        return None

    async def search(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        page: int = 0,
        per_page: int = 10,
    ) -> Tuple[Sequence[Transaction], int, Decimal]:
        """Matching rows for one page, the total count, and the total amount.

        The amount is over *every* match, not just the page: "how much did I
        spend on rent this year" is the question people are really asking.
        """
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)

        needle = (query or "").strip()
        if len(needle) < 2:
            return [], 0, ZERO

        pattern = f"%{needle}%"
        condition = (Transaction.book_id == book_id) & (
            Transaction.category.ilike(pattern)
            | func.coalesce(Transaction.description, "").ilike(pattern)
        )

        matches = (
            await self.session.execute(
                select(Transaction).where(condition).order_by(
                    Transaction.occurred_on.desc(), Transaction.created_at.desc()
                )
            )
        ).scalars().all()

        total_amount = quantize(sum((tx.converted_amount for tx in matches), ZERO))
        start = max(0, page) * per_page
        return matches[start:start + per_page], len(matches), total_amount

    async def to_csv(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period: Optional[Period] = None
    ) -> bytes:
        await self.books.require(book_id, user_id, Permission.EXPORT)
        rows = await self._rows(book_id, user_id, period)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["شناسه", "تاریخ شمسی", "تاریخ میلادی", "نوع", "دسته",
             "مبلغ", "ارز اصلی", "مبلغ اصلی", "نرخ", "توضیح"]
        )
        for tx in rows:
            writer.writerow([
                str(tx.id)[:8],
                jalali.to_text(tx.occurred_on),
                tx.occurred_on.isoformat(),
                "درآمد" if tx.flow is Flow.INCOME else "هزینه",
                tx.category,
                f"{tx.converted_amount:f}",
                tx.original_currency,
                f"{tx.original_amount:f}",
                f"{tx.conversion_rate:f}",
                tx.description or "",
            ])

        # A BOM so Excel opens it as UTF-8 and the Persian is readable.
        return ("﻿" + buffer.getvalue()).encode("utf-8")
