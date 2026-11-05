"""What the market looks like right now, for a client that wants to show it.

The rate provider answers "what is one TON in toman?" for the bot and the
wallet. A panel needs a different question: which prices, how old are they,
and can I still trust them? This is that question, kept in one place so the
HTTP route stays a thin translation and the bot could ask it too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Protocol, Sequence

from ..shared.errors import ServiceUnavailable, ValidationError
from ..shared.security import utcnow


class RateSource(Protocol):
    """What the board needs from a provider; `SwapWalletRates` already has it."""

    name: str

    @property
    def ttl_seconds(self) -> int: ...

    @property
    def fetched_at(self) -> Optional[datetime]: ...

    async def prices(self) -> dict: ...


# What a shop owner watches: the dollar-like token the market is quoted in,
# the two coins everybody has heard of, and the ones the wallet offers.
DEFAULT_PAIRS = ("USDT/IRT", "BTC/IRT", "ETH/IRT", "TON/IRT", "TRX/IRT", "BTC/USDT")

# A panel asks for a handful. The provider publishes hundreds, and an endpoint
# that returns whatever it is told to is a way to make us serialise all of them.
MAX_PAIRS = 20

_PAIR = re.compile(r"^[A-Z0-9]{1,12}/[A-Z0-9]{1,12}$")

UNAVAILABLE = "قیمت لحظه‌ای فعلاً در دسترس نیست؛ کمی بعد دوباره امتحان کن."
BAD_PAIR = "جفت‌ارز نامعتبر است؛ مثل USDT/IRT بنویس."
TOO_MANY = f"حداکثر {MAX_PAIRS} جفت‌ارز را می‌شود یک‌جا خواست."


@dataclass(frozen=True)
class Quote:
    pair: str
    base: str
    quote: str
    value: Decimal
    source: str
    fetched_at: datetime
    age_seconds: int
    # True when the provider could not be reached and this is the last good
    # price. It is still returned, flagged: an old price with its age is more
    # useful on a screen than a blank, and a reader who is told it is old can
    # decide for themselves.
    stale: bool


def parse_pairs(raw: Optional[str]) -> List[str]:
    """`"usdt/irt, ton/irt"` → `["USDT/IRT", "TON/IRT"]`; nothing → the defaults."""
    if raw is None or not raw.strip():
        return list(DEFAULT_PAIRS)

    pairs: List[str] = []
    for part in raw.split(","):
        pair = part.strip().upper()
        if not _PAIR.match(pair):
            raise ValidationError(BAD_PAIR)
        if pair not in pairs:
            pairs.append(pair)
    if len(pairs) > MAX_PAIRS:
        raise ValidationError(TOO_MANY)
    return pairs


class RateBoard:
    def __init__(self, source: RateSource) -> None:
        self.source = source

    async def quotes(self, pairs: Sequence[str]) -> List[Quote]:
        """The requested pairs the market actually publishes, in the order asked.

        A pair the provider does not publish is left out rather than guessed
        or inverted: the caller can see it is missing and say so. Raises
        `ServiceUnavailable` only when there is no price at all — neither fresh
        nor remembered — because then every answer would be a blank pretending
        to be a result.
        """
        prices = await self.source.prices()
        fetched_at = self.source.fetched_at
        if not prices or fetched_at is None:
            raise ServiceUnavailable(UNAVAILABLE)

        age = max(0, int((utcnow() - fetched_at).total_seconds()))
        # The provider only goes back to the network once its cache is older
        # than its ttl, and a successful fetch resets the clock. So an age past
        # the ttl after that call can only mean the fetch failed and this is
        # what was left over.
        stale = age >= self.source.ttl_seconds

        found: List[Quote] = []
        for pair in pairs:
            value = prices.get(pair)
            if value is None:
                continue
            base, quote = pair.split("/")
            found.append(
                Quote(
                    pair=pair, base=base, quote=quote, value=value,
                    source=self.source.name, fetched_at=fetched_at,
                    age_seconds=age, stale=stale,
                )
            )
        return found
