"""Consent-based team membership and provider-specific invitation delivery."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ...shared.security import is_expired, utcnow
from ..identity.models import AuditEvent, Identity, Provider, User
from .models import Book, BookType, Permission, Role, TeamInvitation
from .service import BookService


class InvitationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.books = BookService(session)

    async def create(self, book_id, actor_user_id, provider, identifier, role=Role.MEMBER):
        await self.books.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
        if provider not in (Provider.TELEGRAM, Provider.BALE, Provider.RUBIKA):
            raise ValidationError("این پیام‌رسان برای ارسال دعوت پشتیبانی نمی‌شود.")
        book = await self.session.scalar(select(Book).where(Book.id == book_id).with_for_update())
        if book.type not in (BookType.TEAM, BookType.ORGANIZATION):
            raise ValidationError("دعوت هم‌تیمی فقط در دفتر تیمی یا سازمانی ممکن است.")
        if role is Role.OWNER:
            raise ValidationError("نقش مالک را نمی‌توان دعوت کرد.")
        needle = identifier.strip().lstrip("@").lower()
        query = select(Identity).join(User).where(Identity.provider == provider, User.is_active.is_(True))
        if needle.isascii() and needle.isdigit():
            query = query.where(Identity.external_id == needle)
        else:
            from sqlalchemy import func
            query = query.where(func.lower(Identity.external_username) == needle)
        identities = (await self.session.scalars(query)).all()
        if len(identities) != 1:
            raise NotFound("کاربر پیدا نشد؛ باید قبلاً ربات همین پیام‌رسان را استارت کرده باشد. شناسهٔ عددی را امتحان کن.")
        identity = identities[0]
        member = await self.books.membership(book_id, identity.user_id)
        if member is not None and member.is_active:
            raise ValidationError("این کاربر از قبل عضو دفتر است.")
        if await self.session.scalar(select(TeamInvitation.id).where(
            TeamInvitation.book_id == book_id, TeamInvitation.recipient_user_id == identity.user_id,
            TeamInvitation.status == "pending", TeamInvitation.expires_at > utcnow()
        ).limit(1)):
            raise ValidationError("برای این کاربر دعوت فعال وجود دارد.")
        row = TeamInvitation(book_id=book_id, actor_user_id=actor_user_id,
                             recipient_user_id=identity.user_id, recipient_identity_id=identity.id,
                             role=role, expires_at=utcnow() + timedelta(days=7))
        self.session.add(row)
        self.session.add(AuditEvent(user_id=actor_user_id, action="member.invited", subject=str(identity.user_id)))
        await self.session.flush()
        return row

    async def incoming(self, user_id):
        return (await self.session.scalars(select(TeamInvitation).where(
            TeamInvitation.recipient_user_id == user_id, TeamInvitation.status == "pending",
            TeamInvitation.expires_at > utcnow()
        ).order_by(TeamInvitation.created_at))).all()

    async def respond(self, invitation_id, user_id, accept):
        # The invitation, rather than membership, is the only authority to see
        # this book before joining. An unrelated account gets the same 404.
        row = await self.session.scalar(select(TeamInvitation).where(
            TeamInvitation.id == invitation_id, TeamInvitation.recipient_user_id == user_id
        ))
        if row is None:
            raise NotFound("دعوت پیدا نشد.")
        await self.session.execute(select(Book.id).where(Book.id == row.book_id).with_for_update())
        row = await self.session.scalar(select(TeamInvitation).where(
            TeamInvitation.id == invitation_id
        ).with_for_update().execution_options(populate_existing=True))
        if row.status != "pending" or is_expired(row.expires_at):
            raise ValidationError("این دعوت منقضی شده یا قبلاً پاسخ داده شده است.")
        if accept:
            # Losing management rights invalidates invitations from that actor.
            await self.books.require(row.book_id, row.actor_user_id, Permission.MANAGE_MEMBERS)
            identity = await self.session.get(Identity, row.recipient_identity_id)
            if identity is None or identity.user_id != user_id:
                raise ValidationError("هویت مقصد این دعوت تغییر کرده است.")
            member = await self.books.membership(row.book_id, user_id)
            if member is None:
                await self.books.add_member(row.actor_user_id, row.book_id, user_id, row.role)
            elif not member.is_active:
                member.is_active, member.role, member.joined_at = True, row.role, utcnow()
        row.status = "accepted" if accept else "declined"
        self.session.add(AuditEvent(user_id=user_id, action="invitation." + row.status, subject=str(row.id)))
        await self.session.flush()
        return row

    async def pending_delivery(self, provider):
        rows = (await self.session.execute(select(TeamInvitation, Identity, Book).join(
            Identity, Identity.id == TeamInvitation.recipient_identity_id
        ).join(Book, Book.id == TeamInvitation.book_id).where(
            Identity.provider == provider, Identity.user_id == TeamInvitation.recipient_user_id,
            TeamInvitation.notified_at.is_(None), TeamInvitation.status == "pending",
            TeamInvitation.expires_at > utcnow(),
            Book.is_active.is_(True),
        ).limit(50).with_for_update(of=TeamInvitation, skip_locked=True))).all()
        deliverable = []
        for invitation, identity, book in rows:
            recipient = await self.session.get(User, invitation.recipient_user_id)
            if recipient is not None and recipient.is_active and await self.books.can(
                book.id, invitation.actor_user_id, Permission.MANAGE_MEMBERS
            ):
                deliverable.append((invitation, identity, book))
            else:
                invitation.status = "cancelled"
        return deliverable

    async def mark_delivered(self, invitation):
        invitation.notified_at = utcnow()
        await self.session.flush()
