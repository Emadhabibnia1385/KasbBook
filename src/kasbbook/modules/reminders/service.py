"""Proactive messages: the end-of-day summary and installment warnings.

Nothing here sends anything. It answers "what should this person be told, and
when" — the messenger adapter does the telling. That split is what lets the
same reminder reach Telegram today and Bale tomorrow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.money import ZERO
from ..books.models import Book, Membership
from ..budgets.service import BudgetService
from ..debts.models import Debt, Direction
from ..identity.models import Identity, Provider
from ..loans.service import LoanService
from ..reports import service as reports
from ..reports.service import ReportService

if TYPE_CHECKING:
    from ..recurring.service import RecurringRun


# Past this many rules a section is cut short. Rules, not dates: each line
# already sums a whole rule, so this only bites on a book with dozens of them.
NOTICE_RULES_SHOWN = 15


def _rule_line(rule, dates) -> str:
    """One rule's late or skipped dates, as one line: count, span and total."""
    dates = sorted(dates)
    total = sum((amount for _, amount in dates), ZERO)
    first, last = dates[0][0], dates[-1][0]
    if len(dates) == 1:
        return f"• {rule.category}: {total:,.0f} — {jalali.to_text(first)}"
    return (
        f"• {rule.category}: {len(dates)} بار، {jalali.to_text(first)} تا "
        f"{jalali.to_text(last)} — جمع {total:,.0f}"
    )


def _shown(lines: List[str]) -> List[str]:
    if len(lines) <= NOTICE_RULES_SHOWN:
        return lines
    rest = len(lines) - NOTICE_RULES_SHOWN
    return lines[:NOTICE_RULES_SHOWN] + [f"… و {rest} قاعدهٔ دیگر"]


@dataclass(frozen=True)
class Reminder:
    """One thing to say to one person, on one messenger."""

    user_id: uuid.UUID
    kind: str            # digest | installment | debt_due | recurring
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
        """What happened today, across every book — or nothing if nothing did.

        Each book's own day, not the server's. A transaction is dated where the
        person is; asking the server what day it is made the digest look at
        tomorrow for the three and a half hours after midnight in Tehran, and
        report a busy evening as a quiet one.
        """
        lines: List[str] = []
        anything = False
        header_day = today

        for book in await self._books_of(user_id):
            when = today or jalali.today_in(book.timezone)
            period = reports.Period("امروز", when, when, "d")
            summary = await self.reports.summary(book.id, user_id, period)
            if summary.income == ZERO and summary.expense == ZERO:
                continue

            anything = True
            if header_day is None:
                header_day = when
            lines.append(
                f"📚 {book.name}\n"
                f"  💰 {summary.income:,.0f}  🧾 {summary.expense:,.0f}  "
                f"➖ {summary.net:,.0f}"
            )

        if not anything:
            return None

        header = f"📊 خلاصهٔ {jalali.to_text(header_day)}"
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

    async def recurring_notices(
        self, run: "RecurringRun", today: Optional[date] = None
    ) -> List[Reminder]:
        """Tell each book's owner what a recurring pass did that they would not expect.

        A rule booked on its own day needs no message — the digest shows it.
        What does need one: a date booked late (the first run after downtime,
        or after this loop started booking at all), a date skipped because its
        period was closed, and a rule paused because it can no longer book.
        Silence about any of those would leave the owner believing the books
        hold what they asked for.
        """
        when = today or date.today()

        # Grouped per rule, not per date. A daily rule a year behind books 365
        # dates; one line each passes the messenger's message limit, the send
        # fails, and the owner hears nothing at all.
        late: dict = {}
        skipped: dict = {}
        for rule, tx in run.booked:
            if tx.occurred_on < when:
                late.setdefault(rule, []).append((tx.occurred_on, tx.converted_amount))
        for rule, day in run.skipped:
            skipped.setdefault(rule, []).append((day, rule.amount))

        by_book: dict = {}

        def lines_for(book_id):
            return by_book.setdefault(book_id, {"late": [], "skipped": [], "paused": []})

        for rule, dates in late.items():
            lines_for(rule.book_id)["late"].append(_rule_line(rule, dates))
        for rule, dates in skipped.items():
            lines_for(rule.book_id)["skipped"].append(_rule_line(rule, dates))
        for rule in run.paused:
            lines_for(rule.book_id)["paused"].append(f"• {rule.category}: {rule.amount:,.0f}")

        notices: List[Reminder] = []
        for book_id, found in by_book.items():
            book = await self.session.get(Book, book_id)
            if book is None:
                continue
            parts = [f"🔁 تراکنش‌های تکرارشونده — دفتر «{book.name}»"]
            if found["late"]:
                parts.append("ثبت شد، با تاریخ خودش:\n" + "\n".join(_shown(found["late"])))
            if found["skipped"]:
                parts.append(
                    "ثبت نشد، چون دورهٔ آن روز بسته است. اگر لازم است، "
                    "آن را در یک دورهٔ باز دستی ثبت کنید:\n" + "\n".join(_shown(found["skipped"]))
                )
            if found["paused"]:
                parts.append(
                    "متوقف شد، چون سازندهٔ آن دیگر نمی‌تواند در این دفتر ثبت کند "
                    "یا دسته‌اش با این دفتر جور نیست. از بخش «تکرارشونده» "
                    "اصلاح و دوباره فعالش کنید:\n" + "\n".join(_shown(found["paused"]))
                )
            notices.append(Reminder(book.owner_user_id, "recurring", "\n\n".join(parts)))
        return notices

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
