"""A fixed-window rate limiter.

Behind a protocol for the same reason conversation state is: it counts in
memory on a single worker and in Redis when there is more than one, and the
routes must not be able to tell which.

Fixed windows are not the most elegant algorithm — a burst can straddle a
boundary and get double the budget for a moment. That is an acceptable trade
for something a login route can afford to consult on every request. What it
buys is the thing that matters: password guessing stops being free.
"""

from __future__ import annotations

import time
from typing import Dict, Protocol, Tuple


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """Record one attempt. Returns (allowed, seconds until the window resets)."""


class MemoryRateLimiter:
    """Single process only. Correct on one worker, useless across several."""

    def __init__(self) -> None:
        self._counts: Dict[str, Tuple[int, float]] = {}

    async def hit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        now = time.time()
        count, resets_at = self._counts.get(key, (0, now + window_seconds))

        if now >= resets_at:
            count, resets_at = 0, now + window_seconds

        count += 1
        self._counts[key] = (count, resets_at)
        return count <= limit, max(0, int(resets_at - now))


class RedisRateLimiter:
    """Shared across workers, which is the only way this is true in production."""

    def __init__(self, client) -> None:
        self._client = client

    async def hit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        full_key = f"kasbbook:rate:{key}"
        count = await self._client.incr(full_key)

        if count == 1:
            # Only the first request in a window sets the expiry, so a flood
            # cannot keep pushing the reset further away.
            await self._client.expire(full_key, window_seconds)

        ttl = await self._client.ttl(full_key)
        return count <= limit, max(0, int(ttl))
