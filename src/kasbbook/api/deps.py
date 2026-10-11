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
from ..shared.errors import PermissionDenied
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


async def current_person(
    user: CurrentUser,
    x_api_key: Annotated[Optional[str], Header()] = None,
) -> User:
    """The account, but only when a person signed in — never a program's key.

    A key is for a program that reads and writes books. Managing the account
    is the person's: a key that could mint keys made revoking a leaked one
    pointless, because the holder had already minted its successor; and a key
    that could change the contact, link a messenger or close a passwordless
    account was the account. A valid key is told 403, an invalid one is still
    401 — `CurrentUser` has already refused it.
    """
    if x_api_key:
        raise PermissionDenied("an API key cannot manage the account; sign in as a person")
    return user


Person = Annotated[User, Depends(current_person)]


def client_fingerprint(request: Request) -> str:
    """Who to count rate-limited attempts against.

    The direct peer, unless a proxy we run has said otherwise. `X-Forwarded-For`
    is trusted only when `KASBBOOK_TRUSTED_PROXY` says there is one in front,
    because otherwise anyone can set it and rate limiting becomes decorative.

    Behind that proxy the **right-most** hop is used. A proxy such as nginx
    appends the address it actually saw to whatever header the client sent, so
    everything to the left is the client's own claim: reading the left-most hop
    let a caller pick a fresh "address" per request and never be throttled.
    This assumes exactly one proxy; with a chain, only the last hop (the one
    our own proxy appended) is trustworthy, which is still the one used.
    """
    import os

    if os.environ.get("KASBBOOK_TRUSTED_PROXY"):
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"
