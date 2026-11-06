"""Reading the books back out.

Periods are Jalali. `1403-05` is Mordad of 1403, not May; the service converts
to a Gregorian range before any query runs, because the database stores dates
and the user thinks in months.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, Query, Response

from ...modules.ledger.models import Flow
from ...modules.reports import service as reports
from ...shared import jalali
from ...shared.errors import ValidationError
from ...shared.money import ZERO, quantize
from ..deps import CurrentUser, SessionDep
from ...modules.ledger.service import LedgerService
from ..schemas import (
    CategoryLine,
    DailyPoint,
    DayResponse,
    MonthlyPoint,
    SummaryResponse,
    TransactionSearchPage,
)
from .books import _transaction

router = APIRouter(prefix="/books/{book_id}/reports", tags=["reports"])


def _as_spec(text: str) -> str:
    """The documented forms (`1403-05`, `1403`, `week`) in the service's own.

    The service speaks the bot's button payloads (`m:1403:05`), which are what
    this route used to require while the docs promised the friendlier forms, so
    the documented call answered 422. Payloads still pass through unchanged.
    """
    if text == "week":
        return "w:0"
    year, dash, month = text.partition("-")
    if year.isdigit() and len(year) == 4:
        if not dash:
            return f"y:{year}"
        if month.isdigit():
            return f"m:{year}:{int(month):02d}"
    return text


async def _period(session, book_id, spec: Optional[str]):
    """The period asked for, with its months counted by the book's own calendar."""
    if not spec:
        return None
    cal = await reports.ReportService(session).calendar_of(book_id)
    period = reports.parse_spec(_as_spec(spec.strip()), None, cal)
    if period is None:
        raise ValidationError(
            "period should look like 1403-05 for a month, 1403 for a year, "
            "or 'week' for the current week"
        )
    return period


@router.get("/summary", response_model=SummaryResponse)
async def summary(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = Query(default=None, description="1403-05, 1403, or week"),
) -> SummaryResponse:
    totals = await reports.ReportService(session).summary(
        book_id, user.id, await _period(session, book_id, period)
    )
    return SummaryResponse(
        income=totals.income, expense=totals.expense, net=totals.net,
        transaction_count=totals.count,
    )


@router.get("/search", response_model=TransactionSearchPage)
async def search(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    q: str = Query(default="", max_length=100, description="two characters at least"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> TransactionSearchPage:
    """The bot's search, as a page. A query under two characters matches nothing."""
    rows, total, total_amount = await reports.ReportService(session).search(
        book_id, user.id, q, page=page - 1, per_page=per_page
    )
    activities = await LedgerService(session).activities(user.id, rows)
    return TransactionSearchPage(
        items=[_transaction(row, activities[row.id]) for row in rows],
        # An empty search returns the bare ZERO, so the wire shape is fixed here.
        total=total, total_amount=quantize(total_amount), page=page, per_page=per_page,
    )


@router.get("/day", response_model=DayResponse)
async def day(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    on: str = Query(alias="date", description="a Gregorian date, 2026-03-19"),
) -> DayResponse:
    """The bot's daily list, as numbers. Same service, so the two cannot disagree."""
    try:
        day_on = date_type.fromisoformat(on)
    except ValueError:
        raise ValidationError("date must look like 2026-03-19") from None

    (sheet,) = await reports.ReportService(session).day(user.id, day_on, book_id)
    totals = sheet.totals
    return DayResponse(
        on=day_on,
        business_income=totals.business_income,
        business_expense=totals.business_expense,
        business_net=totals.business_net,
        personal_income=totals.personal_income,
        personal_expense=totals.personal_expense,
        installment=totals.installment,
        savings_operational=totals.savings_operational,
        savings_final=totals.savings_final,
        transaction_count=len(sheet.rows),
    )


@router.get("/by-category", response_model=List[CategoryLine])
async def by_category(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    flow: str = Query(default="expense"),
    period: Optional[str] = None,
) -> List[CategoryLine]:
    try:
        direction = Flow(flow.lower())
    except ValueError:
        raise ValidationError("flow must be income or expense") from None

    buckets = await reports.ReportService(session).by_category(
        book_id, user.id, await _period(session, book_id, period)
    )
    lines = buckets.get(direction, [])
    total = sum((amount for _, amount, _ in lines), ZERO)

    return [
        CategoryLine(
            category=name,
            total=amount,
            # A share of nothing is nothing, not a division by zero.
            share_percent=quantize(amount * 100 / total) if total else ZERO,
        )
        for name, amount, _ in lines
    ]


@router.get("/monthly", response_model=List[MonthlyPoint])
async def monthly(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    months: int = Query(default=6, ge=1, le=24),
) -> List[MonthlyPoint]:
    """Income and expense for each of the last N months of the book's calendar, oldest first."""
    service = reports.ReportService(session)
    cal = await service.calendar_of(book_id)
    rows = await service.monthly(book_id, user.id, months)
    return [
        MonthlyPoint(
            period=f"{y}-{m:02d}", label=cal.month_name(m), income=t.income,
            expense=t.expense, net=t.net, transaction_count=t.count,
        )
        for y, m, t in rows
    ]


@router.get("/daily", response_model=List[DailyPoint])
async def daily(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: str = Query(description="1403-05, 1403, or week"),
) -> List[DailyPoint]:
    """Per-day income and expense inside one period, for a chart."""
    rows = await reports.ReportService(session).daily(book_id, user.id, await _period(session, book_id, period))
    return [DailyPoint(on=d, income=i, expense=e) for d, i, e in rows]


@router.get("/export.csv")
async def export_csv(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = None,
) -> Response:
    """The whole period as a file, for anyone who would rather use a spreadsheet."""
    content = await reports.ReportService(session).to_csv(book_id, user.id, await _period(session, book_id, period))
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kasbbook.csv"'},
    )
