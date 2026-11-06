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

from ..rates.board import RateSource
from ..rates.fiat import OpenErRates
from ..rates.swapwallet import SwapWalletRates
from ..shared.database import Database
from ..shared.settings import Settings
from . import errors, web_static
from .ratelimit import MemoryRateLimiter, RateLimiter
from .routers import (
    analytics,
    auth,
    books,
    currencies,
    everything,
    health,
    identities,
    invitations,
    market,
    payroll,
    planning,
    recurring,
    reports,
    webhooks,
    weblogin,
)

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
    rates: Optional[RateSource] = None,
    fiat: Optional[object] = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # uvicorn configures its own loggers and leaves the root alone, so an
        # application logger inherits WARNING and every logger.info in this
        # package is discarded. That was true from the first day the API ran:
        # errors appeared because they clear WARNING, and nothing else did.
        #
        # Only when nothing has configured logging already, so a host that has
        # its own arrangement keeps it.
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=getattr(logging, resolved.log_level.upper(), logging.INFO),
                format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            )
        # These log full URLs at INFO, and a bot API URL contains the token.
        for noisy in ("httpx", "httpcore"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        app.state.settings = resolved
        app.state.database = database or Database(resolved.database_url)
        app.state.limiter = limiter or await build_limiter(resolved)
        # The bot's construction exactly (apps/bot/runner.py): the public
        # endpoint, no key. One instance per process so its minute of cache is
        # shared by every request, which is what keeps a polling panel from
        # becoming a polling provider.
        app.state.rates = rates or SwapWalletRates()
        app.state.fiat = fiat or OpenErRates()

        # Empty unless this process is meant to receive updates, and an empty
        # map means every webhook path answers 404 — so a misconfigured deploy
        # is a provider seeing 404s rather than an open door.
        app.state.adapters = {}
        app.state.webhook_paths = {}
        app.state.state_store = None

        if resolved.uses_webhook:
            # Serving updates means the API does bot work: it needs the
            # provider's adapter to parse and reply, and the same conversation
            # state the poller would have used — Redis, or nothing shared at
            # all if Redis is absent, which is worth knowing before a
            # half-finished flow disappears between two workers.
            from apps.bot.runner import build_adapter, build_state_store

            resolved.require_webhook()
            app.state.adapters = {resolved.provider.value: build_adapter(resolved)}
            app.state.webhook_paths = {
                resolved.provider.value: resolved.webhook_path_secret
            }
            app.state.state_store = await build_state_store(resolved)
            logger.info("serving %s updates by webhook", resolved.provider.value)

        try:
            yield
        finally:
            for adapter in app.state.adapters.values():
                await adapter.aclose()
            if database is None:
                await app.state.database.dispose()

    app = FastAPI(
        title="KasbBook API",
        description=DESCRIPTION,
        version=health.VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
        # `<tag>_<function>` rather than the default that appends the path and
        # method: the web panel's generated client takes its function names
        # from these, and `books_list_books` reads better than
        # `list_books_api_v1_books_get`.
        generate_unique_id_function=lambda route: f"{route.tags[0]}_{route.name}" if route.tags else route.name,
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
    app.include_router(invitations.router, prefix=api)
    app.include_router(currencies.router, prefix=api)
    app.include_router(books.router, prefix=api)
    app.include_router(everything.router, prefix=api)
    app.include_router(market.router, prefix=api)
    app.include_router(reports.router, prefix=api)
    app.include_router(analytics.router, prefix=api)
    app.include_router(planning.router, prefix=api)
    app.include_router(payroll.router, prefix=api)
    app.include_router(recurring.router, prefix=api)
    app.include_router(weblogin.router, prefix=api)
    app.include_router(webhooks.router, prefix=api)
    # Last, so it only ever answers what nothing above claimed.
    web_static.mount_web(app)
    return app
