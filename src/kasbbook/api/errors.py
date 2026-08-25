"""Domain errors, translated into HTTP once.

This is the only place in the codebase that knows what a status code is. A
service raises `NotFound`; whether that becomes a 404 or a Persian sentence in
a Telegram message is decided at the edge, and there are two edges.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..shared.errors import KasbBookError

logger = logging.getLogger("kasbbook.api")


def install(app: FastAPI) -> None:
    @app.exception_handler(KasbBookError)
    async def _domain_error(request: Request, error: KasbBookError) -> JSONResponse:
        return JSONResponse(
            status_code=getattr(error, "status_code", 400),
            content={"detail": str(error) or error.__class__.__name__},
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, error: Exception) -> JSONResponse:
        # Logged in full, reported as nothing. An exception message can carry a
        # query, a path or a value from someone else's account.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "something went wrong on our side"},
        )
