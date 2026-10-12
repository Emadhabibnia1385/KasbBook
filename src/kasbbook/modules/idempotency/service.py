"""Claiming an Idempotency-Key, and remembering the answer it was given.

Semantics follow the IETF httpapi `Idempotency-Key` draft:
- the same key with the same request replays the stored answer;
- the same key with a different request is refused (422);
- the same key while its first request is still running is refused (409).

Nothing here commits: the claim lives in the request's own transaction, so it
commits with the work or rolls back with it.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import KasbBookError
from ...shared.security import utcnow
from .models import IdempotencyKey

# Long enough to cover a client retrying across a night offline, short enough
# that the table does not keep every request forever.
TTL = timedelta(hours=48)

# Opaque to the server, but bounded and printable: a UUID, a ULID or any
# client-made token fits.
KEY_PATTERN = re.compile(r"[A-Za-z0-9._:-]{8,64}")


class KeyMalformed(KasbBookError):
    """The header is there but is not a usable key."""

    status_code = 400


class KeyRequired(KasbBookError):
    """The route moves money out and will not run without a key."""

    status_code = 400


class KeyReused(KasbBookError):
    """The same key was sent with a different request."""

    status_code = 422


class KeyInFlight(KasbBookError):
    """The first request with this key has not finished yet."""

    status_code = 409


@dataclass
class Claim:
    """What a route does next: replay a stored answer, or do the work and record it."""

    row: Optional[IdempotencyKey] = None
    replay_status: Optional[int] = None
    replay_body: Any = None

    @property
    def is_replay(self) -> bool:
        return self.replay_status is not None


class IdempotencyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim(
        self, user_id: uuid.UUID, key: str, method: str, path: str, request_hash: str
    ) -> Claim:
        if not KEY_PATTERN.fullmatch(key or ""):
            raise KeyMalformed(
                "Idempotency-Key must be 8-64 characters of letters, digits, '.', '_', ':' or '-'"
            )

        now = utcnow()
        scope = (
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.key == key,
            IdempotencyKey.method == method,
            IdempotencyKey.path == path,
        )
        existing = await self.session.scalar(select(IdempotencyKey).where(*scope))

        if existing is not None and _expires(existing) <= now:
            # A key past its window is a new key: the old answer is forgotten.
            await self.session.execute(delete(IdempotencyKey).where(*scope))
            existing = None

        if existing is not None:
            if existing.request_hash != request_hash:
                raise KeyReused(
                    "this Idempotency-Key was already used with a different request"
                )
            if existing.status_code is None:
                raise KeyInFlight("a request with this Idempotency-Key is still running")
            return Claim(
                replay_status=existing.status_code,
                replay_body=json.loads(existing.response_body or "null"),
            )

        row = IdempotencyKey(
            user_id=user_id, key=key, method=method, path=path,
            request_hash=request_hash, expires_at=now + TTL,
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError:
            # A concurrent request with the same key got there first. Refusing
            # rolls this whole request back - the claim comes before any work,
            # so there is nothing else to lose. Not a savepoint: on SQLite's
            # default transaction mode a savepoint opened before any other write
            # commits on release, and the claim would outlive a failed request.
            raise KeyInFlight(
                "a request with this Idempotency-Key is still running"
            ) from None
        return Claim(row=row)

    async def record(self, claim: Claim, status_code: int, body: Any) -> None:
        """Store the answer the work produced, in the same transaction as the work."""
        if claim.row is None:
            return
        claim.row.status_code = status_code
        claim.row.response_body = json.dumps(body, ensure_ascii=False)
        await self.session.flush()


def _expires(row: IdempotencyKey):
    # SQLite hands back naive datetimes; they were written as UTC.
    value = row.expires_at
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
