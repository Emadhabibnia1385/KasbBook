"""Forgiving parsers for the amounts and dates people actually type."""

import jdatetime
import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from .config import TZ

# =========================
# Input parsing
# =========================
# Persian and Arabic-Indic digits are what people actually type on a phone
# keyboard, so every numeric field normalises them before doing anything else.
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def to_ascii_digits(s: str) -> str:
    return (s or "").translate(_DIGIT_MAP)

# Longest first: "میلیون" must win over "م".
_AMOUNT_UNITS: List[Tuple[str, int]] = [
    ("میلیارد", 1_000_000_000),
    ("میلیون", 1_000_000),
    ("هزار", 1_000),
    ("b", 1_000_000_000),
    ("m", 1_000_000),
    ("k", 1_000),
    ("م", 1_000_000),
    ("ک", 1_000),
    ("ه", 1_000),
]

def parse_amount(s: str) -> Optional[int]:
    """Parse an amount the way a person types it: ۲۵۰ک, 1.2m, 250,000, 2 میلیون."""
    t = to_ascii_digits(s or "").strip()
    if not t:
        return None

    for junk in (",", "،", "٬", " ", "‌", "٬"):
        t = t.replace(junk, "")
    t = t.replace("٫", ".").replace("/", ".")

    multiplier = 1
    low = t.lower()
    for suffix, factor in _AMOUNT_UNITS:
        # len check keeps a bare "k" from parsing as 1000
        if low.endswith(suffix) and len(low) > len(suffix):
            t = t[: len(t) - len(suffix)]
            multiplier = factor
            break

    if not re.fullmatch(r"\d+(\.\d+)?", t):
        return None

    return int(round(float(t) * multiplier))

def parse_date_any(s: str) -> Optional[str]:
    """
    Accept any reasonable way of writing a date and return Gregorian ISO.

    Jalali or Gregorian is decided by the year, not the separator: no Gregorian
    date the bot will ever see falls below 1500, and no Jalali one reaches it.
    """
    t = to_ascii_digits(s or "").strip()
    if not t:
        return None

    low = t.lower()
    today = datetime.now(TZ).date()
    if low in ("امروز", "today"):
        return today.strftime("%Y-%m-%d")
    if low in ("دیروز", "yesterday"):
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    if low in ("فردا", "tomorrow"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if not m:
        return None

    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))

    if y >= 1500:
        try:
            date(y, mo, d)
        except ValueError:
            return None
        return f"{y:04d}-{mo:02d}-{d:02d}"

    try:
        return jdatetime.date(y, mo, d).togregorian().strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None

# Both entry points accept either calendar; the labels are only a hint about
# which one the user probably meant to type.
def parse_gregorian(s: str) -> Optional[str]:
    return parse_date_any(s)

def parse_jalali_to_g(s: str) -> Optional[str]:
    return parse_date_any(s)
