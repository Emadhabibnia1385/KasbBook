"""Proactive messages: the end-of-day summary and installment warnings.

Nothing here sends anything. It answers "what should this person be told, and
when" — the messenger adapter does the telling. That split is what lets the
same reminder reach Telegram today and Bale tomorrow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.money import ZERO
from ..books.models import Book, Membership
from ..budgets.service import BudgetService
from ..debts.models import Debt, Direction
from ..identity.models import Identity, Provider
from ..loans.models import Loan
from ..loans.service import LoanService
from ..reports import service as reports
from ..reports.service import ReportService


@dataclass(frozen=True)
class Reminder:
    """One thing to say to one person, on one messenger."""

    user_id: uuid.UUID
    kind: str            # digest | installment | debt_due
    text: str


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reports = ReportService(session)
        self.budgets = BudgetService(session)
        self.loans = LoanService(session)

    async def _books_of(self, user_id: uuid.UUID) -> Sequence[Book]:
        stmt = (
            select(Book)
            .join(Membership, Membership.book_id == Book.id)
            .where(
                Membership.user_id == user_id,
                Membership.is_active.is_(True),
                Book.is_active.is_(True),
            )
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def daily_digest(
        self, user_id: uuid.UUID, today: Optional[date] = None
    ) -> Optional[Reminder]:
        """What happened today, across every book — or nothing if nothing did."""
        when = today or date.today()
        period = reports.Period("امروز", when, when, "d")

        lines: List[str] = []
        anything = False

        for book in await self._books_of(user_id):
            summary = await self.reports.summary(book.id, user_id, period)
            if summary.income == ZERO and summary.expense == ZERO:
                continue

            anything = True
            lines.append(
                f"📚 {book.name}\n"
                f"  💰 {summary.income:,.0f}  🧾 {summary.expense:,.0f}  "
                f"➖ {summary.net:,.0f}"
            )

        if not anything:
            return None

        header = f"📊 خلاصهٔ {jalali.to_text(when)}"
        return Reminder(user_id, "digest", "\n\n".join([header] + lines))

    async def due_installments(
        self, user_id: uuid.UUID, days_ahead: int = 3, today: Optional[date] = None
    ) -> Optional[Reminder]:
        """Loans whose next payment falls inside the warning window."""
        when = today or date.today()
        cutoff = when + timedelta(days=max(0, days_ahead))

        lines: List[str] = []
        for book in await self._books_of(user_id):
            for loan in await self.loans.list_loans(book.id, user_id):
                if not loan.is_active:
                    continue

                progress = await self.loans.progress(book.id, user_id, loan)
                due = progress.next_due
                if due is not None and due <= cutoff:
                    lines.append(
                        f"• {loan.title}: {loan.installment_amount:,.0f}"
                        f" — {jalali.to_text(due)}"
                    )

        if not lines:
            return None
        return Reminder(user_id, "installment", "\n".join(["⏰ یادآور قسط", ""] + lines))

    async def due_debts(
        self, user_id: uuid.UUID, days_ahead: int = 3, today: Optional[date] = None
    ) -> Optional[Reminder]:
        when = today or date.today()
        cutoff = when + timedelta(days=max(0, days_ahead))

        lines: List[str] = []
        for book in await self._books_of(user_id):
            rows = (
                await self.session.execute(
                    select(Debt).where(
                        Debt.book_id == book.id,
                        Debt.settled_at.is_(None),
                        Debt.due_on.is_not(None),
                        Debt.due_on <= cutoff,
                    )
                )
            ).scalars().all()

            for debt in rows:
                arrow = "📥" if debt.direction is Direction.OWED_TO_ME else "📤"
                lines.append(
                    f"{arrow} {debt.person}: {debt.amount:,.0f}"
                    f" — {jalali.to_text(debt.due_on)}"
                )

        if not lines:
            return None
        return Reminder(user_id, "debt_due", "\n".join(["🤝 سررسید نزدیک", ""] + lines))

    async def for_user(
        self, user_id: uuid.UUID, today: Optional[date] = None
    ) -> List[Reminder]:
        """Everything worth saying to one person right now."""
        found = [
            await self.daily_digest(user_id, today),
            await self.due_installments(user_id, today=today),
            await self.due_debts(user_id, today=today),
        ]
        return [reminder for reminder in found if reminder is not None]

    async def recipients(self, provider: Provider) -> List[tuple]:
        """(user_id, external_id) for everyone reachable on this messenger."""
        rows = (
            await self.session.execute(
                # An identity is either attached or its row is gone: unlinking
                # removes it rather than flagging it, so presence is the filter.
                select(Identity).where(Identity.provider == provider)
            )
        ).scalars().all()
        return [(identity.user_id, identity.external_id) for identity in rows]
