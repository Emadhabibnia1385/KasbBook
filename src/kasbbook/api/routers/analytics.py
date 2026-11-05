"""Chart series for the web panel.

Periods are written the way the reports endpoints take them: `1405-08` for a
month, `1405` for a year, `week` for the current week. The service converts to
Gregorian ranges; nothing here sees a Jalali date except as text going out.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Query

from ...modules.ledger.models import Flow
from ...modules.reports import analytics as analytics_service
from ...modules.reports.service import Period, month, parse_spec
from ...shared import jalali
from ...shared.errors import ValidationError
from ..deps import CurrentUser, SessionDep
from ..schemas_analytics import (
    BiggestExpense,
    BudgetActualItem,
    BudgetActualResponse,
    CashflowPoint,
    CategoryDelta,
    CategoryMonthlyResponse,
    CategoryMonthPoint,
    CategorySegment,
    CompareResponse,
    CumulativePoint,
    CumulativeResponse,
    Delta,
    Figures,
    OverviewResponse,
    ScopePoint,
    TopCategory,
    WeekdayPoint,
)
from .reports import _as_spec

router = APIRouter(prefix="/books/{book_id}/analytics", tags=["analytics"])


def _today(user) -> date:
    # The person's own day, not the server's: the first hours of an Iranian
    # morning are still yesterday on a UTC server.
    return jalali.today_in(user.timezone)


def _period(spec: Optional[str], today: date) -> Period:
    """The period asked for, or the current month when none was."""
    if not spec:
        y, m, _ = jalali.to_parts(today)
        return month(y, m)
    period = parse_spec(_as_spec(spec.strip()), today)
    if period is None:
        raise ValidationError(
            "period should look like 1405-08 for a month, 1405 for a year, "
            "or 'week' for the current week"
        )
    return period


def _spec_text(period: Period) -> str:
    """The same period in the documented form, so a client can send it back."""
    parts = period.spec.split(":")
    if parts[0] == "m":
        return f"{parts[1]}-{parts[2]}"
    if parts[0] == "y":
        return parts[1]
    return "week" if period.spec == "w:0" else period.spec


def _flow(text: str) -> Flow:
    try:
        return Flow(text.lower())
    except ValueError:
        raise ValidationError("flow must be income or expense") from None


def _delta(move) -> Delta:
    return Delta(absolute=move.absolute, percent=move.percent)


def _figures(f) -> Figures:
    return Figures(income=f.income, expense=f.expense, net=f.net, transaction_count=f.count)


def _category_delta(m) -> CategoryDelta:
    return CategoryDelta(
        category=m.category, current=m.current, previous=m.previous,
        absolute=m.move.absolute, percent=m.move.percent, transaction_count=m.count,
    )


@router.get("/cashflow", response_model=List[CashflowPoint])
async def cashflow(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    months: int = Query(default=12, ge=1, le=24),
) -> List[CashflowPoint]:
    """Income, expense, net, savings rate and a running net for each of the last N months."""
    rows = await analytics_service.AnalyticsService(session).cashflow(
        book_id, user.id, months, _today(user)
    )
    return [
        CashflowPoint(
            period=f"{r.year}-{r.month:02d}", label=jalali.month_name(r.month),
            income=r.income, expense=r.expense, net=r.net,
            savings_rate_percent=r.savings_rate_percent,
            cumulative_net=r.cumulative_net, transaction_count=r.count,
        )
        for r in rows
    ]


@router.get("/weekday", response_model=List[WeekdayPoint])
async def weekday(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = Query(default=None, description="1405-08, 1405, or week; default this month"),
) -> List[WeekdayPoint]:
    """Income and expense by day of the week, Saturday first."""
    resolved = _period(period, _today(user))
    rows = await analytics_service.AnalyticsService(session).weekday(book_id, user.id, resolved)
    return [
        WeekdayPoint(
            index=r.index, label=r.name, income=r.income, expense=r.expense,
            transaction_count=r.count,
        )
        for r in rows
    ]


@router.get("/scope-split", response_model=List[ScopePoint])
async def scope_split(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = Query(default=None, description="1405-08, 1405, or week; default this month"),
) -> List[ScopePoint]:
    """Totals per scope (work, personal, team); all three are always listed."""
    resolved = _period(period, _today(user))
    rows = await analytics_service.AnalyticsService(session).scope_split(book_id, user.id, resolved)
    return [
        ScopePoint(
            scope=r.scope.value, income=r.income, expense=r.expense, net=r.net,
            transaction_count=r.count,
        )
        for r in rows
    ]


@router.get("/compare", response_model=CompareResponse)
async def compare(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = Query(default=None, description="1405-08, 1405, or week; default this month"),
) -> CompareResponse:
    """This period against the one before it, overall and for the biggest categories."""
    today = _today(user)
    resolved = _period(period, today)
    result = await analytics_service.AnalyticsService(session).compare(
        book_id, user.id, resolved, today
    )
    return CompareResponse(
        period=_spec_text(result.period), label=result.period.label,
        previous_period=_spec_text(result.previous), previous_label=result.previous.label,
        current=_figures(result.current), previous=_figures(result.before),
        income=_delta(result.income), expense=_delta(result.expense), net=_delta(result.net),
        expense_categories=[_category_delta(m) for m in result.expense_categories],
        income_categories=[_category_delta(m) for m in result.income_categories],
    )


@router.get("/top-categories", response_model=List[TopCategory])
async def top_categories(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = Query(default=None, description="1405-08, 1405, or week; default this month"),
    flow: str = Query(default="expense"),
    limit: int = Query(default=8, ge=1, le=50),
) -> List[TopCategory]:
    """The biggest categories this period, each with its change since the last."""
    today = _today(user)
    moves = await analytics_service.AnalyticsService(session).top_categories(
        book_id, user.id, _period(period, today), _flow(flow), limit, today
    )
    return [
        TopCategory(**_category_delta(m).model_dump(), share_percent=m.share_percent)
        for m in moves
    ]


@router.get("/category-monthly", response_model=CategoryMonthlyResponse)
async def category_monthly(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    months: int = Query(default=6, ge=1, le=24),
    flow: str = Query(default="expense", description="expense or income"),
    top: int = Query(default=6, ge=1, le=12, description="categories kept apart; the rest are folded into «سایر»"),
) -> CategoryMonthlyResponse:
    """The last N months, each split by category: the biggest few and «سایر» for the rest."""
    direction = _flow(flow)
    rows = await analytics_service.AnalyticsService(session).category_monthly(
        book_id, user.id, months, direction, top, _today(user)
    )
    return CategoryMonthlyResponse(
        flow=direction.value,
        months=[
            CategoryMonthPoint(
                period=f"{r.year}-{r.month:02d}", label=jalali.month_name(r.month), total=r.total,
                segments=[
                    CategorySegment(category=s.category, amount=s.amount, is_other=s.is_other)
                    for s in r.segments
                ],
            )
            for r in rows
        ],
    )


@router.get("/cumulative", response_model=CumulativeResponse)
async def cumulative(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = Query(default=None, description="1405-08, 1405, or week; default this month"),
) -> CumulativeResponse:
    """Running income, expense and net by day, with last period's net aligned by day number."""
    today = _today(user)
    resolved = _period(period, today)
    previous, points = await analytics_service.AnalyticsService(session).cumulative(
        book_id, user.id, resolved, today
    )
    return CumulativeResponse(
        period=_spec_text(resolved), label=resolved.label,
        previous_period=_spec_text(previous), previous_label=previous.label,
        days=[
            CumulativePoint(
                day_index=p.day_index, on=p.on, income=p.income, expense=p.expense,
                net=p.net, previous_net=p.previous_net,
            )
            for p in points
        ],
    )


@router.get("/overview-kpis", response_model=OverviewResponse)
async def overview_kpis(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = Query(default=None, description="1405-08, 1405, or week; default this month"),
) -> OverviewResponse:
    """Balance, savings rate, average daily spending, biggest expense and runway."""
    today = _today(user)
    resolved = _period(period, today)
    result = await analytics_service.AnalyticsService(session).overview(
        book_id, user.id, resolved, today
    )
    big = result.biggest_expense
    return OverviewResponse(
        period=_spec_text(resolved), label=resolved.label, currency=result.currency,
        base_balance=result.base_balance, total_balance=result.total_balance,
        holds_other_currencies=result.holds_other_currencies,
        income=result.income, expense=result.expense, net=result.net,
        savings_rate_percent=result.savings_rate_percent,
        average_daily_expense=result.average_daily_expense, days_counted=result.days_counted,
        biggest_expense=(
            BiggestExpense(category=big.category, amount=big.amount, on=big.on, description=big.description)
            if big is not None else None
        ),
        runway_days=result.runway_days,
    )


@router.get("/budget-vs-actual", response_model=BudgetActualResponse)
async def budget_vs_actual(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    period: Optional[str] = Query(default=None, description="a month such as 1405-08; default this month"),
) -> BudgetActualResponse:
    """Each budget's ceiling against what the month has spent, and how much of the month is gone."""
    today = _today(user)
    resolved = _period(period, today)
    result = await analytics_service.AnalyticsService(session).budget_vs_actual(
        book_id, user.id, resolved, today
    )
    return BudgetActualResponse(
        period=_spec_text(resolved), label=resolved.label, elapsed_percent=result.elapsed_percent,
        items=[
            BudgetActualItem(
                label=s.label, kind=s.budget.kind.value, limit=s.limit, spent=s.spent,
                remaining=s.remaining, percent_used=s.percent, over=s.over,
            )
            for s in result.items
        ],
    )
