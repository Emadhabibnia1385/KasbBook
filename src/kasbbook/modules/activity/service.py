"""Reading the activity log back: a page of it, what it adds up to, and a spreadsheet of it."""

from __future__ import annotations

import csv
import io
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import ValidationError
from ..books.models import Book, Membership, Role
from ..identity.models import User
from .models import VIA_API, VIA_BOT, VIA_SYSTEM, VIA_WEB, ActivityEvent
from .recorder import CATEGORY_LABELS

VIA_LABELS = {VIA_WEB: "پنل", VIA_API: "API", VIA_BOT: "ربات", VIA_SYSTEM: "سیستم"}
MAX_EXPORT = 20000


@dataclass
class Filters:
    category: Optional[str] = None
    via: Optional[str] = None
    book_id: Optional[uuid.UUID] = None
    # "me" for the viewer's own actions, or a person's id.
    who: Optional[str] = None
    text: Optional[str] = None
    start: Optional[date] = None
    end: Optional[date] = None


@dataclass
class Row:
    event: ActivityEvent
    user_name: Optional[str]
    book_name: Optional[str]


class ActivityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------------------------------------------------------- who may see what
    async def _zone(self, viewer_id: uuid.UUID) -> ZoneInfo:
        user = await self.session.get(User, viewer_id)
        try:
            return ZoneInfo(user.timezone if user and user.timezone else "Asia/Tehran")
        except Exception:  # noqa: BLE001 - an unknown zone name: the default
            return ZoneInfo("Asia/Tehran")

    @staticmethod
    def _visible(viewer_id: uuid.UUID):
        """A person's own actions, and everything done in the books they own or administer."""
        managed = select(Membership.book_id).where(
            Membership.user_id == viewer_id,
            Membership.is_active.is_(True),
            Membership.role.in_([Role.OWNER, Role.ADMIN]),
        )
        return or_(ActivityEvent.user_id == viewer_id, ActivityEvent.book_id.in_(managed))

    def _where(self, viewer_id: uuid.UUID, f: Filters, zone: ZoneInfo) -> list:
        conditions = [self._visible(viewer_id)]
        if f.category:
            if f.category not in CATEGORY_LABELS:
                raise ValidationError("این گروه رویداد را نمی‌شناسم.")
            conditions.append(ActivityEvent.category == f.category)
        if f.via:
            if f.via not in VIA_LABELS:
                raise ValidationError("از راه نامعتبر.")
            conditions.append(ActivityEvent.via == f.via)
        if f.book_id:
            conditions.append(ActivityEvent.book_id == f.book_id)
        if f.who:
            if f.who == "me":
                conditions.append(ActivityEvent.user_id == viewer_id)
            else:
                try:
                    conditions.append(ActivityEvent.user_id == uuid.UUID(f.who))
                except ValueError:
                    raise ValidationError("شناسهٔ فرد درست نیست.") from None
        if f.text and f.text.strip():
            conditions.append(ActivityEvent.summary.ilike(f"%{f.text.strip()}%"))
        if f.start:
            conditions.append(ActivityEvent.created_at >= datetime.combine(f.start, time.min, zone))
        if f.end:
            conditions.append(
                ActivityEvent.created_at < datetime.combine(f.end + timedelta(days=1), time.min, zone)
            )
        return conditions

    def _select(self, conditions: list):
        return (
            select(ActivityEvent, User.display_name, Book.name)
            .outerjoin(User, User.id == ActivityEvent.user_id)
            .outerjoin(Book, Book.id == ActivityEvent.book_id)
            .where(and_(*conditions))
            .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        )

    # ---------------------------------------------------------------- reading
    async def page(
        self, viewer_id: uuid.UUID, f: Filters, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Row], int]:
        zone = await self._zone(viewer_id)
        conditions = self._where(viewer_id, f, zone)
        total = (
            await self.session.execute(
                select(func.count(ActivityEvent.id)).where(and_(*conditions))
            )
        ).scalar_one()
        rows = (
            await self.session.execute(self._select(conditions).limit(limit).offset(offset))
        ).all()
        return [Row(event, name, book) for event, name, book in rows], int(total)

    async def summary(self, viewer_id: uuid.UUID, f: Filters, days: int = 30) -> Dict:
        zone = await self._zone(viewer_id)
        conditions = self._where(viewer_id, f, zone)
        by_category = (
            await self.session.execute(
                select(ActivityEvent.category, func.count(ActivityEvent.id))
                .where(and_(*conditions)).group_by(ActivityEvent.category)
            )
        ).all()
        by_via = (
            await self.session.execute(
                select(ActivityEvent.via, func.count(ActivityEvent.id))
                .where(and_(*conditions)).group_by(ActivityEvent.via)
            )
        ).all()
        by_user = (
            await self.session.execute(
                select(ActivityEvent.user_id, User.display_name, func.count(ActivityEvent.id))
                .outerjoin(User, User.id == ActivityEvent.user_id)
                .where(and_(*conditions)).group_by(ActivityEvent.user_id, User.display_name)
                .order_by(func.count(ActivityEvent.id).desc())
            )
        ).all()
        since = datetime.now(zone).date() - timedelta(days=days - 1)
        stamps = (
            await self.session.execute(
                select(ActivityEvent.created_at).where(
                    and_(*conditions, ActivityEvent.created_at >= datetime.combine(since, time.min, zone))
                )
            )
        ).scalars().all()
        per_day: Counter = Counter()
        for stamp in stamps:
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            per_day[stamp.astimezone(zone).date()] += 1
        series = [
            (since + timedelta(days=offset), per_day.get(since + timedelta(days=offset), 0))
            for offset in range(days)
        ]
        return {
            "total": sum(count for _c, count in by_category),
            "by_category": sorted(by_category, key=lambda row: -row[1]),
            "by_via": sorted(by_via, key=lambda row: -row[1]),
            "by_user": by_user,
            "by_day": series,
        }

    async def groups_for(self, viewer_id: uuid.UUID) -> Dict:
        """The people and the books the viewer can narrow by."""
        zone = await self._zone(viewer_id)
        conditions = self._where(viewer_id, Filters(), zone)
        people = (
            await self.session.execute(
                select(ActivityEvent.user_id, User.display_name)
                .outerjoin(User, User.id == ActivityEvent.user_id)
                .where(and_(*conditions, ActivityEvent.user_id.is_not(None)))
                .group_by(ActivityEvent.user_id, User.display_name)
            )
        ).all()
        books = (
            await self.session.execute(
                select(ActivityEvent.book_id, Book.name)
                .join(Book, Book.id == ActivityEvent.book_id)
                .where(and_(*conditions))
                .group_by(ActivityEvent.book_id, Book.name)
            )
        ).all()
        return {"people": people, "books": books}

    # ---------------------------------------------------------------- the spreadsheet
    async def csv(self, viewer_id: uuid.UUID, f: Filters) -> str:
        zone = await self._zone(viewer_id)
        conditions = self._where(viewer_id, f, zone)
        rows = (
            await self.session.execute(self._select(conditions).limit(MAX_EXPORT))
        ).all()
        out = io.StringIO()
        out.write("﻿")  # so a spreadsheet opens the Persian as Persian
        writer = csv.writer(out)
        writer.writerow(["چه کسی", "از راه", "تاریخ", "ساعت", "گروه", "دفتر", "عملیات"])
        for event, name, book in rows:
            stamp = event.created_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            local = stamp.astimezone(zone)
            who = "تو" if event.user_id == viewer_id else (name or VIA_LABELS.get(event.via, ""))
            writer.writerow([
                who, VIA_LABELS.get(event.via, event.via), local.date().isoformat(),
                local.strftime("%H:%M:%S"), CATEGORY_LABELS.get(event.category, event.category),
                book or "", event.summary,
            ])
        return out.getvalue()
