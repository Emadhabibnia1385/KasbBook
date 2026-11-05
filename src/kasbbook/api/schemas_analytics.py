"""Response shapes for the analytics endpoints.

Kept beside `schemas.py` rather than in it so the panel's chart series can grow
without touching the file every other endpoint shares. The same rule holds:
money and percentages cross HTTP as strings (`MoneyModel`), and an absent
figure is `null` — never zero, because "no previous month" and "spent nothing"
are different statements.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from .schemas import MoneyModel


class CashflowPoint(MoneyModel):
    period: str
    label: str
    income: Decimal
    expense: Decimal
    net: Decimal
    # Null in a month with no income: a share of nothing is not zero percent.
    savings_rate_percent: Optional[Decimal] = None
    cumulative_net: Decimal
    transaction_count: int


class WeekdayPoint(MoneyModel):
    # 0 is Saturday and 6 is Friday: the Iranian week.
    index: int
    label: str
    income: Decimal
    expense: Decimal
    transaction_count: int


class ScopePoint(MoneyModel):
    scope: str
    income: Decimal
    expense: Decimal
    net: Decimal
    transaction_count: int


class Figures(MoneyModel):
    income: Decimal
    expense: Decimal
    net: Decimal
    transaction_count: int


class Delta(MoneyModel):
    absolute: Decimal
    # Null when the earlier figure was zero: growth from nothing has no percentage.
    percent: Optional[Decimal] = None


class CategoryDelta(MoneyModel):
    category: str
    current: Decimal
    previous: Decimal
    absolute: Decimal
    percent: Optional[Decimal] = None
    transaction_count: int


class TopCategory(CategoryDelta):
    share_percent: Decimal


class CompareResponse(MoneyModel):
    period: str
    label: str
    previous_period: str
    previous_label: str
    current: Figures
    previous: Figures
    income: Delta
    expense: Delta
    net: Delta
    expense_categories: List[CategoryDelta]
    income_categories: List[CategoryDelta]


class CumulativePoint(MoneyModel):
    # 1 is the first day of the period; both lines are aligned on it.
    day_index: int
    # Null once the period being viewed has ended (the other period was longer).
    on: Optional[date] = None
    # Null for days that have not happened yet.
    income: Optional[Decimal] = None
    expense: Optional[Decimal] = None
    net: Optional[Decimal] = None
    # Null past the end of the previous period.
    previous_net: Optional[Decimal] = None


class CumulativeResponse(MoneyModel):
    period: str
    label: str
    previous_period: str
    previous_label: str
    days: List[CumulativePoint]


class BiggestExpense(MoneyModel):
    category: str
    amount: Decimal
    on: date
    description: Optional[str] = None


class OverviewResponse(MoneyModel):
    period: str
    label: str
    currency: str
    base_balance: Decimal
    # Null when the book holds another currency and no price is known: one
    # unknown price makes the total a guess, so there is no total.
    total_balance: Optional[Decimal] = None
    holds_other_currencies: bool
    income: Decimal
    expense: Decimal
    net: Decimal
    savings_rate_percent: Optional[Decimal] = None
    average_daily_expense: Decimal
    days_counted: int
    biggest_expense: Optional[BiggestExpense] = None
    # Null when the balance is not positive or nothing is being spent.
    runway_days: Optional[int] = None


class BudgetActualItem(MoneyModel):
    label: str
    kind: str
    limit: Decimal
    spent: Decimal
    remaining: Decimal
    percent_used: int
    over: bool


class BudgetActualResponse(MoneyModel):
    period: str
    label: str
    # How much of the month has passed, so a gauge can show pace beside use.
    elapsed_percent: int
    items: List[BudgetActualItem]
