"""Jalali calendar conversions and period ranges."""

import jdatetime
from datetime import date, datetime, timedelta
from typing import Tuple

from .config import TZ

def g_to_j(g_yyyy_mm_dd: str) -> str:
    y, m, d = map(int, g_yyyy_mm_dd.split("-"))
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    return f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}"

# =========================
# Jalali calendar
# =========================
# Transactions store a Gregorian date_g (ISO, so plain string comparison sorts
# correctly). Reports are Jalali, so every Jalali period is converted into a
# Gregorian [start, end) pair before it ever reaches SQL.
JMONTHS = [
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند",
]

def jmonth_name(jm: int) -> str:
    return JMONTHS[jm - 1] if 1 <= jm <= 12 else f"{jm:02d}"

def g_to_j_parts(g_yyyy_mm_dd: str) -> Tuple[int, int, int]:
    y, m, d = map(int, g_yyyy_mm_dd.split("-"))
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    return (jd.year, jd.month, jd.day)

def j_to_g_str(jy: int, jm: int, jd: int) -> str:
    return jdatetime.date(jy, jm, jd).togregorian().strftime("%Y-%m-%d")

def j_year_range_g(jy: int) -> Tuple[str, str]:
    """Gregorian [start, end) spanning a whole Jalali year."""
    return (j_to_g_str(jy, 1, 1), j_to_g_str(jy + 1, 1, 1))

def j_month_range_g(jy: int, jm: int) -> Tuple[str, str]:
    """Gregorian [start, end) spanning a single Jalali month."""
    start = j_to_g_str(jy, jm, 1)
    end = j_to_g_str(jy + 1, 1, 1) if jm == 12 else j_to_g_str(jy, jm + 1, 1)
    return (start, end)

# =========================
# Weeks
# =========================
def week_range_g(offset: int = 0) -> Tuple[str, str]:
    """Inclusive [start, end] of a week, counting from Saturday like the Iranian week."""
    today = datetime.now(TZ).date()
    since_saturday = (today.weekday() + 2) % 7
    start = today - timedelta(days=since_saturday + 7 * offset)
    return (start.strftime("%Y-%m-%d"), (start + timedelta(days=6)).strftime("%Y-%m-%d"))

# =========================
# Loans / installments
# =========================
def add_jalali_months(g_date: str, months: int) -> str:
    """Shift a date by whole Jalali months, clamping onto short months."""
    jy, jm, jd = g_to_j_parts(g_date)
    total = (jy * 12 + (jm - 1)) + months
    ny, nm = divmod(total, 12)
    nm += 1

    day = jd
    while day > 1:
        try:
            return j_to_g_str(ny, nm, day)
        except (ValueError, TypeError):
            day -= 1
    return j_to_g_str(ny, nm, 1)
