"""Domain errors, translated into HTTP once — and every error in one shape.

This is the only place in the codebase that knows what a status code is. A
service raises `NotFound`; whether that becomes a 404 or a Persian sentence in
a Telegram message is decided at the edge, and there are two edges.

Every error the API returns looks the same:

    {"detail": ..., "error": {"code", "message", "request_id", "fields"?}}

`detail` is what docs/api.md always promised and stays as it was. `error` is
the part a program reads: a stable `code` to branch on rather than a sentence
to match, and the `request_id` that finds the request in the logs. Before this
the API answered in four shapes, so a client had to guess which it had.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..shared.errors import KasbBookError

logger = logging.getLogger("kasbbook.api")

HEADER = "X-Request-Id"
# A caller's own id is kept when it is a sane token, so its logs and ours line
# up; anything else is replaced, so a header cannot inject into a log line.
_ACCEPTABLE = re.compile(r"[A-Za-z0-9._-]{8,64}")

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}


class RequestIdMiddleware:
    """Give every request an id and put it on every response.

    Pure ASGI rather than BaseHTTPMiddleware, and the id is kept on the scope:
    an unhandled exception is answered by Starlette's outermost layer, after
    this one has unwound, and that handler reads the id from the scope.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sent = dict(scope.get("headers") or []).get(HEADER.lower().encode(), b"")
        offered = sent.decode("latin-1")
        request_id = offered if _ACCEPTABLE.fullmatch(offered) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_id)


def request_id_of(request: Request) -> Optional[str]:
    return getattr(request.state, "request_id", None)


def _code_for(error: KasbBookError) -> str:
    """A stable machine name: the class's own `code`, or its name in snake_case."""
    explicit = getattr(error, "code", None)
    if explicit:
        return explicit
    return re.sub(r"(?<!^)(?=[A-Z])", "_", type(error).__name__).lower()


def _body(request: Request, detail: Any, code: str, message: str,
          fields: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message,
                             "request_id": request_id_of(request)}
    if fields is not None:
        error["fields"] = fields
    return {"detail": detail, "error": error}


def install(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(KasbBookError)
    async def _domain_error(request: Request, error: KasbBookError) -> JSONResponse:
        status_code = getattr(error, "status_code", 400)
        message = str(error) or error.__class__.__name__
        headers: Dict[str, str] = {}
        # A throttle says when to come back (RFC 9110 `Retry-After`, seconds),
        # so a well-behaved client waits instead of guessing.
        retry_after = getattr(error, "retry_after", None)
        if retry_after is not None:
            headers["Retry-After"] = str(max(1, retry_after))
        # RFC 9110: a 401 names the scheme that would have worked.
        if status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=status_code,
            content=_body(request, message, _code_for(error), message),
            headers=headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        # Where and why, never what: FastAPI's own body echoed the submitted
        # value back, and a submitted value can be a password or a key.
        fields = [
            {
                "loc": ".".join(str(part) for part in item.get("loc", ())),
                "code": item.get("type", "invalid"),
                "message": item.get("msg", ""),
            }
            for item in error.errors()
        ]
        detail = [{"loc": list(item.get("loc", ())), "msg": item.get("msg", ""),
                   "type": item.get("type", "")} for item in error.errors()]
        return JSONResponse(
            status_code=422,
            content=_body(request, detail, "invalid_request",
                          "the request does not match what this endpoint accepts", fields),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        message = error.detail if isinstance(error.detail, str) else "request refused"
        return JSONResponse(
            status_code=error.status_code,
            content=_body(request, error.detail, _HTTP_CODES.get(error.status_code,
                          f"http_{error.status_code}"), message),
            headers=getattr(error, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, error: Exception) -> JSONResponse:
        # Logged in full, reported as nothing. An exception message can carry a
        # query, a path or a value from someone else's account. The request id
        # is the one thing worth giving back: it is what finds this line.
        request_id = request_id_of(request)
        logger.exception("unhandled error on %s %s [request %s]",
                         request.method, request.url.path, request_id)
        message = "something went wrong on our side"
        return JSONResponse(
            status_code=500,
            content=_body(request, message, "internal_error", message),
            # Answered outside the request-id middleware, so set here.
            headers={HEADER: request_id} if request_id else None,
        )
