"""The application factory.

A factory rather than a module-level `app` so tests can build one against a
throwaway database without the import itself reaching for Postgres. Everything
shared lives on `app.state`, created once at startup and disposed at shutdown.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..shared.database import Database
from ..shared.settings import Settings
from . import errors
from .ratelimit import MemoryRateLimiter, RateLimiter
from .routers import auth, books, health, identities, planning, reports, webhooks

logger = logging.getLogger("kasbbook.api")

DESCRIPTION = """
KasbBook's HTTP API.

The same application services the bot uses. Every permission check happens
below this layer, so an endpoint cannot be more permissive than the equivalent
button in Telegram.

Money is carried as a **string**, never a JSON number: JSON has one numeric
type and it is a float, and a bookkeeping API that loses rials is not one.
"""


async def build_limiter(settings: Settings) -> RateLimiter:
    """Redis when there is one, memory otherwise — with the caveat stated."""
    if not settings.redis_url:
        logger.warning(
            "rate limiting is in-process; correct on one worker, not across several"
        )
        return MemoryRateLimiter()

    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning("REDIS_URL is set but the redis package is missing; using memory")
        return MemoryRateLimiter()

    from .ratelimit import RedisRateLimiter

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await client.ping()
    return RedisRateLimiter(client)


def create_app(
    settings: Optional[Settings] = None,
    database: Optional[Database] = None,
    limiter: Optional[RateLimiter] = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = resolved
        app.state.database = database or Database(resolved.database_url)
        app.state.limiter = limiter or await build_limiter(resolved)

        # Filled in only when this process also serves webhooks. Empty means
        # every webhook path answers 404, which is the right default.
        app.state.adapters = {}
        app.state.webhook_paths = {}
        app.state.state_store = None

        try:
            yield
        finally:
            if database is None:
                await app.state.database.dispose()

    app = FastAPI(
        title="KasbBook API",
        description=DESCRIPTION,
        version=health.VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    origins = [o.strip() for o in os.environ.get("KASBBOOK_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        # Listed explicitly, never "*": these endpoints carry credentials, and
        # a wildcard with credentials is a hole rather than a convenience.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    errors.install(app)

    api = "/api/v1"
    app.include_router(health.router)
    app.include_router(auth.router, prefix=api)
    app.include_router(identities.router, prefix=api)
    app.include_router(books.router, prefix=api)
    app.include_router(reports.router, prefix=api)
    app.include_router(planning.router, prefix=api)
    app.include_router(webhooks.router, prefix=api)
    return app
