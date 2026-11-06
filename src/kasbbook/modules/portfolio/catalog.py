"""What can be held, and where its price comes from."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    code: str
    name: str
    unit: str
    group: str       # gold, coin, metal, currency, crypto, other
    source: str      # iran (the Iranian market), world (an ounce in dollars), market (a currency feed), manual


CATALOG = (
    Instrument("gold18", "طلای ۱۸ عیار", "گرم", "gold", "iran"),
    Instrument("gold24", "طلای ۲۴ عیار", "گرم", "gold", "iran"),
    Instrument("mesghal", "مثقال طلا", "مثقال", "gold", "iran"),
    Instrument("coin_emami", "سکهٔ امامی", "عدد", "coin", "iran"),
    Instrument("coin_bahar", "سکهٔ بهار آزادی", "عدد", "coin", "iran"),
    Instrument("coin_half", "نیم‌سکه", "عدد", "coin", "iran"),
    Instrument("coin_quarter", "ربع‌سکه", "عدد", "coin", "iran"),
    Instrument("coin_gram", "سکهٔ گرمی", "عدد", "coin", "iran"),
    Instrument("silver", "نقرهٔ ۹۹۹", "گرم", "metal", "iran"),
    Instrument("XAU", "اونس جهانی طلا", "اونس", "gold", "world"),
    Instrument("XAG", "اونس جهانی نقره", "اونس", "metal", "world"),
    Instrument("XPT", "اونس جهانی پلاتین", "اونس", "metal", "world"),
    Instrument("XPD", "اونس جهانی پالادیوم", "اونس", "metal", "world"),
    Instrument("USD", "دلار آمریکا", "دلار", "currency", "market"),
    Instrument("EUR", "یورو", "یورو", "currency", "market"),
    Instrument("AED", "درهم امارات", "درهم", "currency", "market"),
    Instrument("TRY", "لیر ترکیه", "لیر", "currency", "market"),
    Instrument("USDT", "تتر", "تتر", "crypto", "market"),
    Instrument("BTC", "بیت‌کوین", "بیت‌کوین", "crypto", "market"),
    Instrument("ETH", "اتریوم", "اتریوم", "crypto", "market"),
    Instrument("TON", "تون‌کوین", "تون", "crypto", "market"),
    Instrument("other", "دیگر (قیمت را خودم می‌نویسم)", "واحد", "other", "manual"),
)

BY_CODE = {item.code: item for item in CATALOG}
