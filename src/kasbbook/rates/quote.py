"""What one unit of a currency is worth in another, across crypto, the toman and national currencies.

Three kinds of money, two feeds, and no single one covers all of them:

* crypto and the toman are priced by SwapWallet (`X/IRT`, `X/USDT`);
* national currencies are priced against each other by exchangerate-api (per US dollar);
* a national currency *in toman* is on neither: nobody here publishes the dollar's price in
  toman. The honest path is the dollar-pegged USDT's price in toman, so those figures are
  **estimates** and say so (`exact=False`) — the same for crypto against a national currency,
  which treats USDT as one dollar.

`exact` is the contract with the screen: a figure with it set may be shown as a price; one
without must be shown as an estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from ..shared.money import ZERO

TOMAN, RIAL = "IRT", "IRR"
ONE = Decimal("1")


@dataclass(frozen=True)
class Quote:
    value: Decimal          # units of `dst` for one unit of `src`
    exact: bool
    source: str
    fetched_at: Optional[datetime]


def _swapwallet_rate(prices: Dict[str, Decimal], src: str, dst: str) -> Optional[Decimal]:
    """A rate SwapWallet itself publishes or implies: direct, inverse, or bridged through USDT."""
    if src == dst:
        return ONE
    direct = prices.get(f"{src}/{dst}")
    if direct:
        return direct
    inverse = prices.get(f"{dst}/{src}")
    if inverse and inverse > ZERO:
        return ONE / inverse
    # Bridged: both sides priced in USDT, or one in USDT and the toman is the other.
    def in_usdt(code: str) -> Optional[Decimal]:
        if code == "USDT":
            return ONE
        if code == TOMAN:
            toman = prices.get("USDT/IRT")
            return ONE / toman if toman else None
        return prices.get(f"{code}/USDT")
    a, b = in_usdt(src), in_usdt(dst)
    if a and b:
        return a / b
    return None


def _in_toman(prices: Dict[str, Decimal], code: str) -> Optional[Decimal]:
    return _swapwallet_rate(prices, code, TOMAN)


def quote(
    prices: Dict[str, Decimal],
    per_usd: Dict[str, Decimal],
    src: str,
    dst: str,
    prices_at: Optional[datetime],
    fiat_at: Optional[datetime],
) -> Optional[Quote]:
    src, dst = src.upper(), dst.upper()
    if src == dst:
        return Quote(ONE, True, "-", None)

    # The rial is ten tomans; everything about it follows from the toman.
    if RIAL in (src, dst):
        other = dst if src == RIAL else src
        base = quote(prices, per_usd, TOMAN if src == RIAL else src, other if src == RIAL else TOMAN,
                     prices_at, fiat_at)
        if base is None:
            return None
        value = base.value / 10 if src == RIAL else base.value * 10
        return Quote(value, base.exact, base.source, base.fetched_at)

    pure = _swapwallet_rate(prices, src, dst)
    if pure is not None and prices:
        return Quote(pure, True, "swapwallet", prices_at)

    src_fiat, dst_fiat = src in per_usd and src != TOMAN, dst in per_usd and dst != TOMAN
    # Two national currencies: exchangerate-api's own cross rate, exact.
    if src_fiat and dst_fiat:
        return Quote(per_usd[dst] / per_usd[src], True, "exchangerate-api", fiat_at)

    # One side a national currency and the other crypto or toman: through the dollar, treating USDT as one.
    if (src_fiat and not dst_fiat) or (dst_fiat and not src_fiat):
        fiat, other, fiat_is_src = (src, dst, True) if src_fiat else (dst, src, False)
        # What one dollar is worth in `other`, by way of USDT.
        dollar_in_other = _swapwallet_rate(prices, "USDT", other)
        if dollar_in_other is None:
            return None
        fiat_per_dollar = per_usd[fiat]
        value = dollar_in_other / fiat_per_dollar if fiat_is_src else fiat_per_dollar / dollar_in_other
        source = "swapwallet+exchangerate-api" if other != "USDT" else "exchangerate-api"
        return Quote(value, False, source, min(t for t in (prices_at, fiat_at) if t is not None) if (prices_at or fiat_at) else None)
    return None
