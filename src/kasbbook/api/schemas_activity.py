"""Response shapes for the activity log («رویدادها»)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from .schemas import Model


class ActivityItem(Model):
    id: uuid.UUID
    at: datetime
    # Who did it: null when the system did, or when the account has since been closed.
    user_id: Optional[uuid.UUID] = None
    user_name: Optional[str] = None
    is_me: bool = False
    # web (the panel), api (a program with the person's key), bot (a messenger), system
    via: str
    via_label: str
    book_id: Optional[uuid.UUID] = None
    book_name: Optional[str] = None
    category: str
    category_label: str
    action: str
    summary: str


class ActivityPage(Model):
    items: List[ActivityItem]
    total: int


class CountRow(Model):
    key: str
    label: str
    count: int


class DayCount(Model):
    day: date
    count: int


class ActivitySummary(Model):
    total: int
    by_category: List[CountRow]
    by_via: List[CountRow]
    by_user: List[CountRow]
    by_day: List[DayCount]


class NamedId(Model):
    id: uuid.UUID
    name: str


class ActivityOptions(Model):
    categories: List[CountRow]
    vias: List[CountRow]
    people: List[NamedId]
    books: List[NamedId]
