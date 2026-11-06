"""The two calendars a book can keep its months and years by.

Every date is stored as a Gregorian `date`, because that is what sorts and
compares correctly. What a book's *calendar* decides is where its months, years
and weeks begin and end, what they are called and how its dates are written: a
Jalali month closes on the 29th, 30th or 31st by its own count, a Gregorian one
by the usual 28 to 31.

The Jalali functions are the existing ones in `jalali`; this module only puts a
second set beside them behind one shape, so a report asks the book's calendar
rather than assuming one.
"""

from __future__ import annotations

import calendar as _calendar
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from . import jalali

GREGORIAN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

CALENDAR_NAMES = ("jalali", "gregorian")


class Calendar:
    name = ""

    def month_name(self, month: int) -> str:
        raise NotImplementedError

    def to_parts(self, value: date) -> Tuple[int, int, int]:
        raise NotImplementedError

    def from_parts(self, year: int, month: int, day: int) -> date:
        raise NotImplementedError

    def week_range(self, today: Optional[date] = None, offset: int = 0) -> Tuple[date, date]:
        raise NotImplementedError

    # The days of the week in the order this calendar's week lists them, and where a day falls in it.
    weekday_names: Tuple[str, ...] = ()

    def weekday_index(self, value: date) -> int:
        raise NotImplementedError

    # ----------------------------------------------------- derived, shared
    def to_text(self, value: date) -> str:
        year, month, day = self.to_parts(value)
        return f"{year:04d}/{month:02d}/{day:02d}"

    def month_range(self, year: int, month: int) -> Tuple[date, date]:
        """Inclusive [start, end] of one month."""
        start = self.from_parts(year, month, 1)
        following = (
            self.from_parts(year + 1, 1, 1) if month == 12 else self.from_parts(year, month + 1, 1)
        )
        return start, following - timedelta(days=1)

    def year_range(self, year: int) -> Tuple[date, date]:
        return self.from_parts(year, 1, 1), self.from_parts(year + 1, 1, 1) - timedelta(days=1)

    def add_months(self, value: date, months: int) -> date:
        """Shift by whole months, clamping onto a shorter one."""
        year, month, day = self.to_parts(value)
        total = (year * 12 + (month - 1)) + months
        new_year, new_month = divmod(total, 12)
        new_month += 1
        while day > 1:
            try:
                return self.from_parts(new_year, new_month, day)
            except (ValueError, TypeError):
                day -= 1
        return self.from_parts(new_year, new_month, 1)

    def recent_months(self, count: int, today: Optional[date] = None) -> List[Tuple[int, int]]:
        """The last `count` (year, month) pairs, oldest first."""
        year, month, _ = self.to_parts(today or date.today())
        out: List[Tuple[int, int]] = []
        for back in range(count - 1, -1, -1):
            total = (year * 12 + (month - 1)) - back
            y, m = divmod(total, 12)
            out.append((y, m + 1))
        return out

    def today_in(self, timezone: str, now: Optional[datetime] = None) -> date:
        return jalali.today_in(timezone, now)

    def datetime_text(self, value: datetime, timezone: str = jalali.DEFAULT_TIMEZONE) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        try:
            zone = ZoneInfo(timezone)
        except Exception:
            zone = ZoneInfo(jalali.DEFAULT_TIMEZONE)
        local = value.astimezone(zone)
        at = "at" if self.name == "gregorian" else "ساعت"
        return f"{self.to_text(local.date())} {at} {local:%H:%M:%S}"


class _Jalali(Calendar):
    name = "jalali"
    weekday_names = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")

    def weekday_index(self, value: date) -> int:
        """0 for Saturday through 6 for Friday."""
        return (value.weekday() + 2) % 7

    def month_name(self, month: int) -> str:
        return jalali.month_name(month)

    def to_parts(self, value: date) -> Tuple[int, int, int]:
        return jalali.to_parts(value)

    def from_parts(self, year: int, month: int, day: int) -> date:
        return jalali.from_parts(year, month, day)

    def week_range(self, today: Optional[date] = None, offset: int = 0) -> Tuple[date, date]:
        # The Iranian week runs Saturday to Friday.
        return jalali.week_range(today, offset)


class _Gregorian(Calendar):
    name = "gregorian"
    weekday_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

    def weekday_index(self, value: date) -> int:
        """0 for Monday through 6 for Sunday."""
        return value.weekday()

    def month_name(self, month: int) -> str:
        return GREGORIAN_MONTHS[month - 1] if 1 <= month <= 12 else str(month)

    def to_parts(self, value: date) -> Tuple[int, int, int]:
        return value.year, value.month, value.day

    def from_parts(self, year: int, month: int, day: int) -> date:
        if not 1 <= month <= 12 or not 1 <= day <= _calendar.monthrange(year, month)[1]:
            raise ValueError("no such day")
        return date(year, month, day)

    def week_range(self, today: Optional[date] = None, offset: int = 0) -> Tuple[date, date]:
        # The ISO week runs Monday to Sunday.
        day = today or date.today()
        start = day - timedelta(days=day.weekday() + 7 * offset)
        return start, start + timedelta(days=6)


JALALI = _Jalali()
GREGORIAN = _Gregorian()
_BY_NAME = {JALALI.name: JALALI, GREGORIAN.name: GREGORIAN}


def named(name: Optional[str]) -> Calendar:
    """The calendar called `name`; the Jalali one when it is missing or unknown."""
    return _BY_NAME.get((name or "").lower(), JALALI)


def of(book) -> Calendar:
    """The calendar a book keeps its months by."""
    return named(getattr(book, "calendar", None))
