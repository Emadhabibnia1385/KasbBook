"""Rates between the world's national currencies, from exchangerate-api's open endpoint.

SwapWallet publishes crypto and nothing else (checked: 373 pairs, no dollar, euro or dirham),
so national currencies need a feed of their own. This one needs no key, covers about 160
currencies and refreshes once a day, which is why it is cached for an hour and why every
answer carries its age: it is a daily rate, not a tick.

Its terms ask for attribution, so the panel names the source beside any figure from it.

Its `IRR` is not used anywhere. It is an official-style figure far from what the toman
trades at, so rials and tomans are priced from the market's own USDT/IRT instead
(see `quote.py`).
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

import httpx

from ..shared.money import ZERO, to_decimal
from ..shared.security import utcnow

log = logging.getLogger(__name__)

URL = "https://open.er-api.com/v6/latest/USD"


class OpenErRates:
    name = "exchangerate-api"
    ttl_seconds = 3600

    def __init__(self, url: str = URL, timeout: float = 5.0, client: Optional[httpx.AsyncClient] = None) -> None:
        self._url, self._timeout, self._client = url, timeout, client
        self._cache: Dict[str, Decimal] = {}
        self._fetched_at: Optional[datetime] = None

    @property
    def fetched_at(self) -> Optional[datetime]:
        return self._fetched_at

    async def per_usd(self) -> Dict[str, Decimal]:
        """How many units of each currency one US dollar buys. The last good table if the feed is down."""
        now = utcnow()
        if self._fetched_at is not None and (now - self._fetched_at).total_seconds() < self.ttl_seconds:
            return self._cache
        try:
            if self._client is not None:
                response = await self._client.get(self._url, timeout=self._timeout)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(self._url)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # noqa: BLE001 - any failure means "no quote"
            log.warning("fiat rates unavailable: %s", exc.__class__.__name__)
            return self._cache
        raw = body.get("rates") if isinstance(body, dict) and body.get("result") == "success" else None
        if not isinstance(raw, dict):
            log.warning("fiat rates had no table")
            return self._cache
        parsed: Dict[str, Decimal] = {}
        for code, value in raw.items():
            try:
                amount = to_decimal(str(value))
            except ValueError:
                continue
            if amount > ZERO:
                parsed[code.upper()] = amount
        if parsed:
            self._cache, self._fetched_at = parsed, now
        return self._cache
