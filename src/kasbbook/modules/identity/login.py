"""Account switching requires proof sent to an existing linked messenger."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ...shared.security import expires_in, is_expired, new_link_code, token_digest, tokens_match, utcnow
from ..books.service import BookService
from .auth import AuthService
from .models import AccountLoginChallenge, AuditEvent, Identity, User
from .service import IdentityService


@dataclass(frozen=True)
class IssuedAccountLogin:
    challenge_id: uuid.UUID
    # Delivery-only fields; never return them to the requester or an API client.
    destination_external_id: str | None
    code: str


class AccountLoginService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.identities = IdentityService(session)

    async def _require_recoverable_source(self, actor_user_id, identity):
        source = await self.identities.get_user(actor_user_id)
        alternatives = await self.session.scalar(select(Identity.id).where(
            Identity.user_id == actor_user_id, Identity.id != identity.id
        ).limit(1))
        if (await BookService(self.session).books_for_user(actor_user_id) and not alternatives
                and not ((source.email or source.phone) and source.password_hash)):
            raise ValidationError("پیش از تغییر حساب، برای حساب فعلی ایمیل یا شماره و رمز تعیین کن تا دفترهایت قابل دسترسی بمانند.")

    async def request(self, actor_user_id, requester_identity_id, identifier):
        identity = await self.session.scalar(select(Identity).where(
            Identity.id == requester_identity_id, Identity.user_id == actor_user_id
        ).with_for_update())
        if identity is None:
            raise NotFound("هویت پیدا نشد.")
        await self._require_recoverable_source(actor_user_id, identity)
        since = utcnow() - timedelta(hours=1)
        count = await self.session.scalar(select(func.count()).select_from(AccountLoginChallenge).where(
            AccountLoginChallenge.requester_identity_id == identity.id,
            AccountLoginChallenge.created_at >= since
        ))
        if count >= 5:
            raise ValidationError("تعداد درخواست ورود زیاد است؛ یک ساعت بعد دوباره امتحان کن.")
        target = await self.identities.find_by_identifier(identifier)
        destination = None
        if target is not None and target.is_active and target.id != actor_user_id:
            # Same provider only: the running bot must never send a Bale id to
            # Telegram, and email/SMS delivery has no configured infrastructure.
            destination = await self.session.scalar(select(Identity).where(
                Identity.user_id == target.id, Identity.provider == identity.provider,
                Identity.id != identity.id
            ).order_by(Identity.linked_at).limit(1))
            if destination is not None:
                await self.session.execute(select(User.id).where(User.id == target.id).with_for_update())
                recent = await self.session.scalar(select(func.count()).select_from(AccountLoginChallenge).where(
                    AccountLoginChallenge.target_user_id == target.id,
                    AccountLoginChallenge.created_at >= since
                ))
                if recent >= 5:
                    destination = None
        # Decoys have exactly the same response and five-attempt budget, so an
        # unknown address cannot be distinguished by the requesting interface.
        raw = new_link_code(10)
        row = AccountLoginChallenge(requester_identity_id=identity.id,
            source_user_id=actor_user_id, target_user_id=target.id if destination else None,
            destination_identity_id=destination.id if destination else None,
            destination_digest=token_digest(identifier.strip().lower()),
            token_digest=token_digest(raw), expires_at=expires_in(5))
        for previous in (await self.session.scalars(select(AccountLoginChallenge).where(
            AccountLoginChallenge.requester_identity_id == identity.id,
            AccountLoginChallenge.consumed_at.is_(None)
        ))).all():
            previous.consumed_at = utcnow()
        self.session.add(row)
        await self.session.flush()
        return IssuedAccountLogin(row.id, destination.external_id if destination else None, raw)

    async def complete(self, actor_user_id, requester_identity_id, challenge_id, code):
        identity = await self.session.scalar(select(Identity).where(
            Identity.id == requester_identity_id, Identity.user_id == actor_user_id
        ).with_for_update())
        if identity is None:
            raise NotFound("هویت پیدا نشد.")
        row = await self.session.scalar(select(AccountLoginChallenge).where(
            AccountLoginChallenge.id == challenge_id,
            AccountLoginChallenge.requester_identity_id == identity.id,
            AccountLoginChallenge.source_user_id == actor_user_id
        ).with_for_update())
        if row is None or row.consumed_at is not None or is_expired(row.expires_at) or row.attempts >= 5:
            return None
        row.attempts += 1
        if row.target_user_id is None or not tokens_match(code.strip().upper(), row.token_digest):
            await self.session.flush()
            return None
        users = (await self.session.scalars(select(User).where(
            User.id.in_([actor_user_id, row.target_user_id])
        ).order_by(User.id).with_for_update().execution_options(populate_existing=True))).all()
        target = next((u for u in users if u.id == row.target_user_id and u.is_active), None)
        if target is None or not await self.session.scalar(select(Identity.id).where(
            Identity.id == row.destination_identity_id, Identity.user_id == target.id,
            Identity.provider == identity.provider, Identity.id != identity.id
        ).limit(1)):
            return None
        await self._require_recoverable_source(actor_user_id, identity)
        # Move only this messenger pointer. Never merge books, balances, payroll,
        # memberships or credentials from the source account.
        identity.user_id, identity.linked_at = target.id, utcnow()
        row.consumed_at = utcnow()
        auth = AuthService(self.session, "account-switch-does-not-mint-tokens")
        for user in users:
            await auth.revoke_all_for_user(user.id)
        self.session.add(AuditEvent(user_id=actor_user_id, action="identity.account_switched",
                                   subject=str(identity.id), detail=str(target.id)))
        await self.session.flush()
        return target
