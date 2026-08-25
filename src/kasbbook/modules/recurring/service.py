"""Defining repeating transactions and materialising the ones that came due."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Book, BookType, Permission
from ..books.service import BookService
from ..ledger.models import Flow, Scope
from ..ledger.service import LedgerService
from .models import Period, RecurringRule

# A rule that has somehow fallen years behind should not spend an afternoon
# writing transactions. This caps one catch-up run.
MAX_CATCH_UP = 400

SCOPE_FOR_BOOK = {
    BookType.PERSONAL: Scope.PERSONAL,
    BookType.BUSINESS: Scope.WORK,
    BookType.TEAM: Scope.TEAM,
    BookType.ORGANIZATION: Scope.TEAM,
}


def next_run_after(period: Period, current: date) -> date:
    if period is Period.DAILY:
        return current + timedelta(days=1)
    if period is Period.WEEKLY:
        return current + timedelta(days=7)
    # A month means a Jalali month, so "the 5th of every month" stays the 5th.
    return jalali.add_months(current, 1)


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
    ) -> RecurringRule:
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

        rule = RecurringRule(
            book_id=book_id,
            created_by_user_id=user_id,
            flow=flow,
            category=category[:80],
            amount=value,
            description=description,
            period=period,
            next_run_on=starts_on,
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

    async def run_due(self, until: Optional[date] = None) -> int:
        """
        Book every rule that has come due, catching up on anything missed.

        Returns how many transactions were created. Safe to call repeatedly: a
        rule only fires for dates it has not already produced, because its own
        next-due date moves forward as it goes.
        """
        cutoff = until or date.today()
        created = 0

        rules = (
            await self.session.execute(
                select(RecurringRule).where(
                    RecurringRule.is_active.is_(True),
                    RecurringRule.next_run_on <= cutoff,
                )
            )
        ).scalars().all()

        for rule in rules:
            book = await self.session.get(Book, rule.book_id)
            if book is None:
                continue

            when = rule.next_run_on
            fired = 0
            while when <= cutoff and fired < MAX_CATCH_UP:
                await self.ledger.record(
                    book_id=rule.book_id,
                    actor_user_id=rule.created_by_user_id,
                    flow=rule.flow,
                    scope=SCOPE_FOR_BOOK.get(book.type, Scope.WORK),
                    category=rule.category,
                    amount=rule.amount,
                    description=rule.description,
                    occurred_on=when,
                )
                created += 1
                fired += 1
                when = next_run_after(rule.period, when)

            rule.next_run_on = when
            rule.last_run_on = cutoff

        await self.session.flush()
        return created
