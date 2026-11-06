"""Today's price of everything in the catalog, in toman, with where it came from.

Iranian gold, coins and silver come from the Iranian feed. The ounce prices come from the world feed
in dollars and are turned into toman through the dollar-pegged USDT, so they are estimates. Currencies
and crypto come from the existing quote function. When the Iranian feed is down the gram prices of
gold and silver are estimated from the ounce and say so; the coins have no estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from ...rates import quote as quoting
from ...rates.metals import GRAMS_PER_MESGHAL, GRAMS_PER_OUNCE, MetalPrices
from ...shared.money import quantize
from .catalog import CATALOG

TOMAN = "IRT"
FINE_18 = Decimal("0.75")


@dataclass(frozen=True)
class Price:
    code: str
    value: Optional[Decimal]      # toman for one unit; None when nobody can price it
    source: str
    exact: bool
    as_of: Optional[datetime]


async def price_table(metals: MetalPrices, rates, fiat) -> Dict[str, Price]:
    """Every catalog instrument's price in toman. An instrument that cannot be priced has `value=None`."""
    snap = await metals.snapshot()
    prices = await rates.prices()
    prices_at = rates.fetched_at
    per_usd = await fiat.per_usd()

    usdt = quoting.quote(prices, per_usd, "USDT", TOMAN, prices_at, fiat.fetched_at) if (prices or per_usd) else None
    dollar = usdt.value if usdt is not None else None

    def from_world(symbol: str) -> Optional[Decimal]:
        """Toman per ounce of the world price, through the dollar."""
        usd = snap.world.get(symbol)
        return usd * dollar if usd is not None and dollar is not None else None

    out: Dict[str, Price] = {}
    for item in CATALOG:
        price: Optional[Price] = None
        if item.source == "iran":
            if item.code in snap.iran:
                price = Price(item.code, snap.iran[item.code], "tgju", True, snap.iran_at)
            else:
                # The Iranian feed is down: gold and silver by the gram can still be estimated from the ounce.
                gold = from_world("XAU")
                silver = from_world("XAG")
                estimate = {
                    "gold24": gold / GRAMS_PER_OUNCE if gold is not None else None,
                    "gold18": gold / GRAMS_PER_OUNCE * FINE_18 if gold is not None else None,
                    "mesghal": gold / GRAMS_PER_OUNCE * GRAMS_PER_MESGHAL if gold is not None else None,
                    "silver": silver / GRAMS_PER_OUNCE if silver is not None else None,
                }.get(item.code)
                if estimate is not None:
                    price = Price(item.code, estimate, "world-estimate", False, snap.world_at)
        elif item.source == "world":
            value = from_world(item.code)
            if value is not None:
                price = Price(item.code, value, "gold-api+swapwallet", False, snap.world_at)
        elif item.source == "market" and (prices or per_usd):
            found = quoting.quote(prices, per_usd, item.code, TOMAN, prices_at, fiat.fetched_at)
            if found is not None:
                price = Price(item.code, found.value, found.source, found.exact, found.fetched_at)
        out[item.code] = price or Price(item.code, None, "", False, None)
    return {code: Price(p.code, quantize(p.value) if p.value is not None else None, p.source, p.exact, p.as_of)
            for code, p in out.items()}


def to_book_currency(
    base: str, prices: dict, per_usd: dict, prices_at, fiat_at
) -> Optional[Decimal]:
    """What one toman is worth in the book's currency, so every toman price can be shown in it."""
    if base == TOMAN:
        return Decimal("1")
    found = quoting.quote(prices, per_usd, TOMAN, base, prices_at, fiat_at)
    return found.value if found is not None else None
