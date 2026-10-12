"""Who owes whom, kept away from the ledger on purpose."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from .models import Debt, Direction


@dataclass(frozen=True)
class DebtTotals:
    owed_to_me: Decimal
    i_owe: Decimal

    @property
    def net(self) -> Decimal:
        return self.owed_to_me - self.i_owe


class DebtService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    async def create(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        person: str,
        direction: Direction,
        amount,
        note: Optional[str] = None,
        due_on: Optional[date] = None,
    ) -> Debt:
        await self.books.require(book_id, user_id, Permission.RECORD_INCOME)

        person = (person or "").strip()
        if not person:
            raise ValidationError("نام طرف حساب لازم است")

        value = quantize(to_decimal(amount))
        # Zero was let through while loans and recurring rules refused it, and a
        # debt of nothing sat in the list as a position.
        if value <= ZERO:
            raise ValidationError("مبلغ باید بیشتر از صفر باشد؛ مثلاً ۵۰۰ هزار.")

        debt = Debt(
            book_id=book_id,
            person=person[:80],
            direction=direction,
            amount=value,
            note=note,
            due_on=due_on,
        )
        self.session.add(debt)
        await self.session.flush()
        return debt

    async def _owned(self, book_id: uuid.UUID, debt_id: uuid.UUID) -> Debt:
        debt = await self.session.get(Debt, debt_id)
        if debt is None or debt.book_id != book_id:
            raise NotFound("این مورد پیدا نشد")
        return debt

    async def settle(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        debt_id: uuid.UUID,
        record_transaction: bool = False,
    ) -> Debt:
        """Close the debt, and — only when asked — record the money moving.

        Whether settling is income or expense depends on what was recorded
        when the debt arose: if the sale on credit, or the purchase, is already
        in the books, booking the payment as well counts it twice. The service
        cannot know, so it does not guess; the caller asks the person (owner
        decision D-2) and the default is to close the debt only.
        """
        await self.books.require(book_id, user_id, Permission.RECORD_INCOME)

        debt = await self._owned(book_id, debt_id)
        if debt.settled_at is not None:
            # A second press must not record the money a second time.
            raise ValidationError(f"«{debt.person}» قبلاً تسویه شده است.")

        if record_transaction:
            from ..ledger.models import Flow
            from ..ledger.service import LedgerService

            received = debt.direction is Direction.OWED_TO_ME
            await LedgerService(self.session).record(
                book_id=book_id,
                actor_user_id=user_id,
                flow=Flow.INCOME if received else Flow.EXPENSE,
                scope=None,
                category="تسویه طلب" if received else "تسویه بدهی",
                amount=debt.amount,
                description=f"تسویه با {debt.person}",
            )

        debt.settled_at = datetime.now(timezone.utc)
        await self.session.flush()
        return debt

    async def delete(
        self, book_id: uuid.UUID, user_id: uuid.UUID, debt_id: uuid.UUID
    ) -> None:
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)

        await self.session.delete(await self._owned(book_id, debt_id))
        await self.session.flush()

    async def list_debts(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        include_settled: bool = False,
    ) -> Sequence[Debt]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)

        stmt = select(Debt).where(Debt.book_id == book_id)
        if not include_settled:
            stmt = stmt.where(Debt.settled_at.is_(None))

        stmt = stmt.order_by(Debt.due_on.is_(None), Debt.due_on, Debt.created_at.desc())
        return (await self.session.execute(stmt)).scalars().all()

    async def totals(self, book_id: uuid.UUID, user_id: uuid.UUID) -> DebtTotals:
        """Only open debts count: a settled one is history, not a position."""
        owed = ZERO
        mine = ZERO

        for debt in await self.list_debts(book_id, user_id, include_settled=False):
            if debt.direction is Direction.OWED_TO_ME:
                owed += debt.amount
            else:
                mine += debt.amount

        return DebtTotals(quantize(owed), quantize(mine))
