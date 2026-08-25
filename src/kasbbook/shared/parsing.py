"""Reading the amounts and dates people actually type.

Ported from the first generation, where these were shaped by real use: Persian
digits from a phone keyboard, "۲۵۰ک" for two hundred and fifty thousand, a
Jalali date with either separator. The one change is that money comes back as
`Decimal`, never `int` or `float`.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

import jdatetime

# Persian and Arabic-Indic digits are what a phone keyboard produces.
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# Longest first: "میلیون" must win over "م".
_UNITS = (
    ("میلیارد", Decimal("1000000000")),
    ("میلیون", Decimal("1000000")),
    ("هزار", Decimal("1000")),
    ("b", Decimal("1000000000")),
    ("m", Decimal("1000000")),
    ("k", Decimal("1000")),
    ("م", Decimal("1000000")),
    ("ک", Decimal("1000")),
    ("ه", Decimal("1000")),
)

_SEPARATORS = (",", "،", "٬", " ", "‌")


def to_ascii_digits(text: str) -> str:
    return (text or "").translate(_DIGIT_MAP)


def parse_amount(text: str) -> Optional[Decimal]:
    """Parse an amount the way a person writes it, or return None."""
    value = to_ascii_digits(text or "").strip()
    if not value:
        return None

    for junk in _SEPARATORS:
        value = value.replace(junk, "")
    value = value.replace("٫", ".")

    multiplier = Decimal("1")
    lowered = value.lower()
    for suffix, factor in _UNITS:
        # The length check stops a bare "k" from parsing as 1000.
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            value = value[: len(value) - len(suffix)]
            multiplier = factor
            break

    if not re.fullmatch(r"\d+(\.\d+)?", value):
        return None

    try:
        return Decimal(value) * multiplier
    except InvalidOperation:
        return None


def parse_date(text: str, today: Optional[date] = None) -> Optional[date]:
    """Accept either calendar and either separator, plus the obvious words.

    Which calendar is meant is decided by the year, not the separator: no
    Gregorian date this bot will see falls below 1500, and no Jalali one
    reaches it.
    """
    value = to_ascii_digits(text or "").strip()
    if not value:
        return None

    now = today or date.today()
    lowered = value.lower()
    if lowered in ("امروز", "today"):
        return now
    if lowered in ("دیروز", "yesterday"):
        return now - timedelta(days=1)
    if lowered in ("فردا", "tomorrow"):
        return now + timedelta(days=1)

    match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", value)
    if not match:
        return None

    year, month, day = (int(group) for group in match.groups())

    if year >= 1500:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    try:
        return jdatetime.date(year, month, day).togregorian()
    except (ValueError, TypeError):
        return None


def to_jalali(value: date) -> str:
    jalali = jdatetime.date.fromgregorian(date=value)
    return f"{jalali.year:04d}/{jalali.month:02d}/{jalali.day:02d}"
