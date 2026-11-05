"""Live market prices for the panel.

Read-only and the same for everyone, so there is no book in the path; it still
needs a signed-in user, because an open price endpoint on our server is an open
relay to someone else's rate limit.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query, Request

from ...rates import quote as quoting
from ...rates.board import MAX_PAIRS, RateBoard, parse_pairs
from ...shared.errors import ServiceUnavailable, ValidationError
from ...shared.security import utcnow
from ..deps import CurrentUser, RatesDep
from ..schemas import MarketRateResponse, QuoteResponse

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/rates", response_model=List[MarketRateResponse])
async def rates(
    user: CurrentUser,
    rates: RatesDep,
    pairs: Optional[str] = Query(
        default=None,
        description=(
            "Comma-separated pairs such as `USDT/IRT,TON/USDT`, at most "
            f"{MAX_PAIRS}. Omitted: the pairs a shop owner watches. A pair the "
            "market does not publish is left out of the answer, not guessed."
        ),
    ),
) -> List[MarketRateResponse]:
    """Current prices, each with its source and when it was fetched.

    Prices are cached in the process for about a minute, so polling this does
    not become polling the provider. While the provider is down the last good
    prices are returned with `stale: true` and their age; with none at all the
    answer is 503.
    """
    quotes = await RateBoard(rates).quotes(parse_pairs(pairs))
    return [
        MarketRateResponse(
            pair=q.pair, base=q.base, quote=q.quote,
            value=format(q.value, "f"),
            source=q.source, fetched_at=q.fetched_at,
            age_seconds=q.age_seconds, stale=q.stale,
        )
        for q in quotes
    ]


# ---------------------------------------------------------------- quotes
MAX_CODES = 30


def _plain(value) -> str:
    """A rate as a plain decimal string: ten places is far more than any price needs, and trailing zeros are noise."""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


@router.get("/quotes", response_model=List[QuoteResponse])
async def quotes(
    request: Request,
    user: CurrentUser,
    rates: RatesDep,
    base: str = Query(default="IRT", min_length=2, max_length=8),
    codes: str = Query(description="Comma-separated currency codes, at most 30; e.g. USD,EUR,TON"),
) -> List[QuoteResponse]:
    """What one unit of each code is worth in `base`, across crypto, the toman and national currencies.

    `exact` is false for an estimate: a national currency in toman is priced through the
    dollar-pegged USDT, because no feed publishes the dollar in toman. A code nothing can price is
    left out rather than guessed. With no price from either feed the answer is 503.
    """
    wanted = [c.strip().upper() for c in codes.split(",") if c.strip()]
    if not wanted or len(wanted) > MAX_CODES or any(not c.isalnum() or len(c) > 8 for c in wanted):
        raise ValidationError("codes must be 1 to 30 currency codes")
    prices = await rates.prices()
    prices_at = rates.fetched_at
    fiat = request.app.state.fiat
    per_usd = await fiat.per_usd()
    if not prices and not per_usd:
        raise ServiceUnavailable("قیمت لحظه‌ای فعلاً در دسترس نیست؛ کمی بعد دوباره امتحان کن.")
    out: List[QuoteResponse] = []
    now = utcnow()
    for code in wanted:
        found = quoting.quote(prices, per_usd, code, base.upper(), prices_at, fiat.fetched_at)
        if found is None:
            continue
        stamp = found.fetched_at
        age = max(0, int((now - stamp).total_seconds())) if stamp else 0
        out.append(QuoteResponse(
            code=code, base=base.upper(), value=_plain(found.value), exact=found.exact,
            source=found.source, fetched_at=stamp, age_seconds=age,
        ))
    return out
