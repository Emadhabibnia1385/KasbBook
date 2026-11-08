"""Folding one account into another.

Someone signs up on the web with a username and a password, then connects Telegram — and that Telegram
already had an account of its own, with books in it. Two accounts are one person, and everything the
second holds has to end up on the first, because a half-merge is worse than none: books without an owner,
records without an author, or a person who sees half their money.

The merge is written against the schema rather than a list of tables. Every column that references
`users.id` is found from the models' metadata and moved, so a table added next year is carried across
without anyone remembering to edit this file. What cannot be moved blindly is named below.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import Table, and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.database import Base
from ...shared.errors import ValidationError
from ..books.models import Membership, Role
from .models import AuditEvent, User

# Stronger first: when both accounts sit in one book, the person keeps the stronger of the two roles.
ROLE_ORDER = [Role.OWNER, Role.ADMIN, Role.ACCOUNTANT, Role.MEMBER, Role.VIEWER]

# Signed in on the account that is going away, so those sessions end; the person signs in on the survivor.
# A link code only meant something to the account that asked for it.
DISCARDED = ("refresh_tokens", "link_tokens")

REFUSAL = (
    "این دو حساب هر دو در یک دورهٔ حقوق یا یک رکورد یکتا سابقه دارند و ادغامشان چیزی را "
    "دوبار می‌شمارد؛ پیش از ادغام یکی از آن‌ها را مرتب کن."
)
NOT_MERGEABLE = "حساب مهمان، دمو و عضو بدون حساب ادغام نمی‌شوند."


@dataclass(frozen=True)
class MergePreview:
    """What the person is shown before agreeing."""

    keep_name: str
    keep_username: Optional[str]
    absorb_books: int


def _user_columns() -> List[Tuple[Table, str]]:
    """Every (table, column) that points at users.id, found from the models."""
    found: List[Tuple[Table, str]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == "users" and fk.column.name == "id":
                    found.append((table, column.name))
    return found


def _unique_sets(table: Table, column: str) -> List[List[str]]:
    """The other columns of every unique constraint or index that includes `column`."""
    sets: List[List[str]] = []
    for constraint in list(table.constraints) + list(table.indexes):
        columns = [c.name for c in getattr(constraint, "columns", [])]
        unique = getattr(constraint, "unique", None)
        is_unique_constraint = constraint.__class__.__name__ == "UniqueConstraint" or unique
        if is_unique_constraint and column in columns and len(columns) > 1:
            sets.append([c for c in columns if c != column])
    return sets


async def preview(session: AsyncSession, keep_id: uuid.UUID, absorb_id: uuid.UUID) -> MergePreview:
    keep = await session.get(User, keep_id)
    absorb = await session.get(User, absorb_id)
    _refuse_unmergeable(keep, absorb)
    owned = (
        await session.execute(select(Membership.id).where(Membership.user_id == absorb_id))
    ).all()
    return MergePreview(keep.display_name, keep.username, len(owned))


def _refuse_unmergeable(keep: Optional[User], absorb: Optional[User]) -> None:
    if keep is None or absorb is None or keep.id == absorb.id:
        raise ValidationError("حساب پیدا نشد.")
    for person in (keep, absorb):
        if person.is_guest or person.is_demo or person.is_placeholder or not person.is_active:
            raise ValidationError(NOT_MERGEABLE)


async def merge_accounts(session: AsyncSession, keep_id: uuid.UUID, absorb_id: uuid.UUID) -> None:
    """Move everything `absorb` holds onto `keep`, then remove `absorb`."""
    keep = await session.get(User, keep_id)
    absorb = await session.get(User, absorb_id)
    _refuse_unmergeable(keep, absorb)

    await _merge_memberships(session, keep_id, absorb_id)

    columns = [(t, c) for t, c in _user_columns() if t.name != "memberships"]
    # A unique key that both accounts would end up sharing cannot be repaired by moving rows.
    for table, column in columns:
        if table.name in DISCARDED:
            continue
        for others in _unique_sets(table, column):
            a, b = table.alias("a"), table.alias("b")
            same = and_(*[a.c[name] == b.c[name] for name in others])
            clash = await session.execute(
                select(a.c[column]).select_from(a.join(b, same))
                .where(a.c[column] == keep_id, b.c[column] == absorb_id).limit(1)
            )
            if clash.first() is not None:
                raise ValidationError(REFUSAL)

    for name in DISCARDED:
        table = Base.metadata.tables[name]
        for t, c in columns:
            if t.name == name:
                await session.execute(delete(table).where(table.c[c] == absorb_id))

    for table, column in columns:
        if table.name in DISCARDED:
            continue
        await session.execute(update(table).where(table.c[column] == absorb_id).values({column: keep_id}))

    # Contact details the survivor lacks come across; the survivor's own name, password and login stay.
    email, phone, username = absorb.email, absorb.phone, absorb.username
    absorb_display = absorb.display_name
    await session.execute(
        update(User).where(User.id == absorb_id).values(email=None, phone=None, username=None)
    )
    await session.execute(
        update(User).where(User.id == keep_id).values(
            email=keep.email or email,
            phone=keep.phone or phone,
            username=keep.username or username,
        )
    )
    # A survivor still called by its sign-up username takes the name the other account was known by.
    if keep.username and keep.display_name == keep.username and absorb_display:
        await session.execute(update(User).where(User.id == keep_id).values(display_name=absorb_display))

    await session.execute(delete(User).where(User.id == absorb_id))
    session.add(AuditEvent(user_id=keep_id, action="account.merged", detail=str(absorb_id)))
    await session.flush()
    session.expire_all()


async def _merge_memberships(session: AsyncSession, keep_id: uuid.UUID, absorb_id: uuid.UUID) -> None:
    """In a book both belong to, one membership survives with the stronger role."""
    kept = {
        row.book_id: row
        for row in (
            await session.execute(select(Membership).where(Membership.user_id == keep_id))
        ).scalars()
    }
    for row in (
        await session.execute(select(Membership).where(Membership.user_id == absorb_id))
    ).scalars().all():
        mine = kept.get(row.book_id)
        if mine is None:
            continue  # moves with the generic update below, through the memberships table itself
        if ROLE_ORDER.index(row.role) < ROLE_ORDER.index(mine.role):
            mine.role = row.role
        mine.is_active = mine.is_active or row.is_active
        await session.delete(row)
    await session.flush()
    # What is left of the absorbed account's memberships moves now, so the generic pass skips the table.
    await session.execute(
        update(Membership).where(Membership.user_id == absorb_id).values(user_id=keep_id)
    )
