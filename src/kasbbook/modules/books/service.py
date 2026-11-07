"""Books, membership and permission checks.

Every permission decision in the system happens here. An adapter or an HTTP
route may decide what to *show*; only this service decides what is *allowed*.
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, PermissionDenied, ValidationError
from ...shared.security import utcnow
from ..exchange.catalog import BY_CODE
from ..identity.models import AuditEvent
from ..ledger.models import JournalEntry, JournalLine
from ..treasury.models import TreasuryAllocation
from .models import Book, BookType, CostPolicy, Membership, Permission, Role


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
        cost_policy: CostPolicy = CostPolicy.BEFORE_SPLIT,
        calendar: str = "jalali",
    ) -> Book:
        # Checked here, not in a route, so the bot and the API refuse the same codes.
        if base_currency.upper() not in BY_CODE:
            raise ValidationError(f"ارز {base_currency} پشتیبانی نمی‌شود.")
        calendar = self._valid_calendar(calendar)
        book = Book(
            name=name.strip(),
            type=book_type,
            owner_user_id=owner_user_id,
            base_currency=base_currency.upper(),
            cost_policy=cost_policy,
            calendar=calendar,
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

    @staticmethod
    def _valid_calendar(calendar: str) -> str:
        from ...shared.calendars import CALENDAR_NAMES

        value = (calendar or "").strip().lower()
        if value not in CALENDAR_NAMES:
            raise ValidationError("تقویم باید شمسی یا میلادی باشد.")
        return value

    async def set_calendar(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID, calendar: str
    ) -> Book:
        """Change which calendar this book's months and years are counted by.

        Every date is stored as a Gregorian day, so nothing recorded moves: the
        same days are simply grouped into different months from now on. That is
        why it is allowed on a book with history, unlike the currency.
        """
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
        book = await self.get_book(book_id)
        book.calendar = self._valid_calendar(calendar)
        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="book.calendar_changed",
                subject=str(book_id),
                detail=book.calendar,
            )
        )
        await self.session.flush()
        return book

    async def update_book(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID,
        name: Optional[str] = None, book_type: Optional[BookType] = None,
    ) -> Book:
        """Rename a book or change what kind of book it is. Nothing recorded moves.

        A personal book is one person's: it cannot be made so while others are in it, and the web panel
        offers the team, payroll and shares only to the other kinds.
        """
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
        book = await self.get_book(book_id)
        if name is not None:
            name = name.strip()
            if not name:
                raise ValidationError("نام دفتر را بنویس.")
            book.name = name[:120]
        if book_type is not None and book_type is not book.type:
            if book_type is BookType.PERSONAL:
                others = (
                    await self.session.execute(
                        select(Membership.user_id).where(
                            Membership.book_id == book_id,
                            Membership.is_active.is_(True),
                            Membership.user_id != book.owner_user_id,
                        )
                    )
                ).first()
                if others is not None:
                    raise ValidationError("این دفتر عضو دیگری دارد؛ اول آنها را بردار تا بشود شخصی.")
            book.type = book_type
        self.session.add(
            AuditEvent(user_id=actor_user_id, action="book.updated", subject=str(book_id), detail=book.name)
        )
        await self.session.flush()
        return book

    async def set_cost_policy(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID, policy: CostPolicy
    ) -> Book:
        """Change who carries this book's costs.

        Gated on MANAGE_TREASURY because that is whose money the answer moves:
        under FROM_TREASURY the members are paid more and the treasury keeps
        less. A period that has already been calculated keeps the figures
        frozen on its payslips, so this only steers what is worked out next.
        """
        await self.require(book_id, actor_user_id, Permission.MANAGE_TREASURY)
        book = await self.get_book(book_id)
        book.cost_policy = policy
        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="book.cost_policy_changed",
                subject=str(book_id),
                detail=policy.value,
            )
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

    async def members(self, book_id: uuid.UUID) -> Sequence[Membership]:
        """Everyone currently on this book, owner first.

        Deactivated memberships are left out: they are kept as history, not as
        people who can still see the books.
        """
        stmt = (
            select(Membership)
            .where(Membership.book_id == book_id, Membership.is_active.is_(True))
            .order_by(Membership.role, Membership.created_at)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def members_ever(self, book_id: uuid.UUID) -> Sequence[Membership]:
        """Everyone who has been on the book, including those since removed."""
        stmt = select(Membership).where(Membership.book_id == book_id)
        return (await self.session.execute(stmt)).scalars().all()

    async def _refuse_guest(self, user_id: uuid.UUID) -> None:
        """A guest's account is deleted when they leave, so nobody else may be tied to it."""
        from ..identity.models import User

        actor = await self.session.get(User, user_id)
        if actor is not None and actor.is_guest:
            raise PermissionDenied("حساب مهمان نمی‌تواند همکار اضافه کند.")

    async def add_member(
        self,
        actor_user_id: uuid.UUID,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
    ) -> Membership:
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
        await self._refuse_guest(actor_user_id)

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

    async def add_person(
        self,
        actor_user_id: uuid.UUID,
        book_id: uuid.UUID,
        name: str,
        role: Role = Role.VIEWER,
    ) -> Membership:
        """Add a colleague by name only: someone to pay and count, with no account to sign in to.

        They are a real row in `users` flagged as a placeholder, so shares, performance and payslips
        work for them exactly as for anyone. Nothing can sign in as them. When they are meant to
        reach the panel or the bot, `link_person` moves everything onto their real account.
        """
        from ..identity.models import User

        # A guest may add people by name: nobody else's account is tied to theirs, unlike a real invitation.
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
        book = await self.get_book(book_id)
        if book.type is BookType.PERSONAL:
            raise ValidationError("یک دفتر شخصی همکار ندارد.")
        if role is Role.OWNER:
            raise ValidationError("a book has one owner; transfer it instead")
        clean = " ".join((name or "").split())
        if not clean:
            raise ValidationError("نام را بنویس.")

        person = User(display_name=clean[:120], is_placeholder=True, timezone=book.timezone)
        self.session.add(person)
        await self.session.flush()
        member = Membership(book_id=book_id, user_id=person.id, role=role, joined_at=utcnow())
        self.session.add(member)
        self.session.add(
            AuditEvent(
                user_id=actor_user_id, action="member.added", subject=str(person.id), detail=role.value
            )
        )
        await self.session.flush()
        return member

    async def rename_person(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID, user_id: uuid.UUID, name: str
    ) -> None:
        """Only a name this book gave: a real account's name is theirs to change."""
        from ..identity.models import User

        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
        if await self.membership(book_id, user_id) is None:
            raise NotFound("membership")
        person = await self.session.get(User, user_id)
        if person is None or not person.is_placeholder:
            raise ValidationError("نام یک حساب واقعی را خودش عوض می‌کند.")
        clean = " ".join((name or "").split())
        if not clean:
            raise ValidationError("نام را بنویس.")
        person.display_name = clean[:120]
        await self.session.flush()

    async def link_person(
        self,
        actor_user_id: uuid.UUID,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        identifier: str,
        role: Role,
    ) -> Membership:
        """Point a colleague added by name at a real account, keeping everything they were paid.

        The shares, performance records, adjustments and payslips follow onto the account; the
        placeholder row is then gone. The role given here is what the account gets in this book.
        """
        from ..identity.models import AuditEvent as _Audit, User
        from ..identity.service import IdentityService
        from ..payroll.models import Adjustment, Payslip, PerformanceRecord, ShareRule

        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
        if role is Role.OWNER:
            raise ValidationError("a book has one owner; transfer it instead")
        current = await self.membership(book_id, user_id)
        person = await self.session.get(User, user_id)
        if current is None or person is None:
            raise NotFound("membership")
        if not person.is_placeholder:
            raise ValidationError("این همکار از قبل حساب دارد.")

        target = await IdentityService(self.session).find_by_identifier(identifier)
        if target is None:
            raise NotFound(
                "حسابی با این شناسه پیدا نشد؛ باید قبلاً ربات را استارت کرده یا در پنل ثبت‌نام کرده باشد."
            )
        if await self.membership(book_id, target.id) is not None:
            raise ValidationError("صاحب این حساب از قبل در این دفتر هست.")

        for model in (ShareRule, PerformanceRecord, Adjustment, Payslip):
            await self.session.execute(
                update(model)
                .where(model.book_id == book_id, model.user_id == user_id)
                .values(user_id=target.id)
            )
        await self.session.delete(current)
        await self.session.flush()
        member = Membership(book_id=book_id, user_id=target.id, role=role, joined_at=utcnow())
        self.session.add(member)
        self.session.add(
            _Audit(
                user_id=actor_user_id,
                action="member.linked",
                subject=str(target.id),
                detail=role.value,
            )
        )
        await self.session.flush()
        # Nothing else can point at a placeholder: it never signed in, so it never wrote a record.
        await self._drop_orphan_placeholders([user_id])
        return member

    async def _drop_orphan_placeholders(self, user_ids) -> None:
        """Delete placeholder rows no book holds any more."""
        from ..identity.models import User

        for user_id in user_ids:
            still = await self.session.scalar(
                select(Membership.id).where(Membership.user_id == user_id).limit(1)
            )
            person = await self.session.get(User, user_id)
            if still is None and person is not None and person.is_placeholder:
                await self.session.delete(person)
        await self.session.flush()

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
        await self._end_shares(book_id, user_id)
        self.session.add(
            AuditEvent(
                user_id=actor_user_id, action="member.deactivated", subject=str(user_id)
            )
        )
        await self.session.flush()

    async def _end_shares(self, book_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Someone taken off the book stops taking a share from today; what they were paid stays.

        Closed rather than switched off, as `PayrollService.clear_share` does, so past periods that
        are recalculated still find the share they were paid under.
        """
        from datetime import timedelta

        from ...shared import jalali
        from ..payroll.models import ShareRule

        book = await self.get_book(book_id)
        today = jalali.today_in(book.timezone)
        for rule in (
            await self.session.execute(
                select(ShareRule).where(
                    ShareRule.book_id == book_id,
                    ShareRule.user_id == user_id,
                    ShareRule.is_active.is_(True),
                )
            )
        ).scalars().all():
            if rule.effective_from >= today:
                rule.is_active = False
            elif rule.effective_to is None or rule.effective_to >= today:
                rule.effective_to = today - timedelta(days=1)

    async def delete_book(self, actor_user_id: uuid.UUID, book_id: uuid.UUID) -> None:
        """Destroy a book and everything recorded in it. There is no undo.

        Only the owner, and only when nobody else is left on it: a book other
        people are still using is not one person's to throw away. They must be
        removed, or the book handed over, first.

        Every foreign key pointing at `books` is ON DELETE CASCADE, so deleting
        the row takes the transactions, journal, budgets, debts, loans, payroll
        and treasury with it. Two edges are RESTRICT and have to be cleared by
        hand first, because the database does not promise to process the
        cascade in an order that satisfies them:

          journal_lines → accounts
          treasury_allocations → treasury_funds

        Both are RESTRICT on purpose — an account with journal lines against it
        must not vanish under normal circumstances. This is the one place that
        is allowed to say the circumstances are not normal.
        """
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
        book = await self.get_book(book_id)
        if book.owner_user_id != actor_user_id:
            raise PermissionDenied("only the owner may delete a book")

        from ..identity.models import User

        # Colleagues added by name have no account to lose the book from, so they never block it.
        others = [
            m
            for m in await self.members(book_id)
            if m.user_id != actor_user_id
            and not (await self.session.get(User, m.user_id)).is_placeholder
        ]
        if others:
            raise ValidationError(
                f"این دفتر {len(others)} عضو دیگر دارد. اول آن‌ها را حذف کن "
                "یا دفتر را به یکی‌شان واگذار کن."
            )

        await self.session.execute(
            delete(JournalLine).where(
                JournalLine.entry_id.in_(
                    select(JournalEntry.id).where(JournalEntry.book_id == book_id)
                )
            )
        )
        await self.session.execute(
            delete(TreasuryAllocation).where(TreasuryAllocation.book_id == book_id)
        )

        self.session.add(
            AuditEvent(
                user_id=actor_user_id, action="book.deleted", subject=book.name
            )
        )
        placeholders = [
            row.user_id
            for row in await self.session.scalars(
                select(Membership).where(Membership.book_id == book_id)
            )
        ]
        await self.session.delete(book)
        await self.session.flush()
        await self._drop_orphan_placeholders(placeholders)

    async def transfer_ownership(
        self, actor_user_id: uuid.UUID, book_id: uuid.UUID, to_user_id: uuid.UUID
    ) -> None:
        await self.require(book_id, actor_user_id, Permission.MANAGE_MEMBERS)
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
