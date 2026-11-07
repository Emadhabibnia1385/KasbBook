"""What a route can ask for.

The important one is `current_user`. It accepts a bearer token or an API key,
resolves either to the same `User`, and every protected route depends on it —
so there is exactly one place that decides whether a request is authenticated.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..modules.activity import recorder as activity
from ..modules.activity.models import VIA_API, VIA_WEB
from ..modules.identity.auth import AuthError, AuthService
from ..modules.identity.models import User
from ..shared.database import Database
from ..shared.errors import PermissionDenied
from ..shared.settings import Settings
from ..rates.board import RateSource
from .ratelimit import RateLimiter


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.limiter


def get_rates(request: Request) -> RateSource:
    return request.app.state.rates


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
        finally:
            # Whoever this request acted for is not carried into the next piece of work in this task.
            activity.clear_actor()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
LimiterDep = Annotated[RateLimiter, Depends(get_limiter)]
RatesDep = Annotated[RateSource, Depends(get_rates)]


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
        # What this request changes is logged as done through the API, on the key owner's behalf.
        activity.set_actor(user.id, VIA_API)
        return user

    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("sign in first")

    user = await auth.user_for_access_token(authorization.split(" ", 1)[1].strip())
    activity.set_actor(user.id, VIA_WEB)
    return user


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


async def current_registered(user: Person) -> User:
    """A person with a real account: not a guest, whose account is gone the moment they sign out.

    Linking a messenger, minting a key or setting a contact would tie something lasting to an account
    that is about to be deleted, so a guest is told plainly to sign in properly first.
    """
    if user.is_guest:
        raise PermissionDenied(
            "حساب مهمان ذخیره نمی‌شود؛ برای این کار با تلگرام یا نام کاربری وارد شو"
        )
    return user


Registered = Annotated[User, Depends(current_registered)]


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
