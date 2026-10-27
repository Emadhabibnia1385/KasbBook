"""Proactive messages: the end-of-day summary and the warnings that go with it.

Nothing here sends anything. It answers "what should this person be told" — the
messenger adapter does the telling and `apps/bot/reminders.py` decides when.
That split is what lets the same reminder reach Telegram today and Bale
tomorrow.

This is the only screen in the product nobody went looking for, which makes it
the only one where being dull costs something. Two rules follow from that, and
every function below obeys them: say nothing when there is nothing to say, and
when there is, say the thing a person could act on rather than the thing that
is easiest to count.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.money import ZERO
from ..books.models import Book, Membership
from ..budgets.service import WARN_AT_PERCENT, BudgetService
from ..debts.models import Direction
from ..debts.service import DebtService
from ..identity.models import Identity, Provider, User
from ..loans.service import LoanService
from ..reports import service as reports
from ..reports.service import ReportService

if TYPE_CHECKING:
    from ..recurring.service import RecurringRun


# Past this many lines a section is cut short. Whole rules and whole budgets,
# not dates: each line already sums one of them, so this only bites on a book
# with dozens.
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


def _shown(lines: List[str], more: str = "قاعدهٔ دیگر") -> List[str]:
    """The first few lines of a section, and an honest count of the rest."""
    if len(lines) <= NOTICE_RULES_SHOWN:
        return lines
    rest = len(lines) - NOTICE_RULES_SHOWN
    return lines[:NOTICE_RULES_SHOWN] + [f"… و {rest} {more}"]


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
        self.debts = DebtService(session)

    async def today_for(
        self,
        user_id: uuid.UUID,
        today: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> date:
        """The day where this person is, which is the only day they date things by.

        The server runs UTC and Tehran is three and a half hours ahead, so the
        server's date turns over at half past three in the morning there. Two
        things went wrong on it. The figures came from whichever day the server
        was on, which for those hours is yesterday. And "already sent today",
        keyed on it, cut one person's day into two keys — a second key is a
        second copy of the same message, which is the one failure this module
        exists to avoid.

        The loop asks for this rather than computing it, so the day a message
        is about and the day it is deduplicated on cannot drift apart.
        """
        if today is not None:
            return today

        user = await self.session.get(User, user_id)
        return jalali.today_in(
            user.timezone if user is not None else jalali.DEFAULT_TIMEZONE, now
        )

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

    async def _budget_pressure(
        self, book: Book, user_id: uuid.UUID, when: date
    ) -> List[str]:
        """Which ceilings this book's month is pressing against, and how much month is left.

        A percentage on its own is not a reason to do anything: 85% spent is
        alarming on the fifth of the month and ordinary on the twenty-eighth.
        The days left are what turn the figure into a decision, which is the
        whole claim this message makes on somebody's evening.

        The threshold and the wording are the budgets service's own, imported
        rather than restated, so the nudge shown when a transaction is recorded
        and this line never start disagreeing about what "close" means.
        """
        # Jalali first, Gregorian bounds after — `status` runs the query.
        year, month, _ = jalali.to_parts(when)
        _, ends_on = jalali.month_range(year, month)
        left = (ends_on - when).days

        lines: List[str] = []
        for status in await self.budgets.status(book.id, user_id, year, month):
            if status.over:
                lines.append(
                    f"⛔ بودجهٔ «{status.label}» {status.spent - status.limit:,.0f} رد شد."
                )
            elif status.percent >= WARN_AT_PERCENT:
                rest = f"{left} روز تا پایان ماه" if left else "امروز آخرین روز ماه است"
                lines.append(
                    f"⚠️ {status.percent}% از بودجهٔ «{status.label}» مصرف شده — {rest}."
                )
        return _shown(lines, "بودجهٔ دیگر")

    async def daily_digest(
        self,
        user_id: uuid.UUID,
        today: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> Optional[Reminder]:
        """What today did, across every book, and what it is pressing against.

        Each book's own day, not the server's. A transaction is dated where the
        person is; asking the server what day it is made the digest look at
        tomorrow for the three and a half hours after midnight in Tehran, and
        report a busy evening as a quiet one. The heading is the *person's* day,
        because one message has one date on it and they are the one reading it.

        Quiet when the day was quiet, which is not politeness but arithmetic: a
        message that says "nothing happened" every evening is one people stop
        opening, and then the evening something did happen is not read either.

        The budget lines ride on a book the day actually touched, for the same
        reason. A ceiling that is over stays over until the month ends, and
        repeating that to somebody who recorded nothing is the noise this
        message cannot afford. Said beside the day's own figures, it is about
        the spending that just happened.
        """
        blocks: List[str] = []

        for book in await self._books_of(user_id):
            when = today or jalali.today_in(book.timezone, now)
            period = reports.Period("امروز", when, when, "d")
            summary = await self.reports.summary(book.id, user_id, period)
            if summary.income == ZERO and summary.expense == ZERO:
                continue

            # Only the lines that carry a figure. A day with expense and no
            # income says so in two lines; the third would be «درآمد: 0» and
            # the fourth would be the expense again with a minus in front of
            # it, and padding a message nobody asked for is how it stops being
            # read. The daily list drops its own empty lines for this reason.
            lines = [f"📚 {book.name}"]
            if summary.income != ZERO:
                lines.append(f"💰 درآمد: {summary.income:,.0f}")
            if summary.expense != ZERO:
                lines.append(f"🧾 هزینه: {summary.expense:,.0f}")
            if summary.income != ZERO and summary.expense != ZERO:
                lines.append(f"💾 مانده امروز: {summary.net:,.0f}")
            lines += await self._budget_pressure(book, user_id, when)
            blocks.append("\n".join(lines))

        if not blocks:
            return None

        day = await self.today_for(user_id, today, now)
        header = f"📊 خلاصهٔ امروز · {jalali.to_text(day)}"
        return Reminder(user_id, "digest", "\n\n".join([header] + blocks))

    async def due_installments(
        self,
        user_id: uuid.UUID,
        days_ahead: int = 3,
        today: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> Optional[Reminder]:
        """Loans whose next payment falls inside the warning window."""
        when = await self.today_for(user_id, today, now)
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
                        f" — سررسید {jalali.to_text(due)}"
                    )

        if not lines:
            return None
        return Reminder(user_id, "installment", "\n".join(["⏰ یادآور قسط", ""] + lines))

    async def due_debts(
        self,
        user_id: uuid.UUID,
        days_ahead: int = 3,
        today: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> Optional[Reminder]:
        """Debts, either way round, close enough to the date to do something about.

        Which way a debt runs is said in words. An arrow is a decoration here —
        there is no column heading above it, the way there is on the debts
        screen, and getting it backwards is how somebody chases a person they
        owe money to.
        """
        when = await self.today_for(user_id, today, now)
        cutoff = when + timedelta(days=max(0, days_ahead))

        lines: List[str] = []
        for book in await self._books_of(user_id):
            # `list_debts` is the one place that knows a settled debt has left
            # the position. This used to select from the table and say it a
            # second time, which is a copy of a rule waiting to disagree.
            for debt in await self.debts.list_debts(book.id, user_id):
                if debt.due_on is None or debt.due_on > cutoff:
                    continue

                side = (
                    f"📥 طلب من از {debt.person}"
                    if debt.direction is Direction.OWED_TO_ME
                    else f"📤 بدهی من به {debt.person}"
                )
                lines.append(
                    f"{side}: {debt.amount:,.0f} — سررسید {jalali.to_text(debt.due_on)}"
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
        self,
        user_id: uuid.UUID,
        today: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> List[Reminder]:
        """Everything worth saying to one person right now, in reading order.

        Which reminders exist, and the person's own settings that decide it,
        are read here rather than in the loop. The loop's job is *when* to
        speak; it had grown a copy of *what* to say, and a copy is a rule that
        the web panel or a second messenger would have to be given again.
        """
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            return []

        found = [
            await self.daily_digest(user_id, today, now) if user.digest_enabled else None,
            await self.due_installments(user_id, user.reminder_days, today, now),
            await self.due_debts(user_id, user.reminder_days, today, now),
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
