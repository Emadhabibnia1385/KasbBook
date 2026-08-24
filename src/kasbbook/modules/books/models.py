"""Books and who may do what inside them.

A `Book` is the boundary every number lives behind: personal money, a personal
business, and a team each get their own. A transaction belongs to exactly one
book, which is what keeps team income from ever being counted as personal income.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class BookType(str, enum.Enum):
    PERSONAL = "personal"
    BUSINESS = "business"
    TEAM = "team"
    ORGANIZATION = "organization"


class Role(str, enum.Enum):
    """Ordered from most to least authority."""

    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(str, enum.Enum):
    VIEW_REPORTS = "view_reports"
    VIEW_TRANSACTIONS = "view_transactions"
    RECORD_INCOME = "record_income"
    RECORD_EXPENSE = "record_expense"
    EDIT_TRANSACTION = "edit_transaction"
    DELETE_TRANSACTION = "delete_transaction"
    APPROVE_EXPENSE = "approve_expense"
    MANAGE_TREASURY = "manage_treasury"
    MANAGE_SHARES = "manage_shares"
    MANAGE_PAYROLL = "manage_payroll"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_BUDGETS = "manage_budgets"
    EXPORT = "export"
    VIEW_OTHERS_PAY = "view_others_pay"
    LOCK_PERIOD = "lock_period"


# What each role may do. Deliberately explicit rather than computed from an
# ordering, so widening a role is a visible, reviewable change.
ROLE_PERMISSIONS = {
    Role.OWNER: set(Permission),
    Role.ADMIN: set(Permission) - {Permission.LOCK_PERIOD},
    Role.ACCOUNTANT: {
        Permission.VIEW_REPORTS,
        Permission.VIEW_TRANSACTIONS,
        Permission.RECORD_INCOME,
        Permission.RECORD_EXPENSE,
        Permission.EDIT_TRANSACTION,
        Permission.APPROVE_EXPENSE,
        Permission.MANAGE_TREASURY,
        Permission.MANAGE_PAYROLL,
        Permission.MANAGE_BUDGETS,
        Permission.EXPORT,
        Permission.VIEW_OTHERS_PAY,
    },
    Role.MEMBER: {
        Permission.VIEW_REPORTS,
        Permission.VIEW_TRANSACTIONS,
        Permission.RECORD_INCOME,
        Permission.RECORD_EXPENSE,
    },
    Role.VIEWER: {
        Permission.VIEW_REPORTS,
        Permission.VIEW_TRANSACTIONS,
    },
}


class Book(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "books"
    __table_args__ = (Index("ix_books_owner", "owner_user_id"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[BookType] = mapped_column(
        Enum(BookType, native_enum=False, length=16), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="IRT")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Tehran")
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="fa")
    calendar: Mapped[str] = mapped_column(String(16), nullable=False, default="jalali")
    treasury_percent: Mapped[Optional[object]] = mapped_column(Money, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="book", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Book {self.type.value}:{self.name!r}>"


class Membership(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("book_id", "user_id", name="one_membership_per_user_per_book"),
        Index("ix_memberships_user", "user_id"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    book: Mapped[Book] = relationship(back_populates="memberships", lazy="selectin")

    @property
    def permissions(self) -> set:
        return ROLE_PERMISSIONS[self.role] if self.is_active else set()
