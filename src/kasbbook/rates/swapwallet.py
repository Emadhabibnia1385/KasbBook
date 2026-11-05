"""Live prices from SwapWallet's public market endpoint.

Read-only. The same API can execute swaps and withdraw funds; none of that is
reachable from here, and adding it would need a key this never asks for.

The endpoint needs no authentication and answers with

    {"status": "OK", "result": {"USDT/IRT": "230970", "TON/IRT": "316890", ...}}

The published schema shows only the inner object. Parsing what the service
actually returns, rather than what its example shows, is the difference between
working and a KeyError in production.

Prices arrive as strings and stay strings until Decimal, because a rate that
went through a float is a rate that is quietly wrong.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, Optional

import httpx

from ..shared.money import ZERO, to_decimal
from ..shared.security import utcnow

log = logging.getLogger(__name__)

URL = "https://swapwallet.app/api/v1/market/prices"

# After a failed fetch, wait this long before trying again. Without it every
# caller during an outage pays the full request timeout in turn, and a panel
# polling once a minute per open tab would hammer a service that is already
# down. Short, because the bot would rather retry soon than keep guessing.
RETRY_AFTER_FAILURE = 15


class SwapWalletRates:
    # What the panel shows beside a price, and what `/market/rates` reports.
    name = "swapwallet"

    def __init__(
        self,
        url: str = URL,
        timeout: float = 5.0,
        ttl_seconds: int = 60,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._ttl = ttl_seconds
        self._client = client
        self._cache: Dict[str, Decimal] = {}
        self._fetched_at = None
        self._failed_at = None

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    @property
    def fetched_at(self):
        """When the prices in the cache were obtained; None before the first success.

        Public so a caller can tell a price from this minute from the last good
        one kept through an outage: `prices()` returns both the same way.
        """
        return self._fetched_at

    async def prices(self) -> Dict[str, Decimal]:
        """Every pair the market publishes, cached briefly.

        A failure returns whatever was last known — possibly nothing. It never
        raises: somebody recording a sale must not be stopped because a price
        service is down.
        """
        now = utcnow()
        if self._fetched_at is not None:
            if (now - self._fetched_at).total_seconds() < self._ttl:
                return self._cache
        if self._failed_at is not None:
            if (now - self._failed_at).total_seconds() < RETRY_AFTER_FAILURE:
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
            log.warning("swapwallet prices unavailable: %s", exc.__class__.__name__)
            self._failed_at = now
            return self._cache

        raw = body.get("result") if isinstance(body, dict) else None
        if not isinstance(raw, dict):
            log.warning("swapwallet prices had no result object")
            self._failed_at = now
            return self._cache

        parsed: Dict[str, Decimal] = {}
        for pair, value in raw.items():
            try:
                amount = to_decimal(value)
            except ValueError:
                continue
            if amount > ZERO:
                parsed[pair.upper()] = amount

        if parsed:
            self._cache = parsed
            self._fetched_at = now
            self._failed_at = None
        else:
            self._failed_at = now
        return self._cache

    async def quote(self, code: str, base: str) -> Optional[Decimal]:
        code, base = code.upper(), base.upper()
        if code == base:
            return Decimal("1")

        prices = await self.prices()
        direct = prices.get(f"{code}/{base}")
        if direct:
            return direct
        # Only IRT and USDT are quote currencies, so the pair we want is
        # sometimes published the other way round.
        inverse = prices.get(f"{base}/{code}")
        if inverse and inverse > ZERO:
            return Decimal("1") / inverse
        return None
