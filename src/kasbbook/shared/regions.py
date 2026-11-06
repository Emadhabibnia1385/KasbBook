"""Where a person is, as far as a time zone says, and what that suggests for a book.

A time zone is the one place hint every client can give without asking: the
browser reports it and the account stores it. From it comes a country, and from
the country the money and the calendar its people keep books in. These are only
starting points that the person can change; nothing here is a rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Region:
    country: str
    currency: str
    calendar: str  # "jalali" or "gregorian"


# Iran and Afghanistan keep the Solar Hijri (Jalali) calendar; everyone else here the Gregorian.
_BY_COUNTRY = {
    "IR": Region("IR", "IRT", "jalali"),
    "AF": Region("AF", "AFN", "jalali"),
    "TR": Region("TR", "TRY", "gregorian"),
    "AE": Region("AE", "AED", "gregorian"),
    "SA": Region("SA", "SAR", "gregorian"),
    "IQ": Region("IQ", "IQD", "gregorian"),
    "KW": Region("KW", "KWD", "gregorian"),
    "QA": Region("QA", "QAR", "gregorian"),
    "OM": Region("OM", "OMR", "gregorian"),
    "BH": Region("BH", "BHD", "gregorian"),
    "AM": Region("AM", "AMD", "gregorian"),
    "AZ": Region("AZ", "AZN", "gregorian"),
    "GE": Region("GE", "GEL", "gregorian"),
    "PK": Region("PK", "PKR", "gregorian"),
    "IN": Region("IN", "INR", "gregorian"),
    "GB": Region("GB", "GBP", "gregorian"),
    "US": Region("US", "USD", "gregorian"),
    "CA": Region("CA", "CAD", "gregorian"),
    "AU": Region("AU", "AUD", "gregorian"),
    "DE": Region("DE", "EUR", "gregorian"),
    "CN": Region("CN", "CNY", "gregorian"),
    "JP": Region("JP", "JPY", "gregorian"),
    "RU": Region("RU", "RUB", "gregorian"),
    "EG": Region("EG", "EGP", "gregorian"),
    "EU": Region("EU", "EUR", "gregorian"),
}

_ZONE_COUNTRY = {
    "Asia/Tehran": "IR",
    "Asia/Kabul": "AF",
    "Europe/Istanbul": "TR", "Asia/Istanbul": "TR",
    "Asia/Dubai": "AE", "Asia/Riyadh": "SA", "Asia/Baghdad": "IQ",
    "Asia/Kuwait": "KW", "Asia/Qatar": "QA", "Asia/Muscat": "OM", "Asia/Bahrain": "BH",
    "Asia/Yerevan": "AM", "Asia/Baku": "AZ", "Asia/Tbilisi": "GE",
    "Asia/Karachi": "PK", "Asia/Kolkata": "IN", "Asia/Calcutta": "IN",
    "Europe/London": "GB",
    "America/Toronto": "CA", "America/Vancouver": "CA", "America/Edmonton": "CA",
    "America/Winnipeg": "CA", "America/Halifax": "CA",
    "Europe/Berlin": "DE", "Asia/Shanghai": "CN", "Asia/Tokyo": "JP",
    "Europe/Moscow": "RU", "Africa/Cairo": "EG",
}

# Zones not named above fall back on their continent, which is right often enough for a first guess.
_PREFIX = (
    ("Europe/", "EU"),
    ("America/", "US"),
    ("Australia/", "AU"),
)

# Someone whose zone says nothing useful is most likely one of the people this product was made for.
DEFAULT = _BY_COUNTRY["IR"]


def region_for_zone(timezone: Optional[str]) -> Region:
    """The country, money and calendar a time zone suggests."""
    zone = (timezone or "").strip()
    country = _ZONE_COUNTRY.get(zone)
    if country is None:
        for prefix, fallback in _PREFIX:
            if zone.startswith(prefix):
                country = fallback
                break
    return _BY_COUNTRY.get(country or "", DEFAULT)
