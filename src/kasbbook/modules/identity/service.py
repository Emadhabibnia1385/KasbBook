"""Account and identity-linking rules.

This is an application service: every interface — the web panel and all four
messenger adapters — goes through it. No adapter and no HTTP route decides who
an identity belongs to.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import (
    AlreadyLinked,
    IdentityTakenError,
    InvalidLinkToken,
    NotFound,
)
from ...shared.security import (
    expires_in,
    hash_password,
    is_expired,
    new_link_code,
    new_token,
    token_digest,
    utcnow,
    verify_password,
)
from .models import AuditEvent, Identity, LinkDirection, LinkToken, Provider, User

# Long enough to switch apps and paste, short enough that a leaked link is dead
# before anyone finds it.
LINK_TTL_MINUTES = 15


@dataclass(frozen=True)
class IssuedLink:
    """What the user is shown once, and never again."""

    token: str
    expires_at_iso: str
    direction: LinkDirection


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------- accounts
    async def create_user(
        self,
        display_name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        password: Optional[str] = None,
    ) -> "User":

        user = User(
            display_name=display_name,
            email=email.lower().strip() if email else None,
            phone=phone.strip() if phone else None,
            password_hash=hash_password(password) if password else None,
        )
        self.session.add(user)
        await self.session.flush()
        await self._audit(user.id, "user.created", subject=email or phone or display_name)
        return user

    async def authenticate(self, identifier: str, password: str) -> Optional["User"]:

        needle = identifier.lower().strip()
        stmt = select(User).where((User.email == needle) | (User.phone == identifier.strip()))
        user = (await self.session.execute(stmt)).scalar_one_or_none()

        if user is None or not user.password_hash or not user.is_active:
            # Same answer for "no such user" and "wrong password", so the
            # endpoint cannot be used to enumerate accounts.
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def find_by_identifier(self, identifier: str) -> Optional["User"]:
        """Look someone up the way a person would name them: email or phone.

        Used to add a colleague to a book. It returns the account without any
        credential check, so nothing that reaches this may expose more than a
        display name — knowing an address should not reveal what else it does.
        """
        needle = (identifier or "").strip()
        if not needle:
            return None

        stmt = select(User).where(
            (User.email == needle.lower()) | (User.phone == needle)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_user(self, user_id: uuid.UUID) -> "User":

        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFound(f"user {user_id}")
        return user

    # ----------------------------------------------------------- identities
    async def find_identity(self, provider: Provider, external_id: str) -> Optional[Identity]:
        stmt = select(Identity).where(
            Identity.provider == provider, Identity.external_id == str(external_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def user_for_identity(self, provider: Provider, external_id: str) -> Optional["User"]:
        identity = await self.find_identity(provider, external_id)
        return identity.user if identity else None

    async def list_identities(self, user_id: uuid.UUID) -> Sequence[Identity]:
        stmt = select(Identity).where(Identity.user_id == user_id).order_by(Identity.linked_at)
        return (await self.session.execute(stmt)).scalars().all()

    async def unlink(self, user_id: uuid.UUID, identity_id: uuid.UUID) -> None:
        identity = await self.session.get(Identity, identity_id)
        if identity is None or identity.user_id != user_id:
            # Refusing to say which of the two it was keeps this from being an
            # oracle for identity ids belonging to other accounts.
            raise NotFound("identity")

        await self.session.delete(identity)
        await self._audit(
            user_id,
            "identity.unlinked",
            subject=f"{identity.provider.value}:{identity.external_id}",
        )

    # ---------------------------------------------------------- link tokens
    async def start_link_from_web(self, user_id: uuid.UUID, provider: Provider) -> IssuedLink:
        """The account is known; we are waiting for the messenger to prove itself."""
        if provider not in (Provider.TELEGRAM, Provider.BALE, Provider.RUBIKA, Provider.EITAA):
            raise ValueError(f"{provider} is not a messenger")

        token = new_token()
        record = LinkToken(
            token_digest=token_digest(token),
            direction=LinkDirection.FROM_WEB,
            user_id=user_id,
            provider=provider,
            expires_at=expires_in(LINK_TTL_MINUTES),
        )
        self.session.add(record)
        await self.session.flush()
        await self._audit(user_id, "link.started", subject=provider.value)

        return IssuedLink(token, record.expires_at.isoformat(), LinkDirection.FROM_WEB)

    async def start_link_from_messenger(
        self,
        provider: Provider,
        external_id: str,
        external_username: Optional[str] = None,
    ) -> IssuedLink:
        """The messenger is known; we are waiting for someone to log in and claim it."""
        existing = await self.find_identity(provider, external_id)
        if existing is not None:
            raise AlreadyLinked(
                f"{provider.value}:{external_id} is already attached to an account"
            )

        code = new_link_code()
        record = LinkToken(
            token_digest=token_digest(code),
            direction=LinkDirection.FROM_MESSENGER,
            provider=provider,
            external_id=str(external_id),
            external_username=external_username,
            expires_at=expires_in(LINK_TTL_MINUTES),
        )
        self.session.add(record)
        await self.session.flush()

        return IssuedLink(code, record.expires_at.isoformat(), LinkDirection.FROM_MESSENGER)

    async def _claim(self, token: str) -> LinkToken:
        stmt = select(LinkToken).where(LinkToken.token_digest == token_digest(token))
        record = (await self.session.execute(stmt)).scalar_one_or_none()

        if record is None:
            raise InvalidLinkToken("unknown code")
        if not record.is_open:
            raise InvalidLinkToken("this code has already been used")
        if is_expired(record.expires_at):
            raise InvalidLinkToken("this code has expired")
        return record

    async def complete_link_from_messenger(
        self,
        token: str,
        provider: Provider,
        external_id: str,
        external_username: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Identity:
        """A messenger redeems a code that the web panel issued."""
        record = await self._claim(token)

        if record.direction is not LinkDirection.FROM_WEB:
            raise InvalidLinkToken("this code is not for a messenger")
        if record.provider is not provider:
            # A Telegram deep link must not be redeemable from Bale.
            raise InvalidLinkToken("this code was issued for a different messenger")

        identity = await self._attach(
            user_id=record.user_id,
            provider=provider,
            external_id=external_id,
            external_username=external_username,
            display_name=display_name,
        )
        record.consumed_at = utcnow()
        await self.session.flush()
        return identity

    async def complete_link_from_web(self, token: str, user_id: uuid.UUID) -> Identity:
        """A logged-in account redeems a code that a messenger issued."""
        record = await self._claim(token)

        if record.direction is not LinkDirection.FROM_MESSENGER:
            raise InvalidLinkToken("this code is not for the web panel")

        identity = await self._attach(
            user_id=user_id,
            provider=record.provider,
            external_id=record.external_id,
            external_username=record.external_username,
        )
        record.consumed_at = utcnow()
        await self.session.flush()
        return identity

    async def revoke_link(self, token_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> None:
        record = await self.session.get(LinkToken, token_id)
        if record is None or (user_id is not None and record.user_id != user_id):
            raise NotFound("link token")
        record.revoked_at = utcnow()
        await self.session.flush()

    # ------------------------------------------------------------- internals
    async def _attach(
        self,
        user_id: uuid.UUID,
        provider: Provider,
        external_id: str,
        external_username: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Identity:
        existing = await self.find_identity(provider, external_id)
        if existing is not None:
            if existing.user_id == user_id:
                raise AlreadyLinked("this messenger is already attached to your account")
            # The whole point of the unique constraint: an identity never moves
            # between accounts without being unlinked from the first one.
            raise IdentityTakenError(
                "this messenger account is already attached to a different KasbBook account"
            )

        identity = Identity(
            user_id=user_id,
            provider=provider,
            external_id=str(external_id),
            external_username=external_username,
            display_name=display_name,
            linked_at=utcnow(),
        )
        self.session.add(identity)
        await self.session.flush()
        await self._audit(
            user_id, "identity.linked", subject=f"{provider.value}:{external_id}"
        )
        return identity

    async def _audit(
        self,
        user_id: Optional[uuid.UUID],
        action: str,
        subject: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        self.session.add(
            AuditEvent(user_id=user_id, action=action, subject=subject, detail=detail)
        )
