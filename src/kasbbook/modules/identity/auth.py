"""Issuing, rotating and revoking credentials.

Three kinds, deliberately different:

  * An **access token** is a signed JWT that nothing looks up. It is cheap to
    check and impossible to revoke, so it is short-lived.
  * A **refresh token** is a random secret stored as a digest. It is looked up
    on every use, so it *can* be revoked — which is the whole reason it exists.
  * An **API key** belongs to a program rather than a person. It does not
    expire on its own, because a nightly job should not stop at 3am.

The rotation rule is the part worth reading. Every refresh mints a new token and
revokes the one it came from. If a token that has already been exchanged shows
up again, two parties hold it, and there is no way to tell which one is the
thief — so the entire family is revoked and both are logged out. Being signed
out is a much smaller harm than the alternative.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import KasbBookError, NotFound
from ...shared.security import (
    is_expired,
    new_token,
    token_digest,
    utcnow,
)
from .models import ApiKey, AuditEvent, RefreshToken, User

ALGORITHM = "HS256"

# Long enough that a screen does not expire mid-form, short enough that a
# stolen one is worth little. Revocation happens at the refresh, not here.
ACCESS_MINUTES = 30
REFRESH_DAYS = 30

# Kept in the clear so a key can be recognised in a list without being produced.
KEY_PREFIX_LENGTH = 8


class AuthError(KasbBookError):
    status_code = 401


class TokenReused(AuthError):
    """A refresh token was presented twice. Someone has a copy."""


@dataclass(frozen=True)
class TokenPair:
    """What a login returns. The refresh token is shown once and never stored."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


@dataclass(frozen=True)
class IssuedApiKey:
    key: str
    record: ApiKey


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        secret_key: str,
        access_minutes: int = ACCESS_MINUTES,
        refresh_days: int = REFRESH_DAYS,
    ) -> None:
        if not secret_key:
            raise RuntimeError("an empty signing key signs nothing")
        self.session = session
        self.secret_key = secret_key
        self.access_minutes = access_minutes
        self.refresh_days = refresh_days

    # ------------------------------------------------------ access tokens
    def mint_access_token(self, user: User) -> str:
        now = utcnow()
        payload = {
            "sub": str(user.id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self.access_minutes)).timestamp()),
            "typ": "access",
            # Which generation this was minted under. See User.token_generation.
            "gen": user.token_generation,
        }
        return jwt.encode(payload, self.secret_key, algorithm=ALGORITHM)

    async def user_for_access_token(self, token: str) -> User:
        """The account behind a bearer token, or an error saying why not.

        Everything an access token has to satisfy is here rather than at the
        edge, so the answer cannot differ between callers: valid signature, not
        expired, the right type, an active account, and issued after that
        account's cutoff.
        """
        payload = self._decode(token)
        try:
            user_id = uuid.UUID(payload["sub"])
        except (KeyError, ValueError):
            raise AuthError("invalid token") from None

        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise AuthError("this account is not active")

        # A token from before the last "sign out everywhere" carries an older
        # generation. Tokens minted before this column existed carry none, and
        # default to 0 — the same value every untouched account has.
        if payload.get("gen", 0) != user.token_generation:
            raise AuthError("this session has ended; sign in again")

        return user

    def _decode(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise AuthError("this session has expired; sign in again") from None
        except jwt.InvalidTokenError:
            raise AuthError("invalid token") from None

        # A refresh token is also a string; it must not be usable as a bearer.
        if payload.get("typ") != "access":
            raise AuthError("invalid token")
        return payload

    def read_access_token(self, token: str) -> uuid.UUID:
        """The user id inside a valid token, without loading the account."""
        try:
            return uuid.UUID(self._decode(token)["sub"])
        except (KeyError, ValueError):
            raise AuthError("invalid token") from None

    # ----------------------------------------------------- refresh tokens
    async def issue_pair(
        self,
        user: User,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        family_id: Optional[uuid.UUID] = None,
    ) -> TokenPair:
        raw = new_token()
        record = RefreshToken(
            user_id=user.id,
            token_digest=token_digest(raw),
            family_id=family_id or uuid.uuid4(),
            expires_at=utcnow() + timedelta(days=self.refresh_days),
            user_agent=(user_agent or "")[:200] or None,
            ip_address=(ip_address or "")[:45] or None,
        )
        self.session.add(record)
        await self.session.flush()

        return TokenPair(
            access_token=self.mint_access_token(user),
            refresh_token=raw,
            expires_in=self.access_minutes * 60,
        )

    async def _find_refresh(self, raw: str) -> RefreshToken:
        stmt = select(RefreshToken).where(RefreshToken.token_digest == token_digest(raw))
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        if record is None:
            raise AuthError("unknown refresh token")
        return record

    async def refresh(
        self,
        raw: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenPair:
        """Exchange a refresh token for a new pair, and burn the old one."""
        record = await self._find_refresh(raw)

        if not record.is_open:
            # Already exchanged or already revoked. Either way a second party
            # holds it, and there is no way to know which one is asking.
            await self.revoke_family(record.family_id)
            await self._audit(record.user_id, "auth.token_reused")

            # Committed here, deliberately, before the error is raised. This is
            # the one place a service commits its own work: the request is about
            # to fail, the caller rolls back on failure, and a rollback would
            # undo the revocation — leaving the stolen family alive and the
            # detection doing nothing at all.
            await self.session.commit()

            raise TokenReused(
                "this session was signed out because the same credential was used "
                "twice. Sign in again."
            )

        if is_expired(record.expires_at):
            record.revoked_at = utcnow()
            await self.session.flush()
            raise AuthError("this session has expired; sign in again")

        user = await self.session.get(User, record.user_id)
        if user is None or not user.is_active:
            raise AuthError("this account is not active")

        pair = await self.issue_pair(user, user_agent, ip_address, family_id=record.family_id)

        replacement = (
            await self.session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_digest == token_digest(pair.refresh_token)
                )
            )
        ).scalar_one()
        record.revoked_at = utcnow()
        record.replaced_by_id = replacement.id
        await self.session.flush()
        return pair

    async def revoke_refresh(self, raw: str) -> None:
        """Sign out one session. An unknown token is not an error — it is signed out."""
        try:
            record = await self._find_refresh(raw)
        except AuthError:
            return
        if record.is_open:
            record.revoked_at = utcnow()
            await self.session.flush()

    async def revoke_family(self, family_id: uuid.UUID) -> int:
        """Kill every token descended from one login."""
        stmt = select(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
        )
        records = (await self.session.execute(stmt)).scalars().all()
        for record in records:
            record.revoked_at = utcnow()
        await self.session.flush()
        return len(records)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Sign out everywhere, and mean it now rather than in half an hour.

        Revoking the refresh tokens alone leaves every already-issued access
        token working until it expires. Somebody signing out because they think
        a credential leaked is not asking for a thirty-minute grace period for
        whoever took it, so the cutoff moves too.
        """
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        records = (await self.session.execute(stmt)).scalars().all()
        for record in records:
            record.revoked_at = utcnow()

        user = await self.session.get(User, user_id)
        if user is not None:
            user.token_generation += 1

        await self.session.flush()
        await self._audit(user_id, "auth.signed_out_everywhere")
        return len(records)

    async def sessions(self, user_id: uuid.UUID) -> Sequence[RefreshToken]:
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .order_by(RefreshToken.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    # ---------------------------------------------------------- api keys
    async def issue_api_key(
        self, user_id: uuid.UUID, name: str, expires_in_days: Optional[int] = None
    ) -> IssuedApiKey:
        raw = f"kb_{new_token(24)}"
        record = ApiKey(
            user_id=user_id,
            name=(name or "").strip()[:80] or "unnamed",
            token_digest=token_digest(raw),
            prefix=raw[:KEY_PREFIX_LENGTH],
            expires_at=(
                utcnow() + timedelta(days=expires_in_days) if expires_in_days else None
            ),
        )
        self.session.add(record)
        await self.session.flush()
        await self._audit(user_id, "apikey.created", subject=record.name)
        return IssuedApiKey(key=raw, record=record)

    async def user_for_api_key(self, raw: str) -> Optional[User]:
        stmt = select(ApiKey).where(ApiKey.token_digest == token_digest(raw))
        record = (await self.session.execute(stmt)).scalar_one_or_none()

        if record is None or not record.is_open or is_expired(record.expires_at):
            return None

        user = await self.session.get(User, record.user_id)
        if user is None or not user.is_active:
            return None

        record.last_used_at = utcnow()
        await self.session.flush()
        return user

    async def list_api_keys(self, user_id: uuid.UUID) -> Sequence[ApiKey]:
        stmt = (
            select(ApiKey)
            .where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def revoke_api_key(self, user_id: uuid.UUID, key_id: uuid.UUID) -> None:
        record = await self.session.get(ApiKey, key_id)
        if record is None or record.user_id != user_id:
            # Not saying which keeps this from being an oracle for other
            # accounts' key ids.
            raise NotFound("api key")

        record.revoked_at = utcnow()
        await self.session.flush()
        await self._audit(user_id, "apikey.revoked", subject=record.name)

    async def _audit(
        self, user_id: Optional[uuid.UUID], action: str, subject: Optional[str] = None
    ) -> None:
        self.session.add(AuditEvent(user_id=user_id, action=action, subject=subject))
