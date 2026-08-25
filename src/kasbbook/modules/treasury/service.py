"""Managing the funds a team sets aside before anyone is paid.

The rules written here are read by the payroll run, which snapshots what they
produced onto the period. That direction is deliberate and one-way: nothing in
this module ever recomputes a past allocation, because a team that reopens last
year's payroll should see what was actually decided then, not what today's
rules would say.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from .models import (
    FundKind,
    RuleBasis,
    TreasuryAllocation,
    TreasuryFund,
    TreasuryRule,
)

# A percentage over a hundred is a typo every time, and the one that would
# quietly hand the treasury more than the business earned.
MAX_PERCENT = 100


class TreasuryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    # ----------------------------------------------------------------- funds
    async def create_fund(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        kind: FundKind = FundKind.MAIN,
    ) -> TreasuryFund:
        await self.books.require(book_id, user_id, Permission.MANAGE_PAYROLL)

        name = (name or "").strip()
        if not name:
            raise ValidationError("صندوق باید نامی داشته باشد")

        fund = TreasuryFund(book_id=book_id, name=name[:80], kind=kind)
        self.session.add(fund)
        await self.session.flush()
        return fund

    async def funds(self, book_id: uuid.UUID, user_id: uuid.UUID) -> Sequence[TreasuryFund]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(TreasuryFund)
                .where(TreasuryFund.book_id == book_id)
                .order_by(TreasuryFund.is_active.desc(), TreasuryFund.created_at)
            )
        ).scalars().all()

    async def get_fund(
        self, book_id: uuid.UUID, user_id: uuid.UUID, fund_id: uuid.UUID
    ) -> TreasuryFund:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)

        fund = await self.session.get(TreasuryFund, fund_id)
        if fund is None or fund.book_id != book_id:
            raise NotFound("این صندوق پیدا نشد")
        return fund

    async def toggle_fund(
        self, book_id: uuid.UUID, user_id: uuid.UUID, fund_id: uuid.UUID
    ) -> TreasuryFund:
        await self.books.require(book_id, user_id, Permission.MANAGE_PAYROLL)

        fund = await self.get_fund(book_id, user_id, fund_id)
        fund.is_active = not fund.is_active
        await self.session.flush()
        return fund

    async def delete_fund(
        self, book_id: uuid.UUID, user_id: uuid.UUID, fund_id: uuid.UUID
    ) -> None:
        """Only while it has taken nothing.

        A fund with allocations behind it is part of a payroll that has already
        been run and possibly paid; deleting it would leave those periods
        pointing at nothing. Deactivating stops it taking any more, which is
        what "remove" actually means once money has moved.
        """
        await self.books.require(book_id, user_id, Permission.MANAGE_PAYROLL)
        fund = await self.get_fund(book_id, user_id, fund_id)

        taken = (
            await self.session.execute(
                select(func.count(TreasuryAllocation.id)).where(
                    TreasuryAllocation.fund_id == fund_id
                )
            )
        ).scalar() or 0
        if taken:
            raise ValidationError(
                f"این صندوق در {taken} دوره سهم برداشته و حذف نمی‌شود. "
                "غیرفعالش کن تا از این به بعد چیزی برندارد."
            )

        for rule in await self.rules(book_id, user_id, fund_id):
            await self.session.delete(rule)
        await self.session.delete(fund)
        await self.session.flush()

    # ----------------------------------------------------------------- rules
    async def add_rule(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        fund_id: uuid.UUID,
        basis: RuleBasis,
        value,
        effective_from: Optional[date] = None,
        category: Optional[str] = None,
    ) -> TreasuryRule:
        await self.books.require(book_id, user_id, Permission.MANAGE_PAYROLL)
        await self.get_fund(book_id, user_id, fund_id)

        amount = quantize(to_decimal(value))
        if amount <= ZERO:
            raise ValidationError("مقدار قاعده باید بیشتر از صفر باشد")
        if basis is not RuleBasis.FIXED and amount > MAX_PERCENT:
            raise ValidationError("درصد نمی‌تواند بیشتر از ۱۰۰ باشد")

        rule = TreasuryRule(
            book_id=book_id,
            fund_id=fund_id,
            basis=basis,
            value=amount,
            category=(category or "").strip()[:80] or None,
            effective_from=effective_from or date.today(),
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def rules(
        self, book_id: uuid.UUID, user_id: uuid.UUID, fund_id: Optional[uuid.UUID] = None
    ) -> Sequence[TreasuryRule]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)

        stmt = select(TreasuryRule).where(TreasuryRule.book_id == book_id)
        if fund_id is not None:
            stmt = stmt.where(TreasuryRule.fund_id == fund_id)

        return (
            await self.session.execute(
                stmt.order_by(TreasuryRule.is_active.desc(), TreasuryRule.effective_from)
            )
        ).scalars().all()

    async def _owned_rule(
        self, book_id: uuid.UUID, rule_id: uuid.UUID
    ) -> TreasuryRule:
        rule = await self.session.get(TreasuryRule, rule_id)
        if rule is None or rule.book_id != book_id:
            raise NotFound("این قاعده پیدا نشد")
        return rule

    async def toggle_rule(
        self, book_id: uuid.UUID, user_id: uuid.UUID, rule_id: uuid.UUID
    ) -> TreasuryRule:
        await self.books.require(book_id, user_id, Permission.MANAGE_PAYROLL)

        rule = await self._owned_rule(book_id, rule_id)
        rule.is_active = not rule.is_active
        await self.session.flush()
        return rule

    async def delete_rule(
        self, book_id: uuid.UUID, user_id: uuid.UUID, rule_id: uuid.UUID
    ) -> None:
        """Safe at any time: what past periods took is snapshotted, not recomputed."""
        await self.books.require(book_id, user_id, Permission.MANAGE_PAYROLL)

        await self.session.delete(await self._owned_rule(book_id, rule_id))
        await self.session.flush()

    # ----------------------------------------------------------- allocations
    async def balance(
        self, book_id: uuid.UUID, user_id: uuid.UUID, fund_id: uuid.UUID
    ):
        """What this fund has taken in total, across every period."""
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)

        total = (
            await self.session.execute(
                select(func.coalesce(func.sum(TreasuryAllocation.amount), 0)).where(
                    TreasuryAllocation.fund_id == fund_id
                )
            )
        ).scalar()
        return quantize(to_decimal(total or 0))

    async def allocations(
        self, book_id: uuid.UUID, user_id: uuid.UUID, period_id: uuid.UUID
    ) -> Sequence[TreasuryAllocation]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(TreasuryAllocation).where(
                    TreasuryAllocation.book_id == book_id,
                    TreasuryAllocation.period_id == period_id,
                )
            )
        ).scalars().all()
