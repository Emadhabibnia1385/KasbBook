"""Reading the books back out.

Periods are Jalali. `1403-05` is Mordad of 1403, not May; the service converts
to a Gregorian range before any query runs, because the database stores dates
and the user thinks in months.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Query, Response

from ...modules.ledger.models import Flow
from ...modules.reports import service as reports
from ...shared.errors import ValidationError
from ...shared.money import ZERO, quantize
from ..deps import CurrentUser, SessionDep
from ..schemas import CategoryLine, SummaryResponse

router = APIRouter(prefix="/books/{book_id}/reports", tags=["reports"])


def _period(spec: Optional[str]):
    if not spec:
        return None
    period = reports.parse_spec(spec)
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
        book_id, user.id, _period(period)
    )
    return SummaryResponse(
        income=totals.income, expense=totals.expense, net=totals.net,
        transaction_count=totals.count,
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
        book_id, user.id, _period(period)
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


@router.get("/export.csv")
async def export_csv(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = None,
) -> Response:
    """The whole period as a file, for anyone who would rather use a spreadsheet."""
    content = await reports.ReportService(session).to_csv(book_id, user.id, _period(period))
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kasbbook.csv"'},
    )
