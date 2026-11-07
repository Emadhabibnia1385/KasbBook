"""«رویدادها»: the log of what people (and programs on their behalf) did.

A person sees their own actions everywhere, and everything done in the books they own or administer.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response

from ...modules.activity.recorder import CATEGORY_LABELS
from ...modules.activity.service import VIA_LABELS, ActivityService, Filters, Row
from ..deps import Person, SessionDep
from ..schemas_activity import (
    ActivityItem,
    ActivityOptions,
    ActivityPage,
    ActivitySummary,
    CountRow,
    DayCount,
    NamedId,
)

router = APIRouter(prefix="/activity", tags=["activity"])


def _filters(
    category: Optional[str] = Query(None, description="transactions, categories, budgets, debts, loans, …"),
    via: Optional[str] = Query(None, description="web, api, bot or system"),
    book_id: Optional[uuid.UUID] = None,
    who: Optional[str] = Query(None, description="`me`, or a person's id"),
    q: Optional[str] = Query(None, description="part of the sentence"),
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Filters:
    return Filters(category=category, via=via, book_id=book_id, who=who, text=q, start=start, end=end)


def _item(row: Row, viewer_id: uuid.UUID) -> ActivityItem:
    event = row.event
    return ActivityItem(
        id=event.id,
        at=event.created_at,
        user_id=event.user_id,
        user_name=row.user_name,
        is_me=event.user_id == viewer_id,
        via=event.via,
        via_label=VIA_LABELS.get(event.via, event.via),
        book_id=event.book_id,
        book_name=row.book_name,
        category=event.category,
        category_label=CATEGORY_LABELS.get(event.category, event.category),
        action=event.action,
        summary=event.summary,
    )


FiltersDep = Depends(_filters)


@router.get("", response_model=ActivityPage)
async def list_activity(
    user: Person,
    session: SessionDep,
    filters: Filters = FiltersDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ActivityPage:
    """A page of the log, newest first."""
    rows, total = await ActivityService(session).page(user.id, filters, limit, offset)
    return ActivityPage(items=[_item(row, user.id) for row in rows], total=total)


@router.get("/summary", response_model=ActivitySummary)
async def summary(
    user: Person,
    session: SessionDep,
    filters: Filters = FiltersDep,
    days: int = Query(30, ge=7, le=90),
) -> ActivitySummary:
    """What the log adds up to, for the same filters: per group, per way in, per person, per day."""
    data = await ActivityService(session).summary(user.id, filters, days)
    return ActivitySummary(
        total=data["total"],
        by_category=[
            CountRow(key=key, label=CATEGORY_LABELS.get(key, key), count=count)
            for key, count in data["by_category"]
        ],
        by_via=[CountRow(key=key, label=VIA_LABELS.get(key, key), count=count) for key, count in data["by_via"]],
        by_user=[
            CountRow(
                key=str(uid) if uid else "system",
                label="تو" if uid == user.id else (name or "سیستم"),
                count=count,
            )
            for uid, name, count in data["by_user"]
        ],
        by_day=[DayCount(day=day, count=count) for day, count in data["by_day"]],
    )


@router.get("/options", response_model=ActivityOptions)
async def options(user: Person, session: SessionDep) -> ActivityOptions:
    """What the filters can be set to: the groups and ways in, and the people and books in view."""
    groups = await ActivityService(session).groups_for(user.id)
    return ActivityOptions(
        categories=[CountRow(key=key, label=label, count=0) for key, label in CATEGORY_LABELS.items()],
        vias=[CountRow(key=key, label=label, count=0) for key, label in VIA_LABELS.items()],
        people=[NamedId(id=uid, name="تو" if uid == user.id else (name or "—")) for uid, name in groups["people"]],
        books=[NamedId(id=bid, name=name) for bid, name in groups["books"]],
    )


@router.get("/export.csv")
async def export(user: Person, session: SessionDep, filters: Filters = FiltersDep) -> Response:
    """The same filtered log as a spreadsheet (up to 20,000 lines)."""
    content = await ActivityService(session).csv(user.id, filters)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kasbbook-activity.csv"'},
    )
