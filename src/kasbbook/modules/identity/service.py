"""Account and identity-linking rules.

This is an application service: every interface — the web panel and all four
messenger adapters — goes through it. No adapter and no HTTP route decides who
an identity belongs to.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo
from typing import Optional, Sequence

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import (
    AlreadyLinked,
    IdentityTakenError,
    InvalidLinkToken,
    NotFound,
    ValidationError,
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
from ...shared.parsing import to_ascii_digits
from .models import AuditEvent, Identity, LinkDirection, LinkToken, Provider, User

# Long enough to switch apps and paste, short enough that a leaked link is dead
# before anyone finds it.
LINK_TTL_MINUTES = 15

# Matches the API's own floor, so a password accepted in one client is accepted
# in the other.
MIN_PASSWORD_LENGTH = 8


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

    async def create_account_from_messenger(
        self,
        provider: Provider,
        external_id: str,
        display_name: Optional[str] = None,
        external_username: Optional[str] = None,
    ) -> "User":
        """Make an account for someone who arrived from a messenger.

        The messenger is attached in the same unit of work, because an account
        with no identity is unreachable and an identity with no account cannot
        own anything. This exists so the conversation layer does not have to
        call `_attach` itself — it did, and reaching past a service is how the
        two clients drift apart.

        The account starts with no email, no phone and no password. That is
        survivable but not good: until one is set it cannot sign in to the API,
        a colleague cannot find it to add to a book, and losing the messenger
        loses the books. `set_contact` and `set_password` are how it stops
        being a dead end, and the bot asks for both.
        """
        if await self.find_identity(provider, external_id) is not None:
            raise AlreadyLinked("this messenger already belongs to an account")

        user = await self.create_user(display_name or "کاربر تازه")
        await self._attach(
            user_id=user.id,
            provider=provider,
            external_id=external_id,
            external_username=external_username,
            display_name=display_name,
        )
        return user

    async def set_contact(
        self,
        user_id: uuid.UUID,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> "User":
        """Give an account a way to be reached, and so a way to be recovered.

        One call sets one of them; passing neither is a mistake worth naming
        rather than a no-op that looks like it worked.
        """
        user = await self.get_user(user_id)

        if email is None and phone is None:
            raise ValidationError("ایمیل یا شمارهٔ تلفن لازم است")

        if email is not None:
            # The same validator the API's EmailStr uses, so an address the bot
            # accepts is one the web login accepts. A hand-rolled check drifted
            # from it immediately: it let "@example.com" through, and it would
            # have taken "emad@localhost" too.
            try:
                validated = validate_email(email.strip(), check_deliverability=False)
                # `normalized` lowercases the domain but keeps the local part's
                # case, because RFC-wise it is significant. Here it must not be:
                # `authenticate` and `find_by_identifier` both lowercase what
                # they are given, so storing "Emad@example.com" would make the
                # account impossible to sign in to or be found by.
                email = validated.normalized.lower()
            except EmailNotValidError:
                raise ValidationError("این ایمیل درست به نظر نمی‌رسد") from None

            taken = await self.find_by_identifier(email)
            if taken is not None and taken.id != user_id:
                # Deliberately vague: confirming which addresses are registered
                # would make this an account-finder.
                raise ValidationError("این ایمیل قابل استفاده نیست")
            user.email = email

        if phone is not None:
            phone = to_ascii_digits(phone).strip()
            if not phone.isdigit() or not (10 <= len(phone) <= 15):
                raise ValidationError("شمارهٔ تلفن درست نیست")
            taken = await self.find_by_identifier(phone)
            if taken is not None and taken.id != user_id:
                raise ValidationError("این شماره قابل استفاده نیست")
            user.phone = phone

        await self.session.flush()
        await self._audit(user_id, "user.contact_changed")
        return user

    async def set_password(
        self,
        user_id: uuid.UUID,
        new_password: str,
        current_password: Optional[str] = None,
    ) -> "User":
        """Set or change the password the API signs in with.

        When one is already set, the current one is required. Whoever holds the
        linked messenger can already read and change the books, so this buys
        less than it looks — but it does stop a stolen phone from quietly
        taking the web side too, and it costs one screen.
        """
        user = await self.get_user(user_id)

        if len(new_password or "") < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"رمز باید دست‌کم {MIN_PASSWORD_LENGTH} نویسه باشد"
            )

        if user.password_hash:
            if not current_password or not verify_password(
                current_password, user.password_hash
            ):
                raise ValidationError("رمز فعلی درست نیست")

        user.password_hash = hash_password(new_password)
        await self.session.flush()
        await self._audit(user_id, "user.password_changed")
        return user

    async def update_profile(
        self,
        user_id: uuid.UUID,
        display_name: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> "User":
        user = await self.get_user(user_id)

        if display_name is not None:
            display_name = display_name.strip()
            if not display_name:
                raise ValidationError("نام نمی‌تواند خالی باشد")
            user.display_name = display_name[:120]

        if timezone is not None:
            try:
                ZoneInfo(timezone)
            except Exception:
                # A bad zone would make the digest arrive at the wrong hour and
                # nobody would connect the two.
                raise ValidationError("این منطقهٔ زمانی شناخته نشد") from None
            user.timezone = timezone

        if locale is not None:
            user.locale = locale.strip()[:8] or "fa"

        await self.session.flush()
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
