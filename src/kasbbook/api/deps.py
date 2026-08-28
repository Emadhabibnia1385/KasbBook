"""What a route can ask for.

The important one is `current_user`. It accepts a bearer token or an API key,
resolves either to the same `User`, and every protected route depends on it —
so there is exactly one place that decides whether a request is authenticated.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..modules.identity.auth import AuthError, AuthService
from ..modules.identity.models import User
from ..shared.database import Database
from ..shared.settings import Settings
from .ratelimit import RateLimiter


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.limiter


async def get_session(request: Request):
    """One session per request, committed on the way out.

    Committing here rather than in each route means a route cannot forget, and
    an exception rolls the whole request back — including the half of it that
    had already succeeded.
    """
    database: Database = request.app.state.database
    async for session in database.session():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
LimiterDep = Annotated[RateLimiter, Depends(get_limiter)]


def get_auth(session: SessionDep, settings: SettingsDep) -> AuthService:
    return AuthService(
        session,
        settings.require_secret_key(),
        access_minutes=settings.access_token_minutes,
        refresh_days=settings.refresh_token_days,
    )


AuthDep = Annotated[AuthService, Depends(get_auth)]


async def current_user(
    auth: AuthDep,
    authorization: Annotated[Optional[str], Header()] = None,
    x_api_key: Annotated[Optional[str], Header()] = None,
) -> User:
    """The account behind this request, however it identified itself.

    A person sends a bearer token; a program sends an API key. Both end up as
    the same `User`, so no route below has to care which arrived.
    """
    if x_api_key:
        user = await auth.user_for_api_key(x_api_key)
        if user is None:
            raise AuthError("invalid API key")
        return user

    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("sign in first")

    return await auth.user_for_access_token(authorization.split(" ", 1)[1].strip())


CurrentUser = Annotated[User, Depends(current_user)]


def client_fingerprint(request: Request) -> str:
    """Who to count rate-limited attempts against.

    The direct peer, unless a proxy we run has said otherwise. `X-Forwarded-For`
    is trusted only when `KASBBOOK_TRUSTED_PROXY` says there is one in front,
    because otherwise anyone can set it and rate limiting becomes decorative.
    """
    import os

    if os.environ.get("KASBBOOK_TRUSTED_PROXY"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
