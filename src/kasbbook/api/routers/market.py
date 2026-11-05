"""Live market prices for the panel.

Read-only and the same for everyone, so there is no book in the path; it still
needs a signed-in user, because an open price endpoint on our server is an open
relay to someone else's rate limit.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query

from ...rates.board import MAX_PAIRS, RateBoard, parse_pairs
from ..deps import CurrentUser, RatesDep
from ..schemas import MarketRateResponse

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
