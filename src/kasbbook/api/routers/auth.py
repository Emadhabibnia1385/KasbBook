"""Registering, signing in, staying signed in, and signing out.

The rate limits here are not decoration. Without them the login route is an
offline password-guessing oracle that answers as fast as the network allows.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Request, status

from dataclasses import replace

from ...modules.identity.auth import AuthError
from ...modules.identity.service import IdentityService
from ...shared.security import password_reset_code, verify_password
from ...shared.errors import ValidationError
from ..deps import (
    AuthDep,
    CurrentUser,
    LimiterDep,
    Person,
    Registered,
    SessionDep,
    SettingsDep,
    client_fingerprint,
)
from ..schemas import (
    ApiKeyCreated,
    ContactRequest,
    DeletionPreviewResponse,
    ApiKeyRequest,
    ApiKeyResponse,
    CloseAccountRequest,
    LoginRequest,
    PasswordRequest,
    ProfileRequest,
    RefreshRequest,
    RegisterRequest,
    ResetCodeResponse,
    SessionResponse,
    TokenResponse,
    UsernameRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Five attempts a minute per address. A person who has genuinely forgotten
# their password tries three times and stops; a script does not.
LOGIN_LIMIT, LOGIN_WINDOW = 5, 60
REGISTER_LIMIT, REGISTER_WINDOW = 3, 3600


class TooManyAttempts(AuthError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        # Read by the error handler to set the `Retry-After` header.
        self.retry_after = retry_after


async def _enforce(limiter, key: str, limit: int, window: int) -> None:
    allowed, retry_after = await limiter.hit(key, limit, window)
    if not allowed:
        raise TooManyAttempts(
            f"too many attempts; try again in {retry_after} seconds", retry_after
        )


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
        with_book=True,
    )
    pair = await auth.issue_pair(
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_fingerprint(request),
    )
    return TokenResponse(**pair.__dict__)


GUEST_LIMIT, GUEST_WINDOW = 10, 3600


@router.post("/guest", response_model=TokenResponse, status_code=201)
async def guest(
    request: Request, session: SessionDep, auth: AuthDep, limiter: LimiterDep
) -> TokenResponse:
    """Let someone look around without an account. Signing out removes everything."""
    fingerprint = client_fingerprint(request)
    await _enforce(limiter, f"guest:{fingerprint}", GUEST_LIMIT, GUEST_WINDOW)
    user = await IdentityService(session).create_guest()
    pair = await auth.issue_pair(
        user, user_agent=request.headers.get("user-agent"), ip_address=fingerprint
    )
    return TokenResponse(**pair.__dict__)


DEMO_LIMIT, DEMO_WINDOW = 4, 3600


@router.post("/demo", response_model=TokenResponse, status_code=201)
async def demo(
    request: Request, session: SessionDep, auth: AuthDep, limiter: LimiterDep
) -> TokenResponse:
    """A guest account with four books of a year's worth of made-up data, to see the whole panel.

    Like any guest it is removed when the visitor signs out (and after a day), and so are the made-up
    colleagues. Making it writes a thousand rows, so it is limited harder than a plain guest.
    """
    from ...modules.demo.seed import seed_demo

    fingerprint = client_fingerprint(request)
    await _enforce(limiter, f"demo:{fingerprint}", DEMO_LIMIT, DEMO_WINDOW)
    await IdentityService(session).purge_guests()
    user, _ = await seed_demo(session)
    pair = await auth.issue_pair(
        user, user_agent=request.headers.get("user-agent"), ip_address=fingerprint
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
async def logout(body: RefreshRequest, auth: AuthDep, session: SessionDep) -> None:
    """Sign out this session. An unknown token is not an error; it is signed out."""
    owner = await auth.owner_of(body.refresh_token)
    await auth.revoke_refresh(body.refresh_token)
    if owner is not None and owner.is_guest:
        await IdentityService(session).delete_account(owner.id)


@router.post("/logout-everywhere", status_code=204)
async def logout_everywhere(user: Person, auth: AuthDep, session: SessionDep) -> None:
    await auth.revoke_all_for_user(user.id)
    if user.is_guest:
        await IdentityService(session).delete_account(user.id)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/sessions", response_model=List[SessionResponse])
async def sessions(user: Person, auth: AuthDep) -> List[SessionResponse]:
    """Where this account is currently signed in."""
    return [SessionResponse.model_validate(row) for row in await auth.sessions(user.id)]


@router.delete("/sessions/{session_id}", status_code=204)
async def sign_out_session(session_id: uuid.UUID, user: Person, auth: AuthDep) -> None:
    """Sign out one device, leaving the others as they are."""
    await auth.revoke_session(user.id, session_id)


# -------------------------------------------------------------- account
@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: ProfileRequest, user: Person, session: SessionDep
) -> UserResponse:
    updated = await IdentityService(session).update_profile(
        user.id, display_name=body.display_name,
        timezone=body.timezone, locale=body.locale,
        digest_enabled=body.digest_enabled, digest_hour=body.digest_hour,
        reminder_days=body.reminder_days,
    )
    return UserResponse.model_validate(updated)


@router.put("/me/contact", response_model=UserResponse)
async def set_contact(
    body: ContactRequest, user: Registered, session: SessionDep
) -> UserResponse:
    """The address or number this account can be reached and recovered by."""
    updated = await IdentityService(session).set_contact(
        user.id, email=body.email, phone=body.phone
    )
    return UserResponse.model_validate(updated)


@router.put("/me/username", response_model=UserResponse)
async def set_username(
    body: UsernameRequest, user: Person, session: SessionDep
) -> UserResponse:
    """The name the web login takes next to the password."""
    updated = await IdentityService(session).set_username(user.id, body.username)
    return UserResponse.model_validate(updated)


RESET_CODE_LIMIT, RESET_CODE_WINDOW = 3, 600
RESET_TRY_LIMIT = 10


async def _send_code(request: Request, settings, identity, text: str, buttons) -> None:
    """Hand a message to the messenger the identity belongs to, using the running bot's adapter."""
    from ...adapters.base import OutgoingMessage
    from ...bot.delivery import deliver_notifications

    adapter = getattr(request.app.state, "adapters", {}).get(identity.provider.value)
    temporary = adapter is None
    if temporary:
        from apps.bot.runner import build_adapter

        selected = replace(settings, provider=identity.provider)
        if not selected.token:
            raise ValidationError("ارسال کد در این پیام‌رسان پیکربندی نشده است.")
        adapter = build_adapter(selected)
    try:
        notification = OutgoingMessage(identity.external_id, text, buttons)
        await deliver_notifications(adapter, OutgoingMessage("", "", notifications=[notification]))
    finally:
        if temporary:
            await adapter.aclose()


@router.post("/me/password/reset-code", response_model=ResetCodeResponse)
async def send_password_reset_code(
    request: Request, user: Person, session: SessionDep, settings: SettingsDep, limiter: LimiterDep
) -> ResetCodeResponse:
    """For someone who has forgotten the current password: a code goes to a messenger they already own."""
    from ...bot.screens import password_reset_proof

    await _enforce(limiter, f"pwreset:send:{user.id}", RESET_CODE_LIMIT, RESET_CODE_WINDOW)
    if not user.password_hash:
        raise ValidationError("این حساب هنوز رمزی ندارد؛ لازم نیست کدی بفرستی.")
    if not settings.api_secret_key:
        raise ValidationError("ارسال کد پیکربندی نشده است.")
    identities = [
        row for row in await IdentityService(session).list_identities(user.id)
        if row.provider.value != "web"
    ]
    if not identities:
        raise ValidationError("پیام‌رسانی وصل نیست؛ اول یکی را وصل کن تا کد به آن برود.")
    # The one used most recently is the one the person is most likely looking at.
    chosen = max(identities, key=lambda row: row.last_seen_at or row.linked_at)
    code = password_reset_code(settings.api_secret_key, user.id, user.password_hash)
    text, buttons = password_reset_proof(code)
    await _send_code(request, settings, chosen, text, buttons)
    return ResetCodeResponse(sent_to=chosen.provider.value)


@router.put("/me/password", status_code=204)
async def set_password(
    body: PasswordRequest,
    user: Person,
    session: SessionDep,
    auth: AuthDep,
    settings: SettingsDep,
    limiter: LimiterDep,
) -> None:
    """Set or change the password, and end every session including this one.

    Somebody changing a password because they fear it leaked expects the
    sessions to go with it; leaving them alive would defeat the point.
    """
    if body.reset_code:
        # A code is guessable in principle, so tries are counted like login attempts.
        await _enforce(limiter, f"pwreset:try:{user.id}", RESET_TRY_LIMIT, RESET_CODE_WINDOW)
    await IdentityService(session).set_password(
        user.id,
        body.new_password,
        current_password=body.current_password,
        reset_code=body.reset_code,
        secret=settings.api_secret_key,
    )
    await auth.revoke_all_for_user(user.id)


@router.get("/me/deletion-preview", response_model=DeletionPreviewResponse)
async def deletion_preview(
    user: CurrentUser, session: SessionDep
) -> DeletionPreviewResponse:
    """What closing this account would destroy, and what would stop it."""
    preview = await IdentityService(session).deletion_preview(user.id)
    return DeletionPreviewResponse(
        books_to_delete=preview.books_to_delete,
        books_to_hand_over=preview.books_to_hand_over,
        other_books_left=preview.other_books_left,
        blocked=preview.blocked,
    )


@router.delete("/me", status_code=204)
async def close_account(
    body: CloseAccountRequest, user: Person, session: SessionDep
) -> None:
    """Close the account. There is no undo, and no grace period.

    Books nobody else is on go with it. Books shared with other people are not
    this account's to destroy, so the request is refused until they are handed
    over — `GET /auth/me/deletion-preview` names them.
    """
    identity = IdentityService(session)

    if user.password_hash:
        if not body.password or not verify_password(body.password, user.password_hash):
            raise AuthError("the password does not match")

    await identity.delete_account(user.id)


# ------------------------------------------------------------- api keys
@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyRequest, user: Registered, auth: AuthDep
) -> ApiKeyCreated:
    """Issue a key for a program. This is the only response that contains it."""
    issued = await auth.issue_api_key(user.id, body.name, body.expires_in_days)
    return ApiKeyCreated(
        **ApiKeyResponse.model_validate(issued.record).model_dump(), key=issued.key
    )


@router.get("/api-keys", response_model=List[ApiKeyResponse])
async def list_api_keys(user: Person, auth: AuthDep) -> List[ApiKeyResponse]:
    return [ApiKeyResponse.model_validate(row) for row in await auth.list_api_keys(user.id)]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: uuid.UUID, user: Person, auth: AuthDep) -> None:
    await auth.revoke_api_key(user.id, key_id)
