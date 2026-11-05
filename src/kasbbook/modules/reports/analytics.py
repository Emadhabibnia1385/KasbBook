"""The series behind the web panel's charts.

Everything here is a *reading* of what was already recorded: no rule is made
up in this module. Totals come from `Transaction.converted_amount`, the figure
stored at the rate in force when the entry was made, so a chart of last spring
does not move when today's rate does. A currency conversion is not a
transaction and never appears in any series here — it moves value between two
holdings and earns or spends nothing, and counting it would inflate both
income and expense by the same amount.

Every method starts with the same permission gate as the reports it sits
beside, so a stranger gets "not found" and not an empty chart.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import ValidationError
from ...shared.money import ZERO, quantize
from ..books.models import Permission
from ..books.service import BookService
from ..budgets.service import BudgetService, BudgetStatus
from ..exchange.service import ExchangeService
from ..ledger.models import Flow, Scope, Transaction
from .service import Period, ReportService, month, week, year

# The Iranian week starts on Saturday, which is also where `jalali.week_range`
# starts it, so a weekday chart and a "this week" report agree on day one.
WEEKDAYS = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")

# What the categories after the biggest few are called when they are folded
# together. The word is data the panel shows, like the weekday names above.
OTHER_LABEL = "سایر"

_HUNDRED = Decimal(100)
_PERCENT_SCALE = Decimal("0.01")


def weekday_index(value: date) -> int:
    """0 for Saturday through 6 for Friday."""
    return (value.weekday() + 2) % 7


def _percent(part: Decimal, whole: Decimal) -> Optional[Decimal]:
    """`part` as a percentage of `whole`; nothing when there is no whole.

    A share of nothing is not zero percent — it is not a number — and a chart
    that drew it as zero would call an empty month "all saved".
    """
    if whole == ZERO:
        return None
    return (part * _HUNDRED / whole).quantize(_PERCENT_SCALE, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Change:
    """How a figure moved. `percent` is empty when it started from nothing."""

    absolute: Decimal
    percent: Optional[Decimal]


def change(current: Decimal, previous: Decimal) -> Change:
    # Measured against the size of the old figure, not its sign: a loss that
    # shrank from -100 to -50 improved by 50%, and dividing by -100 would say -50.
    return Change(
        quantize(current - previous),
        _percent(current - previous, abs(previous)),
    )


def previous_period(period: Period, today: date) -> Period:
    """The period of the same kind immediately before this one."""
    parts = period.spec.split(":")
    if parts[0] == "m":
        y, m = int(parts[1]), int(parts[2])
        return month(y - 1, 12) if m == 1 else month(y, m - 1)
    if parts[0] == "y":
        return year(int(parts[1]) - 1)
    if parts[0] == "w":
        return week(today, int(parts[1]) + 1)
    raise ValidationError("this period has no earlier period to compare with")


def days_in(period: Period) -> int:
    return (period.ends_on - period.starts_on).days + 1


# --------------------------------------------------------------- results
@dataclass(frozen=True)
class CashflowRow:
    year: int
    month: int
    income: Decimal
    expense: Decimal
    count: int
    cumulative_net: Decimal

    @property
    def net(self) -> Decimal:
        return self.income - self.expense

    @property
    def savings_rate_percent(self) -> Optional[Decimal]:
        return _percent(self.net, self.income)


@dataclass(frozen=True)
class WeekdayRow:
    index: int
    name: str
    income: Decimal
    expense: Decimal
    count: int


@dataclass(frozen=True)
class ScopeRow:
    scope: Scope
    income: Decimal
    expense: Decimal
    count: int

    @property
    def net(self) -> Decimal:
        return self.income - self.expense


@dataclass(frozen=True)
class Figures:
    income: Decimal
    expense: Decimal
    count: int

    @property
    def net(self) -> Decimal:
        return self.income - self.expense


@dataclass(frozen=True)
class CategoryMove:
    category: str
    current: Decimal
    previous: Decimal
    count: int
    move: Change
    # Only filled by `top_categories`, where a share of the period's total means something.
    share_percent: Optional[Decimal] = None


@dataclass(frozen=True)
class CategorySegment:
    category: str
    amount: Decimal
    # The folded «سایر» bucket, as opposed to a real category that happens to
    # carry the same name: a client keys on this, not on the label.
    is_other: bool = False


@dataclass(frozen=True)
class CategoryMonth:
    year: int
    month: int
    # Every category of the legend, in legend order, zeros included, so a
    # column chart can read position i as the same category in every month.
    segments: List[CategorySegment]

    @property
    def total(self) -> Decimal:
        return quantize(sum((s.amount for s in self.segments), ZERO))


@dataclass(frozen=True)
class Comparison:
    period: Period
    previous: Period
    current: Figures
    before: Figures
    income: Change
    expense: Change
    net: Change
    expense_categories: List[CategoryMove]
    income_categories: List[CategoryMove]


@dataclass(frozen=True)
class CumulativePoint:
    day_index: int
    on: Optional[date]
    income: Optional[Decimal]
    expense: Optional[Decimal]
    net: Optional[Decimal]
    previous_net: Optional[Decimal]


@dataclass(frozen=True)
class BiggestExpense:
    category: str
    amount: Decimal
    on: date
    description: Optional[str]


@dataclass(frozen=True)
class Overview:
    period: Period
    currency: str
    base_balance: Decimal
    total_balance: Optional[Decimal]
    holds_other_currencies: bool
    income: Decimal
    expense: Decimal
    savings_rate_percent: Optional[Decimal]
    average_daily_expense: Decimal
    days_counted: int
    biggest_expense: Optional[BiggestExpense]
    runway_days: Optional[int]

    @property
    def net(self) -> Decimal:
        return self.income - self.expense


@dataclass(frozen=True)
class BudgetActual:
    period: Period
    elapsed_percent: int
    items: List[BudgetStatus] = field(default_factory=list)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)
        self.reports = ReportService(session)
        self.budgets = BudgetService(session)
        self.exchange = ExchangeService(session)

    async def _rows(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period: Period
    ) -> Sequence[Transaction]:
        # The reports service keeps its row reader to itself, and a series that
        # needs the rows (a weekday, a running total) has to read them. The
        # gate is the same one, first, so this opens nothing it did not.
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(Transaction)
                .where(
                    Transaction.book_id == book_id,
                    Transaction.occurred_on >= period.starts_on,
                    Transaction.occurred_on <= period.ends_on,
                )
                .order_by(Transaction.occurred_on, Transaction.created_at)
            )
        ).scalars().all()

    # -------------------------------------------------------------- cashflow
    async def cashflow(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        months: int = 12,
        today: Optional[date] = None,
    ) -> List[CashflowRow]:
        """Each of the last N months, with the running total of their net.

        The running total starts at zero on the first month shown, because it
        answers "how much did these months add up to", not "what is the balance"
        — the balance would need an opening figure nothing records.
        """
        running = ZERO
        out: List[CashflowRow] = []
        for y, m, summary in await self.reports.monthly(book_id, user_id, months, today):
            running += summary.net
            out.append(CashflowRow(y, m, summary.income, summary.expense, summary.count, quantize(running)))
        return out

    # --------------------------------------------------------------- weekday
    async def weekday(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period: Period
    ) -> List[WeekdayRow]:
        income = [ZERO] * 7
        expense = [ZERO] * 7
        counts = [0] * 7
        for tx in await self._rows(book_id, user_id, period):
            i = weekday_index(tx.occurred_on)
            if tx.flow is Flow.INCOME:
                income[i] += tx.converted_amount
            else:
                expense[i] += tx.converted_amount
            counts[i] += 1
        return [
            WeekdayRow(i, WEEKDAYS[i], quantize(income[i]), quantize(expense[i]), counts[i])
            for i in range(7)
        ]

    # ----------------------------------------------------------------- scope
    async def scope_split(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period: Period
    ) -> List[ScopeRow]:
        """Every scope, including those with nothing in them, in a fixed order."""
        totals: Dict[Scope, List] = {scope: [ZERO, ZERO, 0] for scope in Scope}
        for tx in await self._rows(book_id, user_id, period):
            bucket = totals[tx.scope]
            bucket[0 if tx.flow is Flow.INCOME else 1] += tx.converted_amount
            bucket[2] += 1
        return [
            ScopeRow(scope, quantize(i), quantize(e), n)
            for scope, (i, e, n) in totals.items()
        ]

    # ------------------------------------------------------------ categories
    async def _moves(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        period: Period,
        previous: Period,
        flow: Flow,
    ) -> List[CategoryMove]:
        now = {name: (total, n) for name, total, n in (await self.reports.by_category(book_id, user_id, period))[flow]}
        before = {name: total for name, total, _ in (await self.reports.by_category(book_id, user_id, previous))[flow]}
        moves: List[CategoryMove] = []
        for name in set(now) | set(before):
            # Quantized zeros, so a missing side serializes as "0.0000" like every other amount.
            total, count = now.get(name, (quantize(ZERO), 0))
            earlier = before.get(name, quantize(ZERO))
            moves.append(CategoryMove(name, total, earlier, count, change(total, earlier)))
        # Biggest first on whichever side was bigger: a category that vanished
        # this month is as much a story as one that appeared.
        moves.sort(key=lambda m: (max(m.current, m.previous), m.category), reverse=True)
        return moves

    async def top_categories(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        period: Period,
        flow: Flow,
        limit: int,
        today: date,
    ) -> List[CategoryMove]:
        """This period's biggest categories, each against the period before.

        The share is of the whole period's total in that direction, not of the
        `limit` rows returned, so it stays true when the list is cut short.
        """
        moves = await self._moves(
            book_id, user_id, period, previous_period(period, today), flow
        )
        moves = [m for m in moves if m.current > ZERO]
        moves.sort(key=lambda m: (m.current, m.category), reverse=True)
        total = sum((m.current for m in moves), ZERO)
        return [
            replace(m, share_percent=_percent(m.current, total) or ZERO)
            for m in moves[:limit]
        ]

    # ------------------------------------------------------ category by month
    async def category_monthly(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        months: int,
        flow: Flow,
        top: int,
        today: Optional[date] = None,
    ) -> List[CategoryMonth]:
        """Each of the last N months split by category, the biggest `top` kept apart.

        "Biggest" is judged over the whole window, not month by month: a
        category that is the top cost in one month and absent in the rest would
        otherwise change colour from column to column, and a stacked chart is
        only readable when one colour means one category throughout. Everything
        outside the top is folded into one «سایر» segment, present only when
        something was folded. Months with no activity are still listed.
        """
        wanted = jalali.recent_months(months, today)
        start = jalali.month_range(*wanted[0])[0]
        end = jalali.month_range(*wanted[-1])[1]
        # `Period` wants a spec and a label, which a window of loose months has none of.
        window = Period("", start, end, "")

        per_month: Dict[Tuple[int, int], Dict[str, Decimal]] = {key: {} for key in wanted}
        overall: Dict[str, Decimal] = {}
        for tx in await self._rows(book_id, user_id, window):
            if tx.flow is not flow:
                continue
            y, m, _ = jalali.to_parts(tx.occurred_on)
            bucket = per_month.get((y, m))
            if bucket is None:
                continue
            bucket[tx.category] = bucket.get(tx.category, ZERO) + tx.converted_amount
            overall[tx.category] = overall.get(tx.category, ZERO) + tx.converted_amount

        # Name breaks a tie so two equal categories keep the same order on every request.
        ranked = sorted(overall, key=lambda name: (-overall[name], name))
        kept = ranked[:top]
        folded = len(ranked) > top

        out: List[CategoryMonth] = []
        for (y, m), bucket in per_month.items():
            segments = [CategorySegment(name, quantize(bucket.get(name, ZERO))) for name in kept]
            if folded:
                rest = sum((v for name, v in bucket.items() if name not in kept), ZERO)
                segments.append(CategorySegment(OTHER_LABEL, quantize(rest), is_other=True))
            out.append(CategoryMonth(y, m, segments))
        return out

    # --------------------------------------------------------------- compare
    async def compare(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        period: Period,
        today: date,
        categories: int = 6,
    ) -> Comparison:
        previous = previous_period(period, today)
        now = await self.reports.summary(book_id, user_id, period)
        before = await self.reports.summary(book_id, user_id, previous)
        return Comparison(
            period=period,
            previous=previous,
            current=Figures(now.income, now.expense, now.count),
            before=Figures(before.income, before.expense, before.count),
            income=change(now.income, before.income),
            expense=change(now.expense, before.expense),
            net=change(now.net, before.net),
            expense_categories=(await self._moves(book_id, user_id, period, previous, Flow.EXPENSE))[:categories],
            income_categories=(await self._moves(book_id, user_id, period, previous, Flow.INCOME))[:categories],
        )

    # ------------------------------------------------------------ cumulative
    async def cumulative(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        period: Period,
        today: date,
    ) -> Tuple[Period, List[CumulativePoint]]:
        """Day by day inside one period, with the previous period's net beside it.

        The two lines are aligned by day index (day 5 against day 5), not by
        date, which is what makes "are we ahead of last month" readable. Days
        after today carry nothing rather than a flat line: the month has not
        happened yet, and a line that stayed level would read as "no more
        spending to come".
        """
        previous = previous_period(period, today)

        def per_day(rows: Sequence[Transaction]) -> Dict[date, Tuple[Decimal, Decimal]]:
            days: Dict[date, Tuple[Decimal, Decimal]] = {}
            for tx in rows:
                i, e = days.get(tx.occurred_on, (ZERO, ZERO))
                if tx.flow is Flow.INCOME:
                    i += tx.converted_amount
                else:
                    e += tx.converted_amount
                days[tx.occurred_on] = (i, e)
            return days

        now_days = per_day(await self._rows(book_id, user_id, period))
        before_days = per_day(await self._rows(book_id, user_id, previous))

        length = max(days_in(period), days_in(previous))
        income = expense = before = ZERO
        points: List[CumulativePoint] = []
        for index in range(length):
            on = period.starts_on + timedelta(days=index)
            inside = index < days_in(period)
            visible = inside and on <= today

            if visible:
                i, e = now_days.get(on, (ZERO, ZERO))
                income += i
                expense += e

            before_on = previous.starts_on + timedelta(days=index)
            has_before = index < days_in(previous)
            if has_before:
                i, e = before_days.get(before_on, (ZERO, ZERO))
                before += i - e

            points.append(
                CumulativePoint(
                    day_index=index + 1,
                    on=on if inside else None,
                    income=quantize(income) if visible else None,
                    expense=quantize(expense) if visible else None,
                    net=quantize(income - expense) if visible else None,
                    previous_net=quantize(before) if has_before else None,
                )
            )
        return previous, points

    # -------------------------------------------------------------- overview
    async def overview(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        period: Period,
        today: date,
    ) -> Overview:
        book = await self.books.get_book(book_id)
        rows = await self._rows(book_id, user_id, period)

        income = expense = ZERO
        biggest: Optional[Transaction] = None
        for tx in rows:
            if tx.flow is Flow.INCOME:
                income += tx.converted_amount
            else:
                expense += tx.converted_amount
                if biggest is None or tx.converted_amount > biggest.converted_amount:
                    biggest = tx
        income, expense = quantize(income), quantize(expense)

        # Spending is averaged over the days that have happened, not the whole
        # month: on the fifth, thirty days of denominator would call a normal
        # pace a fifth of what it is.
        last_day = min(period.ends_on, today)
        counted = max(1, (last_day - period.starts_on).days + 1)
        average = quantize(expense / counted)

        balances, total = await self.exchange.valuation(user_id, book_id)
        base_balance = next((b.amount for b in balances if b.is_base), ZERO)
        others = any(b.amount != ZERO for b in balances if not b.is_base)

        # How long the base-currency balance lasts at this pace. Nothing when
        # the balance is not positive or nothing is being spent: "infinite" and
        # "already negative" are both not a number of days.
        runway = (
            int(base_balance / average) if base_balance > ZERO and average > ZERO else None
        )

        return Overview(
            period=period,
            currency=book.base_currency,
            base_balance=base_balance,
            total_balance=total,
            holds_other_currencies=others,
            income=income,
            expense=expense,
            savings_rate_percent=_percent(income - expense, income),
            average_daily_expense=average,
            days_counted=counted,
            biggest_expense=(
                BiggestExpense(biggest.category, quantize(biggest.converted_amount), biggest.occurred_on, biggest.description)
                if biggest is not None
                else None
            ),
            runway_days=runway,
        )

    # --------------------------------------------------------------- budgets
    async def budget_vs_actual(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        period: Period,
        today: date,
    ) -> BudgetActual:
        """Budgets are monthly, so only a month can be asked about."""
        parts = period.spec.split(":")
        if parts[0] != "m":
            raise ValidationError("budgets are monthly; ask for a month such as 1405-08")

        items = await self.budgets.status(book_id, user_id, int(parts[1]), int(parts[2]), today)

        total = days_in(period)
        if today < period.starts_on:
            elapsed = 0
        elif today > period.ends_on:
            elapsed = 100
        else:
            elapsed = round(((today - period.starts_on).days + 1) * 100 / total)
        return BudgetActual(period, elapsed, list(items))
