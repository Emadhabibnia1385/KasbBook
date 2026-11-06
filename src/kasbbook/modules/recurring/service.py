"""Defining repeating transactions and materialising the ones that came due."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import calendars
from ...shared.calendars import Calendar
from ...shared.errors import BalanceError, NotFound, PermissionDenied, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ...shared.security import utcnow
from ..books.models import Book, BookType, Permission
from ..books.service import BookService
from ..ledger.models import Flow, Scope, Transaction
from ..ledger.service import LedgerService
from .models import Mode, OccurrenceStatus, Period, RecurringOccurrence, RecurringRule

# A rule that has somehow fallen years behind should not spend an afternoon
# writing transactions. This caps one catch-up run.
MAX_CATCH_UP = 400

SCOPE_FOR_BOOK = {
    BookType.PERSONAL: Scope.PERSONAL,
    BookType.BUSINESS: Scope.WORK,
    BookType.TEAM: Scope.TEAM,
    BookType.ORGANIZATION: Scope.TEAM,
}


def next_run_after(period: Period, current: date, cal: Calendar = calendars.JALALI) -> date:
    if period is Period.DAILY:
        return current + timedelta(days=1)
    if period is Period.WEEKLY:
        return current + timedelta(days=7)
    # A month means a month of the book's own calendar, so "the 5th of every month" stays the 5th.
    return cal.add_months(current, 1)


class RecurringService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)
        self.ledger = LedgerService(session)

    async def create(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        flow: Flow,
        category: str,
        amount,
        period: Period,
        starts_on: date,
        description: Optional[str] = None,
        mode: Mode = Mode.AUTO,
        first_booked: bool = False,
    ) -> RecurringRule:
        """Define a rule.

        `first_booked` says the person has just recorded the first date by
        hand (the add form does), so the schedule starts from the one after it
        rather than asking about a date they have already answered.
        """
        permission = (
            Permission.RECORD_INCOME if flow is Flow.INCOME else Permission.RECORD_EXPENSE
        )
        await self.books.require(book_id, user_id, permission)

        category = (category or "").strip()
        if not category:
            raise ValidationError("دستهٔ تراکنش لازم است")

        value = quantize(to_decimal(amount))
        if value <= ZERO:
            raise ValidationError("مبلغ باید بیشتر از صفر باشد")

        book = await self.books.get_book(book_id)
        first = (
            next_run_after(period, starts_on, calendars.of(book)) if first_booked else starts_on
        )
        rule = RecurringRule(
            book_id=book_id,
            created_by_user_id=user_id,
            flow=flow,
            category=category[:80],
            amount=value,
            description=description,
            period=period,
            next_run_on=first,
            mode=mode,
            last_run_on=starts_on if first_booked else None,
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def _owned(self, book_id: uuid.UUID, rule_id: uuid.UUID) -> RecurringRule:
        rule = await self.session.get(RecurringRule, rule_id)
        if rule is None or rule.book_id != book_id:
            raise NotFound("این قاعده پیدا نشد")
        return rule

    async def list_rules(
        self, book_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[RecurringRule]:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        return (
            await self.session.execute(
                select(RecurringRule)
                .where(RecurringRule.book_id == book_id)
                .order_by(RecurringRule.is_active.desc(), RecurringRule.next_run_on)
            )
        ).scalars().all()

    async def toggle(
        self, book_id: uuid.UUID, user_id: uuid.UUID, rule_id: uuid.UUID
    ) -> RecurringRule:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)

        rule = await self._owned(book_id, rule_id)
        rule.is_active = not rule.is_active
        await self.session.flush()
        return rule

    async def delete(
        self, book_id: uuid.UUID, user_id: uuid.UUID, rule_id: uuid.UUID
    ) -> None:
        """Delete the rule; anything it already booked stays."""
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)

        await self.session.delete(await self._owned(book_id, rule_id))
        await self.session.flush()

    async def _queue(self, rule: RecurringRule, due_on: date) -> Optional[RecurringOccurrence]:
        """Put one due date in the queue, once. A date already there (or already answered) is left alone."""
        known = await self.session.scalar(
            select(RecurringOccurrence.id).where(
                RecurringOccurrence.rule_id == rule.id, RecurringOccurrence.due_on == due_on
            )
        )
        if known is not None:
            return None
        occurrence = RecurringOccurrence(
            rule_id=rule.id, book_id=rule.book_id, due_on=due_on,
            status=OccurrenceStatus.PENDING,
        )
        self.session.add(occurrence)
        await self.session.flush()
        return occurrence

    async def update_rule(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        rule_id: uuid.UUID,
        mode: Optional[Mode] = None,
        amount=None,
        description: Optional[str] = None,
    ) -> RecurringRule:
        """Change how a rule behaves or what it records from now on; what it already recorded stays."""
        rule = await self._owned(book_id, rule_id)
        await self.books.require(book_id, user_id, self._permission_for(rule.flow))
        if mode is not None:
            rule.mode = mode
        if amount is not None:
            value = quantize(to_decimal(amount))
            if value <= ZERO:
                raise ValidationError("مبلغ باید بیشتر از صفر باشد")
            rule.amount = value
        if description is not None:
            rule.description = description.strip() or None
        await self.session.flush()
        return rule

    @staticmethod
    def _permission_for(flow: Flow) -> Permission:
        return Permission.RECORD_INCOME if flow is Flow.INCOME else Permission.RECORD_EXPENSE

    async def pending(
        self, book_id: uuid.UUID, user_id: uuid.UUID
    ) -> List[Tuple[RecurringOccurrence, RecurringRule]]:
        """The due dates of this book that are waiting for an answer, oldest first."""
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        rows = (
            await self.session.execute(
                select(RecurringOccurrence, RecurringRule)
                .join(RecurringRule, RecurringRule.id == RecurringOccurrence.rule_id)
                .where(
                    RecurringOccurrence.book_id == book_id,
                    RecurringOccurrence.status == OccurrenceStatus.PENDING,
                )
                .order_by(RecurringOccurrence.due_on, RecurringOccurrence.created_at)
            )
        ).all()
        return [(occurrence, rule) for occurrence, rule in rows]

    async def _decidable(
        self, book_id: uuid.UUID, user_id: uuid.UUID, occurrence_id: uuid.UUID
    ) -> Tuple[RecurringOccurrence, RecurringRule]:
        """The waiting date, locked so two people answering at once do not both record it."""
        occurrence = (
            await self.session.execute(
                select(RecurringOccurrence)
                .where(RecurringOccurrence.id == occurrence_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if occurrence is None or occurrence.book_id != book_id:
            raise NotFound("این مورد پیدا نشد")
        rule = await self.session.get(RecurringRule, occurrence.rule_id)
        if rule is None:
            raise NotFound("این مورد پیدا نشد")
        await self.books.require(book_id, user_id, self._permission_for(rule.flow))
        if occurrence.status is not OccurrenceStatus.PENDING:
            raise ValidationError("این مورد قبلاً تعیین تکلیف شده است.")
        return occurrence, rule

    async def confirm(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        occurrence_id: uuid.UUID,
        amount=None,
    ) -> Transaction:
        """Say yes to one waiting date: it is recorded on its own day, by whoever confirmed it.

        The amount may be changed on the way (a bill is rarely the same twice);
        the rule keeps its own amount for the next date.
        """
        occurrence, rule = await self._decidable(book_id, user_id, occurrence_id)
        value = rule.amount
        if amount is not None:
            value = quantize(to_decimal(amount))
            if value <= ZERO:
                raise ValidationError("مبلغ باید بیشتر از صفر باشد")
        book = await self.books.get_book(book_id)
        transaction = await self.ledger.record(
            book_id=book_id,
            actor_user_id=user_id,
            flow=rule.flow,
            scope=SCOPE_FOR_BOOK.get(book.type, Scope.WORK),
            category=rule.category,
            amount=value,
            description=rule.description,
            occurred_on=occurrence.due_on,
        )
        occurrence.status = OccurrenceStatus.CONFIRMED
        occurrence.transaction_id = transaction.id
        occurrence.decided_by_id = user_id
        occurrence.decided_at = utcnow()
        await self.session.flush()
        return transaction

    async def skip(
        self, book_id: uuid.UUID, user_id: uuid.UUID, occurrence_id: uuid.UUID
    ) -> None:
        """Say no to one waiting date: nothing is recorded, and the rule carries on with the next."""
        occurrence, _ = await self._decidable(book_id, user_id, occurrence_id)
        occurrence.status = OccurrenceStatus.SKIPPED
        occurrence.decided_by_id = user_id
        occurrence.decided_at = utcnow()
        await self.session.flush()

    async def run_due(self, until: Optional[date] = None) -> "RecurringRun":
        """
        Book every rule that has come due, catching up on anything missed.

        Safe to call repeatedly: a rule only fires for dates it has not already
        produced, because its own next-due date moves forward as it goes.

        One rule's trouble is that rule's alone. This used to raise on the
        first rule it could not book, which rolled back every other rule in the
        same run — and since nothing ever called it, nobody noticed that rent
        and salaries defined "once" were never booked at all.

        A missed date inside a period someone has closed is skipped, not
        forced in: the closed month's payslips were computed without it. The
        skip is reported so the owner can record it in an open month by hand.
        A rule whose author can no longer record in the book is paused and
        reported once, rather than retried — and reported — every tick.
        """
        cutoff = until or date.today()
        run = RecurringRun()

        rules = (
            await self.session.execute(
                select(RecurringRule)
                .where(
                    RecurringRule.is_active.is_(True),
                    RecurringRule.next_run_on <= cutoff,
                )
                # One bot process runs per messenger, and each has a reminder
                # loop. Without the lock two of them could book the same date
                # twice; with it the second skips what the first is holding.
                # SQLite has no FOR UPDATE and is single-writer anyway.
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()

        for rule in rules:
            book = await self.session.get(Book, rule.book_id)
            if book is None or not book.is_active:
                continue

            needed = (
                Permission.RECORD_INCOME if rule.flow is Flow.INCOME
                else Permission.RECORD_EXPENSE
            )
            try:
                await self.books.require(rule.book_id, rule.created_by_user_id, needed)
            except (NotFound, PermissionDenied):
                rule.is_active = False
                run.paused.append(rule)
                continue

            when = rule.next_run_on
            fired = 0
            while when <= cutoff and fired < MAX_CATCH_UP:
                if rule.mode is Mode.ASK:
                    # Nothing is recorded until somebody says so; the date waits in a queue.
                    queued = await self._queue(rule, when)
                    if queued is not None:
                        run.pending.append((rule, queued))
                    fired += 1
                    when = next_run_after(rule.period, when, calendars.of(book))
                    continue
                try:
                    tx = await self.ledger.record(
                        book_id=rule.book_id,
                        actor_user_id=rule.created_by_user_id,
                        flow=rule.flow,
                        scope=SCOPE_FOR_BOOK.get(book.type, Scope.WORK),
                        category=rule.category,
                        amount=rule.amount,
                        description=rule.description,
                        occurred_on=when,
                    )
                except PermissionDenied:
                    # The author's permission was just confirmed, so this is
                    # the ledger refusing a date inside a closed period. Every
                    # check in record() runs before it writes, so nothing is
                    # left half-booked.
                    run.skipped.append((rule, when))
                except (ValidationError, BalanceError):
                    # The rule itself no longer fits the book — its category
                    # now belongs to the other flow, say. Retrying will not
                    # change that, so it waits, paused, at the date it failed.
                    rule.is_active = False
                    run.paused.append(rule)
                    break
                else:
                    run.booked.append((rule, tx))
                fired += 1
                when = next_run_after(rule.period, when, calendars.of(book))

            rule.next_run_on = when
            rule.last_run_on = cutoff

        await self.session.flush()
        return run


@dataclass
class RecurringRun:
    """What one pass did, for the reminder loop to tell the books' owners."""

    booked: List[Tuple[RecurringRule, Transaction]] = field(default_factory=list)
    skipped: List[Tuple[RecurringRule, date]] = field(default_factory=list)
    paused: List[RecurringRule] = field(default_factory=list)
    # Dates of rules that ask first, now waiting for an answer.
    pending: List[Tuple[RecurringRule, RecurringOccurrence]] = field(default_factory=list)
