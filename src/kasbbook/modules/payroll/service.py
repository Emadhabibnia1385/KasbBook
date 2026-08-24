"""Turning a period's income into what each member is owed.

The whole chain lives here so it can be read top to bottom and tested as one
thing. Nothing in an adapter, a route or a report re-implements any part of it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, PermissionDenied, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ...shared.security import utcnow
from ..books.models import Permission
from ..books.service import BookService
from ..identity.models import AuditEvent
from ..ledger.models import Flow, Transaction
from ..treasury.models import RuleBasis, TreasuryAllocation, TreasuryRule
from .models import (
    PERIOD_TRANSITIONS,
    Adjustment,
    AdjustmentMode,
    FinancialPeriod,
    Payment,
    PerformanceRecord,
    PeriodStatus,
    Payslip,
    ShareBasis,
    ShareRule,
)

HUNDRED = Decimal("100")


@dataclass
class Distribution:
    """What a period produced, and what is left to share out."""

    gross_income: Decimal = ZERO
    direct_costs: Decimal = ZERO
    treasury_total: Decimal = ZERO
    treasury_by_fund: Dict[uuid.UUID, Decimal] = field(default_factory=dict)

    @property
    def net_profit(self) -> Decimal:
        return self.gross_income - self.direct_costs

    @property
    def distributable(self) -> Decimal:
        return self.net_profit - self.treasury_total


class PayrollService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    # -------------------------------------------------------------- periods
    async def open_period(
        self,
        actor_user_id: uuid.UUID,
        book_id: uuid.UUID,
        label: str,
        starts_on: date,
        ends_on: date,
    ) -> FinancialPeriod:
        await self.books.require(book_id, actor_user_id, Permission.MANAGE_PAYROLL)
        if ends_on < starts_on:
            raise ValidationError("a period cannot end before it starts")

        period = FinancialPeriod(
            book_id=book_id, label=label.strip(), starts_on=starts_on, ends_on=ends_on
        )
        self.session.add(period)
        await self.session.flush()
        return period

    async def get_period(self, period_id: uuid.UUID) -> FinancialPeriod:
        period = await self.session.get(FinancialPeriod, period_id)
        if period is None:
            raise NotFound("period")
        return period

    async def advance_period(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID, to: PeriodStatus
    ) -> FinancialPeriod:
        period = await self.get_period(period_id)

        needed = (
            Permission.LOCK_PERIOD if to is PeriodStatus.LOCKED else Permission.MANAGE_PAYROLL
        )
        await self.books.require(period.book_id, actor_user_id, needed)

        if to not in PERIOD_TRANSITIONS[period.status]:
            raise ValidationError(
                f"a {period.status.value} period cannot move to {to.value}"
            )

        period.status = to
        if to is PeriodStatus.LOCKED:
            period.locked_at = utcnow()

        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="period.status_changed",
                subject=period.label,
                detail=to.value,
            )
        )
        await self.session.flush()
        return period

    async def _require_editable(self, period: FinancialPeriod) -> None:
        if period.status is PeriodStatus.LOCKED:
            raise PermissionDenied(
                "this period is locked; record a correction in a later one"
            )

    # ------------------------------------------------------------- treasury
    async def compute_distribution(self, period_id: uuid.UUID) -> Distribution:
        """Income minus costs minus whatever the treasury rules take."""
        period = await self.get_period(period_id)

        rows = (
            await self.session.execute(
                select(Transaction).where(
                    Transaction.book_id == period.book_id,
                    Transaction.occurred_on >= period.starts_on,
                    Transaction.occurred_on <= period.ends_on,
                )
            )
        ).scalars().all()

        result = Distribution()
        for tx in rows:
            if tx.flow is Flow.INCOME:
                result.gross_income += tx.converted_amount
            else:
                result.direct_costs += tx.converted_amount

        rules = (
            await self.session.execute(
                select(TreasuryRule).where(
                    TreasuryRule.book_id == period.book_id,
                    TreasuryRule.is_active.is_(True),
                )
            )
        ).scalars().all()

        for rule in rules:
            # A rule that had not started, or had already ended, takes nothing.
            if not rule.applies_on(period.ends_on):
                continue

            if rule.basis is RuleBasis.GROSS_PERCENT:
                cut = result.gross_income * rule.value / HUNDRED
            elif rule.basis is RuleBasis.NET_PERCENT:
                cut = result.net_profit * rule.value / HUNDRED
            else:
                cut = rule.value

            cut = quantize(max(cut, ZERO))
            result.treasury_total += cut
            result.treasury_by_fund[rule.fund_id] = (
                result.treasury_by_fund.get(rule.fund_id, ZERO) + cut
            )

        result.gross_income = quantize(result.gross_income)
        result.direct_costs = quantize(result.direct_costs)
        result.treasury_total = quantize(result.treasury_total)
        return result

    # --------------------------------------------------------------- shares
    async def share_rules_for(
        self, book_id: uuid.UUID, on: date
    ) -> Dict[uuid.UUID, ShareRule]:
        """The rule in force for each member on a given day."""
        rules = (
            await self.session.execute(
                select(ShareRule).where(
                    ShareRule.book_id == book_id, ShareRule.is_active.is_(True)
                )
            )
        ).scalars().all()

        current: Dict[uuid.UUID, ShareRule] = {}
        for rule in rules:
            if not rule.applies_on(on):
                continue
            # If two rules overlap, the one that started later wins.
            held = current.get(rule.user_id)
            if held is None or rule.effective_from > held.effective_from:
                current[rule.user_id] = rule
        return current

    async def _base_shares(
        self, period: FinancialPeriod, distributable: Decimal
    ) -> Dict[uuid.UUID, tuple]:
        """Split the distributable amount by each member's rule."""
        rules = await self.share_rules_for(period.book_id, period.ends_on)
        if not rules:
            return {}

        records = {
            record.user_id: record
            for record in (
                await self.session.execute(
                    select(PerformanceRecord).where(
                        PerformanceRecord.period_id == period.id
                    )
                )
            ).scalars().all()
        }

        # Weight-based rules split what is left after the fixed and percentage
        # claims are settled, which is why they are gathered first.
        weights: Dict[uuid.UUID, Decimal] = {}
        direct: Dict[uuid.UUID, Decimal] = {}

        for user_id, rule in rules.items():
            if rule.basis is ShareBasis.PERCENT:
                direct[user_id] = quantize(distributable * rule.value / HUNDRED)
            elif rule.basis is ShareBasis.FIXED:
                direct[user_id] = quantize(rule.value)
            else:
                record = records.get(user_id)
                measured = {
                    ShareBasis.HOURS: record.hours_worked if record else ZERO,
                    ShareBasis.DAYS: record.days_worked if record else ZERO,
                    ShareBasis.POINTS: record.points if record else ZERO,
                    ShareBasis.PROJECT: rule.value,
                }[rule.basis]
                weights[user_id] = to_decimal(measured) * (
                    rule.value if rule.basis is not ShareBasis.PROJECT else Decimal("1")
                )

        remaining = distributable - sum(direct.values(), ZERO)
        total_weight = sum(weights.values(), ZERO)

        out: Dict[uuid.UUID, tuple] = {}
        for user_id, amount in direct.items():
            out[user_id] = (rules[user_id], amount)
        for user_id, weight in weights.items():
            portion = (
                quantize(remaining * weight / total_weight) if total_weight > ZERO else ZERO
            )
            out[user_id] = (rules[user_id], portion)
        return out

    # ---------------------------------------------------------- adjustments
    async def add_adjustment(
        self,
        actor_user_id: uuid.UUID,
        period_id: uuid.UUID,
        user_id: uuid.UUID,
        kind,
        mode: AdjustmentMode,
        value,
        reason: Optional[str] = None,
    ) -> Adjustment:
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.MANAGE_PAYROLL)
        await self._require_editable(period)

        adjustment = Adjustment(
            book_id=period.book_id,
            period_id=period_id,
            user_id=user_id,
            kind=kind,
            mode=mode,
            value=quantize(value),
            reason=reason,
            recorded_by=actor_user_id,
        )
        self.session.add(adjustment)
        await self.session.flush()
        return adjustment

    async def approve_adjustment(
        self, actor_user_id: uuid.UUID, adjustment_id: uuid.UUID
    ) -> Adjustment:
        adjustment = await self.session.get(Adjustment, adjustment_id)
        if adjustment is None:
            raise NotFound("adjustment")
        await self.books.require(
            adjustment.book_id, actor_user_id, Permission.APPROVE_EXPENSE
        )

        if adjustment.recorded_by == actor_user_id:
            raise PermissionDenied("an adjustment is not approved by whoever wrote it")

        adjustment.approved_by = actor_user_id
        adjustment.approved_at = utcnow()
        await self.session.flush()
        return adjustment

    def _apply_adjustments(
        self, base: Decimal, adjustments: Sequence[Adjustment]
    ) -> Decimal:
        total = ZERO
        for adjustment in adjustments:
            if adjustment.mode is AdjustmentMode.PERCENT:
                total += quantize(base * adjustment.value / HUNDRED)
            else:
                total += adjustment.value
        return quantize(total)

    # -------------------------------------------------------------- payroll
    async def calculate(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID
    ) -> List[Payslip]:
        """Produce a payslip per member, freezing every input onto it."""
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.MANAGE_PAYROLL)
        await self._require_editable(period)

        book = await self.books.get_book(period.book_id)
        distribution = await self.compute_distribution(period_id)
        shares = await self._base_shares(period, distribution.distributable)

        adjustments_by_user: Dict[uuid.UUID, List[Adjustment]] = {}
        for adjustment in (
            await self.session.execute(
                select(Adjustment).where(Adjustment.period_id == period_id)
            )
        ).scalars().all():
            adjustments_by_user.setdefault(adjustment.user_id, []).append(adjustment)

        # Recalculating replaces the previous run rather than doubling it.
        for stale in (
            await self.session.execute(
                select(Payslip).where(Payslip.period_id == period_id)
            )
        ).scalars().all():
            await self.session.delete(stale)
        await self.session.flush()

        slips: List[Payslip] = []
        for user_id, (rule, base_share) in shares.items():
            adjustments_total = self._apply_adjustments(
                base_share, adjustments_by_user.get(user_id, [])
            )
            slip = Payslip(
                book_id=period.book_id,
                period_id=period_id,
                user_id=user_id,
                distributable_snapshot=distribution.distributable,
                share_basis_snapshot=rule.basis,
                share_value_snapshot=rule.value,
                base_share=base_share,
                adjustments_total=adjustments_total,
                net_pay=quantize(base_share + adjustments_total),
                currency=book.base_currency,
                # A slip that was just built genuinely has no payments yet.
                # Saying so avoids a lazy load the caller cannot await.
                payments=[],
            )
            self.session.add(slip)
            slips.append(slip)

        # The treasury cut is recorded once, as fact, alongside the run.
        for fund_id, amount in distribution.treasury_by_fund.items():
            self.session.add(
                TreasuryAllocation(
                    book_id=period.book_id,
                    fund_id=fund_id,
                    period_id=period_id,
                    amount=amount,
                    basis_snapshot=RuleBasis.GROSS_PERCENT,
                    value_snapshot=amount,
                )
            )

        await self.session.flush()
        return slips

    async def payslips(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID
    ) -> Sequence[Payslip]:
        period = await self.get_period(period_id)

        # Seeing everyone's pay is its own permission; otherwise you see your own.
        if await self.books.can(
            period.book_id, actor_user_id, Permission.VIEW_OTHERS_PAY
        ):
            stmt = select(Payslip).where(Payslip.period_id == period_id)
        else:
            await self.books.require(
                period.book_id, actor_user_id, Permission.VIEW_REPORTS
            )
            stmt = select(Payslip).where(
                Payslip.period_id == period_id, Payslip.user_id == actor_user_id
            )
        return (await self.session.execute(stmt)).scalars().all()

    async def pay(
        self,
        actor_user_id: uuid.UUID,
        payslip_id: uuid.UUID,
        amount,
        paid_on: Optional[date] = None,
        currency: Optional[str] = None,
        conversion_rate=None,
        reference: Optional[str] = None,
    ) -> Payment:
        """Hand over some or all of what is owed. Instalments are the norm."""
        slip = await self.session.get(Payslip, payslip_id)
        if slip is None:
            raise NotFound("payslip")
        await self.books.require(slip.book_id, actor_user_id, Permission.MANAGE_PAYROLL)

        value = quantize(amount)
        if value <= ZERO:
            raise ValidationError("a payment must be positive")

        # Summed in SQL rather than through the relationship: the payslip may
        # already be in the identity map from a calculate() in the same session,
        # in which case its `payments` collection was never loaded.
        already = to_decimal(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.payslip_id == payslip_id
                    )
                )
            ).scalar_one()
        )
        owed = quantize(slip.net_pay - already)
        if value > owed:
            raise ValidationError(f"only {owed} is still owed on this payslip")

        payment = Payment(
            payslip_id=payslip_id,
            amount=value,
            currency=(currency or slip.currency).upper(),
            conversion_rate=to_decimal(conversion_rate) if conversion_rate else Decimal("1"),
            paid_on=paid_on or date.today(),
            reference=reference,
        )
        self.session.add(payment)
        await self.session.flush()
        # Reload the collection so the caller's `remaining` / `is_settled` are true.
        await self.session.refresh(slip, attribute_names=["payments"])
        return payment
