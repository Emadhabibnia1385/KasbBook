"""Signing in to the web by asking a messenger to vouch for the browser.

No password and no widget that needs a domain registered with the provider:
the browser gets a link into the bot, the person taps it, the bot asks "was
this you?", and the browser collects a session once the answer is yes.
"""

from __future__ import annotations

import enum
import hmac
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound
from ...shared.security import expires_in, is_expired, new_token, token_digest, utcnow
from .models import AuditEvent, User, WebLoginChallenge

# Long enough to open the bot and tap twice, short enough that a link left in a
# chat is worth nothing by the time anyone finds it.
LIFETIME_MINUTES = 5


class Outcome(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass(frozen=True)
class StartedLogin:
    token: str          # goes into the deep link
    poll_secret: str    # stays in the browser
    expires_at: object


class WebLoginService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(self, ip: Optional[str], agent: Optional[str]) -> StartedLogin:
        token, poll = new_token(18), new_token(32)
        row = WebLoginChallenge(
            token_digest=token_digest(token), poll_digest=token_digest(poll),
            requester_ip=(ip or "")[:64] or None, requester_agent=(agent or "")[:200] or None,
            expires_at=expires_in(LIFETIME_MINUTES),
        )
        self.session.add(row)
        await self.session.flush()
        return StartedLogin(token, poll, row.expires_at)

    async def _open(self, token: str) -> WebLoginChallenge:
        row = await self.session.scalar(select(WebLoginChallenge).where(
            WebLoginChallenge.token_digest == token_digest(token)
        ).with_for_update())
        if (row is None or is_expired(row.expires_at) or row.approved_at is not None
                or row.denied_at is not None or row.consumed_at is not None):
            # One answer for unknown, stale and already-used: a link tells
            # nobody which of those it was.
            raise NotFound("این لینک ورود منقضی شده یا قبلاً استفاده شده است.")
        return row

    async def describe(self, token: str) -> WebLoginChallenge:
        return await self._open(token)

    async def approve(self, token: str, user_id: uuid.UUID) -> None:
        row = await self._open(token)
        row.user_id, row.approved_at = user_id, utcnow()
        self.session.add(AuditEvent(user_id=user_id, action="identity.web_login_approved",
                                    subject=str(row.id), detail=row.requester_ip))

    async def deny(self, token: str, user_id: uuid.UUID) -> None:
        row = await self._open(token)
        row.denied_at = utcnow()
        # "It wasn't me" is the one signal that someone is trying; keep it.
        self.session.add(AuditEvent(user_id=user_id, action="identity.web_login_denied",
                                    subject=str(row.id), detail=row.requester_ip))

    async def collect(self, poll_secret: str) -> tuple[Outcome, Optional[User]]:
        """What the browser learns. A session is handed over exactly once."""
        row = await self.session.scalar(select(WebLoginChallenge).where(
            WebLoginChallenge.poll_digest == token_digest(poll_secret)
        ).with_for_update())
        if row is None or row.consumed_at is not None:
            return Outcome.EXPIRED, None
        if row.denied_at is not None:
            return Outcome.DENIED, None
        if row.approved_at is None:
            return (Outcome.EXPIRED if is_expired(row.expires_at) else Outcome.PENDING), None
        user = await self.session.get(User, row.user_id)
        if user is None or not user.is_active:
            return Outcome.EXPIRED, None
        row.consumed_at = utcnow()
        return Outcome.APPROVED, user


def verify_webapp_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> Optional[dict]:
    """The Telegram user inside Mini App `initData`, or None if it is not genuine.

    Telegram signs the launch parameters with a key derived from the bot token;
    anything that does not verify, or is old enough to have been lifted from a
    log, is refused. The check string is the sorted `key=value` lines without
    `hash`, as Telegram documents for Mini Apps.
    """
    import hashlib
    import json
    import time
    from urllib.parse import parse_qsl

    if not init_data or not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > max_age_seconds:
            return None
        user = json.loads(pairs["user"])
    except (KeyError, ValueError):
        return None
    return user if isinstance(user, dict) and "id" in user else None
