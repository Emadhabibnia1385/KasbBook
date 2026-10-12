"""The HTTP side of Idempotency-Key: read the header, replay, remember.

A route that moves money calls `claim()` first. If the claim is a replay it
returns `replay(claim)` and does nothing else; otherwise it does its work and
passes its response through `remember()`, which stores it in the same
transaction as the work. The rules themselves live in IdempotencyService.

Used explicitly in each route rather than as middleware: which routes are
guarded, and which require a key, is then visible where the route is written.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..modules.idempotency.service import Claim, IdempotencyService, KeyRequired

HEADER = "Idempotency-Key"


async def claim(
    request: Request, session: AsyncSession, user_id, *, required: bool = False
) -> Claim:
    key = request.headers.get(HEADER)
    if key is None:
        if required:
            raise KeyRequired(
                f"this request moves money out and needs an {HEADER} header, "
                "so a retry cannot pay twice"
            )
        return Claim()

    # The whole request, not just the body: the same key on a different path,
    # or with different query parameters, is a different request.
    digest = hashlib.sha256()
    for part in (request.method, request.url.path, str(request.url.query)):
        digest.update(part.encode("utf-8") + b"\0")
    digest.update(await request.body())

    return await IdempotencyService(session).claim(
        user_id, key, request.method, request.url.path, digest.hexdigest()
    )


def replay(found: Claim) -> JSONResponse:
    return JSONResponse(
        content=found.replay_body,
        status_code=found.replay_status,
        headers={"Idempotent-Replay": "true"},
    )


async def remember(session: AsyncSession, found: Claim, status_code: int, response: Any) -> Any:
    """Store what the route is about to return, and return it unchanged."""
    await IdempotencyService(session).record(found, status_code, jsonable_encoder(response))
    return response
