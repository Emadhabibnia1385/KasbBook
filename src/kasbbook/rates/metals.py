"""Prices of gold, coins and metals.

Two feeds, because no single one has both halves:

* the Iranian market (gold by the gram and the mithqal, the coins, silver), from tgju's public
  indicator feed, quoted in rials: a tenth of that is the toman price;
* the world market (an ounce of gold, silver, platinum, palladium) in US dollars, from
  gold-api.com's open endpoint, which needs no key.

Neither is an official API with a promise, so each is cached for a few minutes, a failure keeps the
last good table, and every figure carries when it was fetched. When the Iranian feed is down the
gram prices of gold and silver can still be estimated from the ounce, and are marked as estimates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

import httpx

from ..shared.money import ZERO, to_decimal
from ..shared.security import utcnow

log = logging.getLogger(__name__)

IRAN_URL = "https://call1.tgju.org/ajax.json"
WORLD_URL = "https://api.gold-api.com/price/{symbol}"

# tgju's own keys, by what they are. Their figures are rials.
IRAN_KEYS = {
    "gold18": "geram18",
    "gold24": "geram24",
    "mesghal": "mesghal",
    "coin_emami": "sekee",
    "coin_bahar": "sekeb",
    "coin_half": "nim",
    "coin_quarter": "rob",
    "coin_gram": "gerami",
    "silver": "silver_999",
}

WORLD_SYMBOLS = ("XAU", "XAG", "XPT", "XPD")
GRAMS_PER_OUNCE = Decimal("31.1034768")
GRAMS_PER_MESGHAL = Decimal("4.6083")


@dataclass
class MetalSnapshot:
    """What the two feeds said, and when."""

    iran: Dict[str, Decimal] = field(default_factory=dict)       # toman per unit, by instrument code
    iran_at: Optional[datetime] = None
    world: Dict[str, Decimal] = field(default_factory=dict)      # US dollars per troy ounce, by symbol
    world_at: Optional[datetime] = None


class MetalPrices:
    name = "metals"
    ttl_seconds = 300

    def __init__(
        self,
        iran_url: str = IRAN_URL,
        world_url: str = WORLD_URL,
        timeout: float = 6.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._iran_url, self._world_url, self._timeout, self._client = iran_url, world_url, timeout, client
        self._snapshot = MetalSnapshot()

    async def _get(self, url: str):
        if self._client is not None:
            response = await self._client.get(url, timeout=self._timeout)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
        response.raise_for_status()
        return response.json()

    def _fresh(self, at: Optional[datetime]) -> bool:
        return at is not None and (utcnow() - at).total_seconds() < self.ttl_seconds

    async def snapshot(self) -> MetalSnapshot:
        """Both tables, refreshed when they are older than a few minutes; the last good ones when a feed is down."""
        if not self._fresh(self._snapshot.iran_at):
            await self._refresh_iran()
        if not self._fresh(self._snapshot.world_at):
            await self._refresh_world()
        return self._snapshot

    async def _refresh_iran(self) -> None:
        try:
            body = await self._get(self._iran_url)
            current = body["current"]
        except Exception as exc:  # noqa: BLE001 - any failure means "keep what we had"
            log.warning("iran gold prices unavailable: %s", exc.__class__.__name__)
            return
        parsed: Dict[str, Decimal] = {}
        for code, key in IRAN_KEYS.items():
            try:
                rials = to_decimal(str(current[key]["p"]).replace(",", ""))
            except (KeyError, ValueError, TypeError):
                continue
            if rials > ZERO:
                parsed[code] = rials / 10
        if parsed:
            self._snapshot.iran, self._snapshot.iran_at = parsed, utcnow()

    async def _refresh_world(self) -> None:
        parsed: Dict[str, Decimal] = {}
        for symbol in WORLD_SYMBOLS:
            try:
                body = await self._get(self._world_url.format(symbol=symbol))
                price = to_decimal(str(body["price"]))
            except Exception as exc:  # noqa: BLE001
                log.warning("world %s price unavailable: %s", symbol, exc.__class__.__name__)
                continue
            if price > ZERO:
                parsed[symbol] = price
        if parsed:
            self._snapshot.world, self._snapshot.world_at = parsed, utcnow()
