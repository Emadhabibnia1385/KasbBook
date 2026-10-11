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

    # How often to look for windows that have ended. A sweep is O(keys), so it
    # runs on a timer rather than on every hit.
    SWEEP_EVERY = 60.0

    def __init__(self) -> None:
        self._counts: Dict[str, Tuple[int, float]] = {}
        self._next_sweep = 0.0

    async def hit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        now = time.time()
        self._sweep(now)
        count, resets_at = self._counts.get(key, (0, now + window_seconds))

        if now >= resets_at:
            count, resets_at = 0, now + window_seconds

        count += 1
        self._counts[key] = (count, resets_at)
        return count <= limit, max(0, int(resets_at - now))

    def _sweep(self, now: float) -> None:
        """Forget windows that have ended; every distinct client otherwise
        stays in memory for as long as the process lives, and an attacker who
        varies the key (a fresh address or login name per request) grows it
        without bound."""
        if now < self._next_sweep:
            return
        self._next_sweep = now + self.SWEEP_EVERY
        for key in [k for k, (_, resets_at) in self._counts.items() if now >= resets_at]:
            del self._counts[key]


class RedisRateLimiter:
    """Shared across workers, which is the only way this is true in production."""

    def __init__(self, client) -> None:
        self._client = client

    async def hit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        full_key = f"kasbbook:rate:{key}"

        # One MULTI/EXEC. The expiry used to be a second round trip after INCR,
        # so a crash between the two left a counter with no TTL that never
        # reset and locked that client out for good. SET NX EX creates the key
        # with its TTL in the same transaction (and works on any Redis, unlike
        # EXPIRE NX), so only the first hit of a window sets the clock and a
        # flood cannot keep pushing the reset further away.
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.set(full_key, 0, nx=True, ex=window_seconds)
            pipe.incr(full_key)
            pipe.ttl(full_key)
            _, count, ttl = await pipe.execute()

        if ttl < 0:
            # A key written by the old non-atomic code, already stranded
            # without a TTL: give it one so it heals instead of locking forever.
            await self._client.expire(full_key, window_seconds)
            ttl = window_seconds

        return count <= limit, max(0, int(ttl))
