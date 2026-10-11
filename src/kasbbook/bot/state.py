"""Where a half-finished conversation lives between two messages.

A user picking a book, then a category, then typing an amount is three separate
updates; something has to remember the first two. That store is behind an
interface because it will be Redis in production and a dictionary in tests, and
the conversation code should not be able to tell the difference.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Protocol

# Long enough to finish a flow, short enough that an abandoned one does not
# reappear days later and confuse someone.
DEFAULT_TTL_SECONDS = 30 * 60


class StateStore(Protocol):
    async def get(self, key: str) -> Dict[str, Any]:
        ...

    async def set(self, key: str, value: Dict[str, Any], ttl: int = DEFAULT_TTL_SECONDS) -> None:
        ...

    async def clear(self, key: str) -> None:
        ...

    async def pop(self, key: str) -> Dict[str, Any]:
        """Read the value and remove it in one step; {} if there was none.

        This is how a draft is *claimed*: of two concurrent confirm taps, only
        one gets the draft back, so only one records it. A `get` followed by a
        `clear` cannot do that, because both taps read before either clears.
        """
        ...


class MemoryStateStore:
    """In-process state, for tests and single-worker development.

    Expiry is checked on read rather than swept, which is enough for a store
    that never outlives the process.
    """

    def __init__(self) -> None:
        self._data: Dict[str, tuple] = {}

    async def get(self, key: str) -> Dict[str, Any]:
        entry = self._data.get(key)
        if entry is None:
            return {}

        value, expires_at = entry
        if expires_at is not None and expires_at <= time.time():
            self._data.pop(key, None)
            return {}
        return dict(value)

    async def set(
        self, key: str, value: Dict[str, Any], ttl: int = DEFAULT_TTL_SECONDS
    ) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._data[key] = (dict(value), expires_at)

    async def clear(self, key: str) -> None:
        self._data.pop(key, None)

    async def pop(self, key: str) -> Dict[str, Any]:
        # There is no await between the read and the removal, so no other task
        # can run in between: on one event loop that is atomic.
        value = await self.get(key)
        self._data.pop(key, None)
        return value


class RedisStateStore:
    """Redis-backed state, for running more than one worker.

    Kept deliberately thin: the same three operations, serialised as JSON, so
    swapping it in changes nothing above this file.
    """

    def __init__(self, redis: Any, prefix: str = "kasbbook:state:") -> None:
        self._redis = redis
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> Dict[str, Any]:
        import json

        raw = await self._redis.get(self._key(key))
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            # Unreadable state is worse than none: start the flow over.
            await self.clear(key)
            return {}

    async def set(
        self, key: str, value: Dict[str, Any], ttl: int = DEFAULT_TTL_SECONDS
    ) -> None:
        import json

        await self._redis.set(self._key(key), json.dumps(value), ex=ttl)

    async def clear(self, key: str) -> None:
        await self._redis.delete(self._key(key))

    async def pop(self, key: str) -> Dict[str, Any]:
        import json

        # GETDEL (Redis 6.2+, deploy/ runs 7) reads and deletes in one command,
        # so two workers cannot both receive the same draft.
        raw = await self._redis.getdel(self._key(key))
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            return {}


def conversation_key(provider: str, external_id: str) -> str:
    """One conversation per person per messenger."""
    return f"{provider}:{external_id}"
