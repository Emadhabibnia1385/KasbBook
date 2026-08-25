"""Registering, signing in, staying signed in, and signing out.

The rate limits here are not decoration. Without them the login route is an
offline password-guessing oracle that answers as fast as the network allows.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Request, status

from ...modules.identity.auth import AuthError
from ...modules.identity.service import IdentityService
from ...shared.errors import ValidationError
from ..deps import AuthDep, CurrentUser, LimiterDep, SessionDep, client_fingerprint
from ..schemas import (
    ApiKeyCreated,
    ApiKeyRequest,
    ApiKeyResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Five attempts a minute per address. A person who has genuinely forgotten
# their password tries three times and stops; a script does not.
LOGIN_LIMIT, LOGIN_WINDOW = 5, 60
REGISTER_LIMIT, REGISTER_WINDOW = 3, 3600


class TooManyAttempts(AuthError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


async def _enforce(limiter, key: str, limit: int, window: int) -> None:
    allowed, retry_after = await limiter.hit(key, limit, window)
    if not allowed:
        raise TooManyAttempts(f"too many attempts; try again in {retry_after} seconds")


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    session: SessionDep,
    auth: AuthDep,
    limiter: LimiterDep,
) -> TokenResponse:
    await _enforce(
        limiter, f"register:{client_fingerprint(request)}", REGISTER_LIMIT, REGISTER_WINDOW
    )

    if not body.email and not body.phone:
        raise ValidationError("an email address or a phone number is required")

    identity = IdentityService(session)
    user = await identity.create_user(
        display_name=body.display_name,
        email=body.email,
        phone=body.phone,
        password=body.password,
    )
    pair = await auth.issue_pair(
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_fingerprint(request),
    )
    return TokenResponse(**pair.__dict__)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: SessionDep,
    auth: AuthDep,
    limiter: LimiterDep,
) -> TokenResponse:
    fingerprint = client_fingerprint(request)
    # Counted per address *and* per account, so one attacker cannot lock every
    # user out by hammering, and one account cannot be hammered from a botnet.
    await _enforce(limiter, f"login:ip:{fingerprint}", LOGIN_LIMIT, LOGIN_WINDOW)
    await _enforce(limiter, f"login:id:{body.identifier.lower()}", LOGIN_LIMIT * 2, LOGIN_WINDOW)

    user = await IdentityService(session).authenticate(body.identifier, body.password)
    if user is None:
        # One message for "no such account" and "wrong password". Two would
        # turn this route into an account-enumeration tool.
        raise AuthError("the details you entered do not match an account")

    pair = await auth.issue_pair(
        user, user_agent=request.headers.get("user-agent"), ip_address=fingerprint
    )
    return TokenResponse(**pair.__dict__)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, auth: AuthDep) -> TokenResponse:
    """Trade a refresh token for a new pair. The old one dies here."""
    pair = await auth.refresh(
        body.refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_fingerprint(request),
    )
    return TokenResponse(**pair.__dict__)


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest, auth: AuthDep) -> None:
    """Sign out this session. An unknown token is not an error; it is signed out."""
    await auth.revoke_refresh(body.refresh_token)


@router.post("/logout-everywhere", status_code=204)
async def logout_everywhere(user: CurrentUser, auth: AuthDep) -> None:
    await auth.revoke_all_for_user(user.id)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/sessions", response_model=List[SessionResponse])
async def sessions(user: CurrentUser, auth: AuthDep) -> List[SessionResponse]:
    """Where this account is currently signed in."""
    return [SessionResponse.model_validate(row) for row in await auth.sessions(user.id)]


# ------------------------------------------------------------- api keys
@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyRequest, user: CurrentUser, auth: AuthDep
) -> ApiKeyCreated:
    """Issue a key for a program. This is the only response that contains it."""
    issued = await auth.issue_api_key(user.id, body.name, body.expires_in_days)
    return ApiKeyCreated(
        **ApiKeyResponse.model_validate(issued.record).model_dump(), key=issued.key
    )


@router.get("/api-keys", response_model=List[ApiKeyResponse])
async def list_api_keys(user: CurrentUser, auth: AuthDep) -> List[ApiKeyResponse]:
    return [ApiKeyResponse.model_validate(row) for row in await auth.list_api_keys(user.id)]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: uuid.UUID, user: CurrentUser, auth: AuthDep) -> None:
    await auth.revoke_api_key(user.id, key_id)
