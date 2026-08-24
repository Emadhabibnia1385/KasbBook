"""Setting ceilings and reporting how much of one is used."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import Flow, Transaction
from .models import Budget, BudgetKind

# How close to the ceiling counts as worth mentioning.
WARN_AT_PERCENT = 80


@dataclass(frozen=True)
class BudgetStatus:
    budget: Budget
    label: str
    limit: Decimal
    spent: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.limit - self.spent

    @property
    def percent(self) -> int:
        return int(round(self.spent * 100 / self.limit)) if self.limit else 0

    @property
    def over(self) -> bool:
        return self.spent > self.limit


class BudgetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    async def set_budget(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: BudgetKind,
        target: str,
        amount,
    ) -> Budget:
        await self.books.require(book_id, user_id, Permission.MANAGE_BUDGETS)

        value = quantize(to_decimal(amount))
        if value <= ZERO:
            raise ValidationError("سقف بودجه باید بیشتر از صفر باشد")

        target = (target or "").strip()
        if not target:
            raise ValidationError("هدف بودجه مشخص نیست")

        existing = await self._find(book_id, kind, target)
        if existing is not None:
            existing.amount = value
            await self.session.flush()
            return existing

        budget = Budget(book_id=book_id, kind=kind, target=target, amount=value)
        self.session.add(budget)
        await self.session.flush()
        return budget

    async def _find(
        self, book_id: uuid.UUID, kind: BudgetKind, target: str
    ) -> Optional[Budget]:
        return (
            await self.session.execute(
                select(Budget).where(
                    Budget.book_id == book_id,
                    Budget.kind == kind,
                    Budget.target == target,
                )
            )
        ).scalar_one_or_none()

    async def delete(self, book_id: uuid.UUID, user_id: uuid.UUID, budget_id: uuid.UUID) -> None:
        await self.books.require(book_id, user_id, Permission.MANAGE_BUDGETS)

        budget = await self.session.get(Budget, budget_id)
        if budget is None or budget.book_id != book_id:
            raise NotFound("این بودجه پیدا نشد")

        await self.session.delete(budget)
        await self.session.flush()

    async def list_budgets(self, book_id: uuid.UUID, user_id: uuid.UUID) -> Sequence[Budget]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(Budget).where(Budget.book_id == book_id).order_by(Budget.target)
            )
        ).scalars().all()

    async def status(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        year: Optional[int] = None,
        month: Optional[int] = None,
        today: Optional[date] = None,
    ) -> List[BudgetStatus]:
        """How much of each ceiling this Jalali month has used."""
        budgets = await self.list_budgets(book_id, user_id)
        if not budgets:
            return []

        if year is None or month is None:
            year, month, _ = jalali.to_parts(today or date.today())
        starts_on, ends_on = jalali.month_range(year, month)

        rows = (
            await self.session.execute(
                select(Transaction).where(
                    Transaction.book_id == book_id,
                    Transaction.occurred_on >= starts_on,
                    Transaction.occurred_on <= ends_on,
                )
            )
        ).scalars().all()

        out: List[BudgetStatus] = []
        for budget in budgets:
            spent = ZERO
            for tx in rows:
                if budget.kind is BudgetKind.CATEGORY:
                    if tx.category == budget.target:
                        spent += tx.converted_amount
                elif tx.flow.value == budget.target:
                    spent += tx.converted_amount

            label = (
                budget.target
                if budget.kind is BudgetKind.CATEGORY
                else ("درآمد" if budget.target == Flow.INCOME.value else "هزینه")
            )
            out.append(
                BudgetStatus(budget, label, quantize(budget.amount), quantize(spent))
            )

        return out

    async def warning_for(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        category: str,
        flow: Flow,
        on: date,
    ) -> Optional[str]:
        """A one-line nudge when a just-recorded amount crosses a ceiling."""
        year, month, _ = jalali.to_parts(on)
        for status in await self.status(book_id, user_id, year, month):
            hits = (
                status.budget.kind is BudgetKind.CATEGORY
                and status.budget.target == category
            ) or (
                status.budget.kind is BudgetKind.FLOW
                and status.budget.target == flow.value
            )
            if not hits:
                continue

            if status.over:
                return f"⛔ بودجهٔ «{status.label}» {status.spent - status.limit:,.0f} رد شد."
            if status.percent >= WARN_AT_PERCENT:
                return f"⚠️ {status.percent}% از بودجهٔ «{status.label}» مصرف شده."
        return None
