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


class SwapWalletRates:
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
            return self._cache

        raw = body.get("result") if isinstance(body, dict) else None
        if not isinstance(raw, dict):
            log.warning("swapwallet prices had no result object")
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
