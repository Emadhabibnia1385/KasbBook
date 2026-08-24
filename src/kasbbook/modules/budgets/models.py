"""Monthly spending ceilings.

A budget informs, it never blocks. Recording a transaction that crosses one
says so and carries on: the money already moved, and a bookkeeping tool that
refuses to record reality is worse than useless.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class BudgetKind(str, enum.Enum):
    """What the ceiling applies to."""

    CATEGORY = "category"   # one named category
    FLOW = "flow"           # everything flowing one way in the book


class Budget(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "budgets"
    __table_args__ = (
        # One ceiling per target: setting it again raises or lowers the same one
        # rather than quietly stacking a second.
        UniqueConstraint("book_id", "kind", "target", name="uq_budget_target"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[BudgetKind] = mapped_column(
        Enum(BudgetKind, native_enum=False, length=16), nullable=False
    )
    # A category name, or a Flow value when kind is FLOW.
    target: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Money] = mapped_column(Money, nullable=False)
