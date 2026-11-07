"""One row per thing a person (or a program on their behalf) did."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey

# How the action reached the system.
VIA_WEB = "web"      # the person, in the panel
VIA_API = "api"      # a program, with the person's API key
VIA_BOT = "bot"      # the person, in a messenger
VIA_SYSTEM = "system"  # nobody asked: a schedule, a reminder, a sync of its own


class ActivityEvent(UUIDPrimaryKey, Timestamped, Base):
    """Append-only. Written as a side effect of the change itself, so nothing can change unrecorded."""

    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_user_time", "user_id", "created_at"),
        Index("ix_activity_book_time", "book_id", "created_at"),
        Index("ix_activity_category_time", "category", "created_at"),
    )

    # Who. Kept as a plain reference: a closed account leaves its history behind, without a name.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    via: Mapped[str] = mapped_column(String(8), nullable=False, default=VIA_WEB)
    book_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="SET NULL")
    )
    # transactions, categories, budgets, debts, loans, recurring, payroll, treasury, members, books,
    # wallet, portfolio, capital, account
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    # transaction.created, category.renamed, ...
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    # The sentence a person reads: «ثبت درآمد ۱٬۳۰۰٬۰۰۰ تومان — فروش».
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
