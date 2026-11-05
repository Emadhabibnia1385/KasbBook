"""Signing in to the web panel with a messenger instead of a password.

Three calls, in the order a browser makes them: `start` returns a link into the
bot, `poll` waits for the bot to approve it, and `telegram/webapp` is the
shortcut when the panel is already open inside Telegram as a Mini App and the
messenger has vouched for the person before they ever arrived.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import Field

from ...modules.identity.models import Provider
from ...modules.identity.service import IdentityService
from ...modules.identity.weblogin import Outcome, WebLoginService, verify_webapp_init_data
from ...shared.errors import ValidationError
from ..deps import AuthDep, LimiterDep, SessionDep, SettingsDep, client_fingerprint
from ..schemas import Model, TokenResponse
from .auth import TooManyAttempts, _enforce

router = APIRouter(prefix="/auth/telegram", tags=["auth"])

START_LIMIT, START_WINDOW = 10, 3600
# A browser asks every couple of seconds for the five minutes a link lives.
POLL_LIMIT, POLL_WINDOW = 180, 300
WEBAPP_LIMIT, WEBAPP_WINDOW = 20, 60

__all__ = ["router", "TooManyAttempts"]


class StartLoginResponse(Model):
    poll_secret: str
    deep_link: str
    expires_at: str


class PollRequest(Model):
    poll_secret: str = Field(min_length=1, max_length=200)


class PollResponse(Model):
    status: str
    tokens: Optional[TokenResponse] = None


class WebAppRequest(Model):
    init_data: str = Field(min_length=1, max_length=4096)


@router.post("/start", response_model=StartLoginResponse, status_code=201)
async def start(request: Request, session: SessionDep, settings: SettingsDep,
                limiter: LimiterDep) -> StartLoginResponse:
    username = settings.telegram_bot_username
    if not username:
        raise ValidationError("ورود با تلگرام روی این سرور پیکربندی نشده است.")
    ip = client_fingerprint(request)
    await _enforce(limiter, f"weblogin:start:{ip}", START_LIMIT, START_WINDOW)
    issued = await WebLoginService(session).start(ip, request.headers.get("user-agent"))
    return StartLoginResponse(
        poll_secret=issued.poll_secret,
        deep_link=f"https://t.me/{username}?start=wl_{issued.token}",
        expires_at=issued.expires_at.isoformat(),
    )


@router.post("/poll", response_model=PollResponse)
async def poll(body: PollRequest, request: Request, session: SessionDep, auth: AuthDep,
               limiter: LimiterDep) -> PollResponse:
    ip = client_fingerprint(request)
    await _enforce(limiter, f"weblogin:poll:{ip}", POLL_LIMIT, POLL_WINDOW)
    outcome, user = await WebLoginService(session).collect(body.poll_secret)
    if outcome is not Outcome.APPROVED:
        return PollResponse(status=outcome.value)
    pair = await auth.issue_pair(
        user, user_agent=request.headers.get("user-agent"), ip_address=ip
    )
    return PollResponse(status=outcome.value, tokens=TokenResponse(**pair.__dict__))


@router.post("/webapp", response_model=TokenResponse)
async def webapp(body: WebAppRequest, request: Request, session: SessionDep,
                 auth: AuthDep, settings: SettingsDep, limiter: LimiterDep) -> TokenResponse:
    ip = client_fingerprint(request)
    await _enforce(limiter, f"weblogin:webapp:{ip}", WEBAPP_LIMIT, WEBAPP_WINDOW)
    person = verify_webapp_init_data(body.init_data, settings.telegram_token or "")
    if person is None:
        raise ValidationError("اطلاعات ورود تلگرام معتبر نیست؛ برنامه را دوباره از ربات باز کن.")
    identities = IdentityService(session)
    external_id = str(person["id"])
    user = await identities.user_for_identity(Provider.TELEGRAM, external_id)
    if user is None:
        full = " ".join(p for p in (person.get("first_name"), person.get("last_name")) if p)
        user = await identities.create_account_from_messenger(
            Provider.TELEGRAM, external_id, display_name=full or None,
            external_username=person.get("username"),
        )
    pair = await auth.issue_pair(
        user, user_agent=request.headers.get("user-agent"), ip_address=ip
    )
    return TokenResponse(**pair.__dict__)
