"""Jalali periods, expressed as Gregorian ranges.

Transactions store a Gregorian date because that is what sorts and compares
correctly everywhere. Reports are Jalali because that is the year the people
using this actually live in. Every period below is converted to a Gregorian
[start, end] pair before it reaches a query, so the two never disagree.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional, Tuple

import jdatetime

MONTHS = (
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند",
)


def month_name(month: int) -> str:
    return MONTHS[month - 1] if 1 <= month <= 12 else str(month)


def to_parts(value: date) -> Tuple[int, int, int]:
    jalali = jdatetime.date.fromgregorian(date=value)
    return jalali.year, jalali.month, jalali.day


def to_text(value: date) -> str:
    year, month, day = to_parts(value)
    return f"{year:04d}/{month:02d}/{day:02d}"


def from_parts(year: int, month: int, day: int) -> date:
    return jdatetime.date(year, month, day).togregorian()


def month_range(year: int, month: int) -> Tuple[date, date]:
    """Inclusive [start, end] of one Jalali month."""
    start = from_parts(year, month, 1)
    next_start = (
        from_parts(year + 1, 1, 1) if month == 12 else from_parts(year, month + 1, 1)
    )
    return start, next_start - timedelta(days=1)


def year_range(year: int) -> Tuple[date, date]:
    return from_parts(year, 1, 1), from_parts(year + 1, 1, 1) - timedelta(days=1)


def week_range(today: Optional[date] = None, offset: int = 0) -> Tuple[date, date]:
    """The Iranian week runs Saturday to Friday."""
    day = today or date.today()
    since_saturday = (day.weekday() + 2) % 7
    start = day - timedelta(days=since_saturday + 7 * offset)
    return start, start + timedelta(days=6)


def add_months(value: date, months: int) -> date:
    """Shift by whole Jalali months, clamping onto a shorter month."""
    year, month, day = to_parts(value)
    total = (year * 12 + (month - 1)) + months
    new_year, new_month = divmod(total, 12)
    new_month += 1

    while day > 1:
        try:
            return from_parts(new_year, new_month, day)
        except (ValueError, TypeError):
            day -= 1
    return from_parts(new_year, new_month, 1)


def recent_months(count: int, today: Optional[date] = None) -> List[Tuple[int, int]]:
    """The last `count` Jalali (year, month) pairs, oldest first."""
    year, month, _ = to_parts(today or date.today())
    out: List[Tuple[int, int]] = []

    for back in range(count - 1, -1, -1):
        total = (year * 12 + (month - 1)) - back
        y, m = divmod(total, 12)
        out.append((y, m + 1))
    return out
