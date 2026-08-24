"""Books, membership and permission checks.

Every permission decision in the system happens here. An adapter or an HTTP
route may decide what to *show*; only this service decides what is *allowed*.
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, PermissionDenied, ValidationError
from ...shared.security import utcnow
from ..identity.models import AuditEvent
from .models import Book, BookType, Membership, Permission, Role


class BookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------------------------------------------------------- books
    async def create_book(
        self,
        owner_user_id: uuid.UUID,
        name: str,
        book_type: BookType,
        base_currency: str = "IRT",
    ) -> Book:
        book = Book(
            name=name.strip(),
            type=book_type,
            owner_user_id=owner_user_id,
            base_currency=base_currency.upper(),
        )
        self.session.add(book)
        await self.session.flush()

        # The owner is a member too, so every access check has exactly one path
        # to follow instead of a special case for owners.
        self.session.add(
            Membership(
                book_id=book.id,
                user_id=owner_user_id,
                role=Role.OWNER,
                joined_at=utcnow(),
            )
        )
        self.session.add(
            AuditEvent(user_id=owner_user_id, action="book.created", subject=name)
        )
        await self.session.flush()
        return book

    async def get_book(self, book_id: uuid.UUID) -> Book:
        book = await self.session.get(Book, book_id)
        if book is None:
            raise NotFound(f"book {book_id}")
        return book

    async def books_for_user(self, user_id: uuid.UUID) -> Sequence[Book]:
        """Only books this user is an active member of — the isolation boundary."""
        stmt = (
            select(Book)
            .join(Membership, Membership.book_id == Book.id)
            .where(
                Membership.user_id == user_id,
                Membership.is_active.is_(True),
                Book.is_active.is_(True),
            )
            .order_by(Book.created_at)
        )
        return (await self.session.execute(stmt)).scalars().all()

    # ----------------------------------------------------------- membership
    async def membership(
        self, book_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[Membership]:
        stmt = select(Membership).where(
            Membership.book_id == book_id, Membership.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_member(
        self,
        actor_user_id: uuid.UUID,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
    ) -> Membership:
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)

        if role is Role.OWNER:
            raise ValidationError("a book has one owner; transfer it instead")
        if await self.membership(book_id, user_id) is not None:
            raise ValidationError("this person is already a member")

        member = Membership(
            book_id=book_id, user_id=user_id, role=role, joined_at=utcnow()
        )
        self.session.add(member)
        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="member.added",
                subject=str(user_id),
                detail=role.value,
            )
        )
        await self.session.flush()
        return member

    async def change_role(
        self,
        actor_user_id: uuid.UUID,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
    ) -> Membership:
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)

        member = await self.membership(book_id, user_id)
        if member is None:
            raise NotFound("membership")
        if member.role is Role.OWNER:
            raise ValidationError("the owner's role cannot be changed directly")
        if role is Role.OWNER:
            raise ValidationError("use transfer_ownership to hand a book over")

        member.role = role
        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="member.role_changed",
                subject=str(user_id),
                detail=role.value,
            )
        )
        await self.session.flush()
        return member

    async def deactivate_member(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)

        member = await self.membership(book_id, user_id)
        if member is None:
            raise NotFound("membership")
        if member.role is Role.OWNER:
            raise ValidationError("the owner cannot be removed from their own book")

        member.is_active = False
        self.session.add(
            AuditEvent(
                user_id=actor_user_id, action="member.deactivated", subject=str(user_id)
            )
        )
        await self.session.flush()

    async def transfer_ownership(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID, to_user_id: uuid.UUID
    ) -> None:
        book = await self.get_book(book_id)
        if book.owner_user_id != actor_user_id:
            raise PermissionDenied("only the owner may hand a book over")

        target = await self.membership(book_id, to_user_id)
        if target is None or not target.is_active:
            raise ValidationError("the new owner must already be an active member")

        previous = await self.membership(book_id, actor_user_id)
        if previous is not None:
            previous.role = Role.ADMIN

        target.role = Role.OWNER
        book.owner_user_id = to_user_id
        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="book.ownership_transferred",
                subject=str(to_user_id),
            )
        )
        await self.session.flush()

    # ---------------------------------------------------------- permissions
    async def permissions_for(
        self, book_id: uuid.UUID, user_id: uuid.UUID
    ) -> set:
        member = await self.membership(book_id, user_id)
        return member.permissions if member is not None else set()

    async def can(
        self, book_id: uuid.UUID, user_id: uuid.UUID, permission: Permission
    ) -> bool:
        return permission in await self.permissions_for(book_id, user_id)

    async def require(
        self, book_id: uuid.UUID, user_id: uuid.UUID, permission: Permission
    ) -> Membership:
        """Raise unless the user may do this. The one gate everything passes."""
        member = await self.membership(book_id, user_id)
        if member is None or not member.is_active:
            # A non-member is told the book does not exist rather than that it
            # does but is off-limits, so ids cannot be probed.
            raise NotFound("book")
        if permission not in member.permissions:
            raise PermissionDenied(f"{member.role.value} may not {permission.value}")
        return member
