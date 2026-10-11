"""Turning a period's income into what each member is owed.

The whole chain lives here so it can be read top to bottom and tested as one
thing. Nothing in an adapter, a route or a report re-implements any part of it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import NotFound, PermissionDenied, ValidationError
from ...shared.money import SCALE, ZERO, quantize, to_decimal
from ...shared.security import utcnow
from ..books.models import CostPolicy, Permission
from ..exchange.models import CURRENCY_NAMES
from ..exchange.service import ExchangeService
from ..books.service import BookService
from ..identity.models import AuditEvent
from ..ledger.models import Flow, Transaction
from ..ledger.categories import CategoryService
from ..treasury.models import RuleBasis, TreasuryAllocation, TreasuryFund, TreasuryRule
from .models import (
    PERIOD_TRANSITIONS,
    Adjustment,
    AdjustmentKind,
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

# The forward path a period takes to locked; close_period walks it.
CLOSING_PATH = [
    PeriodStatus.OPEN, PeriodStatus.CALCULATING, PeriodStatus.AWAITING_APPROVAL,
    PeriodStatus.APPROVED, PeriodStatus.PAID, PeriodStatus.LOCKED,
]

# Which way each kind of adjustment moves pay. A correction may go either way.
RAISES_PAY = frozenset({AdjustmentKind.BONUS, AdjustmentKind.OVERTIME})
LOWERS_PAY = frozenset(
    {AdjustmentKind.PENALTY, AdjustmentKind.SHORTFALL, AdjustmentKind.ADVANCE}
)

_FA_DIGITS = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")


def _fa_number(value: Decimal) -> str:
    """A percentage as a person reads it in a refusal: ۳۰ or ۳۲٫۵, never 30.0000."""
    return format(value, "f").translate(_FA_DIGITS)


@dataclass
class Distribution:
    """What a period produced, and what is left to share out."""

    gross_income: Decimal = ZERO
    direct_costs: Decimal = ZERO
    treasury_total: Decimal = ZERO
    treasury_by_fund: Dict[uuid.UUID, Decimal] = field(default_factory=dict)
    cost_policy: CostPolicy = CostPolicy.BEFORE_SPLIT
    # Kept so a treasury rule written for one category can be charged on that
    # category alone, which is what such a rule says it does. Only income is
    # tracked: a category is either an income one or an expense one, never
    # both, so a category's "net" is its income.
    income_by_category: Dict[str, Decimal] = field(default_factory=dict)
    # Each rule's own cut, so the allocation written for it can say which
    # rule took it and on what basis. treasury_by_fund is the same money
    # summed per fund.
    treasury_cuts: List[tuple] = field(default_factory=list)

    @property
    def net_profit(self) -> Decimal:
        return self.gross_income - self.direct_costs

    @property
    def _before_floor(self) -> Decimal:
        if self.cost_policy is CostPolicy.FROM_TREASURY:
            # Members are paid out of gross income; the treasury's cut is what
            # carries the costs. See CostPolicy.
            return self.gross_income - self.treasury_total
        return self.net_profit - self.treasury_total

    @property
    def distributable(self) -> Decimal:
        """What the members share, never below zero.

        A month that spent more than it earned used to hand every member a
        negative payslip, which read as "settled" because nothing was owed — a
        loss shown as a closed account. There is nothing to share in such a
        month; the loss itself is `shortfall`, for a screen to say out loud.
        """
        return quantize(max(self._before_floor, ZERO))

    @property
    def shortfall(self) -> Decimal:
        """How far the month fell short of paying anything out, or zero."""
        return quantize(max(-self._before_floor, ZERO))

    @property
    def treasury_net(self) -> Decimal:
        """What the treasury keeps once it has paid what this policy asks of it."""
        if self.cost_policy is CostPolicy.FROM_TREASURY:
            return self.treasury_total - self.direct_costs
        return self.treasury_total


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
        await CategoryService(self.session).lock_book(book_id)
        if ends_on < starts_on:
            raise ValidationError("a period cannot end before it starts")
        await self._require_no_overlap(book_id, starts_on, ends_on)

        period = FinancialPeriod(
            book_id=book_id, label=label.strip(), starts_on=starts_on, ends_on=ends_on
        )
        self.session.add(period)
        await self.session.flush()
        return period

    async def periods(
        self, book_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[FinancialPeriod]:
        """Newest first — the one being worked on is almost always the last one."""
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(FinancialPeriod)
                .where(FinancialPeriod.book_id == book_id)
                .order_by(FinancialPeriod.starts_on.desc())
            )
        ).scalars().all()

    async def adjustments(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID
    ) -> Sequence[Adjustment]:
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(Adjustment)
                .where(Adjustment.period_id == period_id)
                .order_by(Adjustment.created_at)
            )
        ).scalars().all()

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
        await CategoryService(self.session).lock_book(period.book_id)
        await self.session.refresh(period)

        if to not in PERIOD_TRANSITIONS[period.status]:
            raise ValidationError(
                f"a {period.status.value} period cannot move to {to.value}"
            )

        if to is PeriodStatus.LOCKED:
            await self._refuse_lock_over_unpaid(period)

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

    async def close_period(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID
    ) -> FinancialPeriod:
        """Take a period all the way to locked, in one step.

        The bot offered "close period" only on an approved period and then
        asked for a move the state machine does not have (approved → locked),
        while offering no way to approve or mark paid at all: no period could be
        closed from the bot. The steps in between are bookkeeping states for a
        team that splits proposing from approving; for whoever holds the lock
        permission they are one decision, so this walks them.

        Every refusal is checked before the first step, so a refused close
        moves nothing: no payslips yet, payslips older than the period's
        numbers, or anyone still owed.
        """
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.LOCK_PERIOD)
        await CategoryService(self.session).lock_book(period.book_id)
        await self.session.refresh(period)
        if period.status is PeriodStatus.LOCKED:
            return period

        slips = (await self.session.execute(
            select(Payslip).where(Payslip.period_id == period.id)
        )).scalars().all()
        if not slips:
            raise ValidationError("هنوز فیشی صادر نشده؛ اول فیش‌ها را حساب کن.")
        distributable = (await self.compute_distribution(period.id)).distributable
        if any(slip.distributable_snapshot != distributable for slip in slips):
            # Locking would freeze payslips that no longer match the period.
            raise ValidationError(
                "بعد از صدور فیش‌ها چیزی در این دوره عوض شده؛ اول دوباره حساب کن."
            )
        await self._refuse_lock_over_unpaid(period)

        for step in CLOSING_PATH[CLOSING_PATH.index(period.status) + 1:]:
            await self.advance_period(actor_user_id, period.id, step)
        return period

    async def _refuse_lock_over_unpaid(self, period: FinancialPeriod) -> None:
        """A locked period takes no payment, so it may not lock while one is owed.

        Locking used to check only the transition, so a month could close with
        pay still outstanding — and then, because pay() did not look at the
        lock either, be paid into after it was closed. The refusal names who is
        still owed, so the fix is obvious: pay them, or recalculate.
        """
        from ..identity.models import User

        unpaid = []
        for slip in (
            await self.session.execute(
                select(Payslip).where(Payslip.period_id == period.id)
            )
        ).scalars().all():
            await self.session.refresh(slip, attribute_names=["payments"])
            if slip.remaining > ZERO:
                person = await self.session.get(User, slip.user_id)
                name = person.display_name if person else "—"
                unpaid.append(f"{name} ({_fa_number(slip.remaining.normalize())})")
        if unpaid:
            raise ValidationError(
                "این دوره فیش پرداخت‌نشده دارد و قفل نمی‌شود: " + "، ".join(unpaid)
            )

    async def _require_no_overlap(
        self,
        book_id: uuid.UUID,
        starts_on: date,
        ends_on: date,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Two periods must not cover the same day.

        compute_distribution sums a period's transactions by date, so a day in
        two periods is counted in both — the same income divided twice, and two
        people paid for it. Nothing stopped that until now, and a book picked
        one up within minutes of somebody exploring the menu.
        """
        stmt = select(FinancialPeriod).where(
            FinancialPeriod.book_id == book_id,
            FinancialPeriod.starts_on <= ends_on,
            FinancialPeriod.ends_on >= starts_on,
        )
        if exclude_id is not None:
            stmt = stmt.where(FinancialPeriod.id != exclude_id)

        clash = (await self.session.execute(stmt.limit(1))).scalar_one_or_none()
        if clash is not None:
            raise ValidationError(
                f"این بازه با دورهٔ «{clash.label}» "
                f"({jalali.to_text(clash.starts_on)} تا {jalali.to_text(clash.ends_on)}) "
                "هم‌پوشانی دارد."
            )

    async def reschedule_period(
        self,
        actor_user_id: uuid.UUID,
        period_id: uuid.UUID,
        starts_on: Optional[date] = None,
        ends_on: Optional[date] = None,
    ) -> FinancialPeriod:
        """Move a period's start or end.

        The window decides which transactions the period divides, so its
        payslips are a snapshot of it. Moving the window makes that snapshot
        stale, and stale beats nothing only if nobody looks — so any payslips
        are recalculated here rather than left to be trusted. Payments made
        against them stay, as they do on any recalculation.
        """
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.MANAGE_PAYROLL)

        if period.status in (PeriodStatus.PAID, PeriodStatus.LOCKED):
            raise PermissionDenied("این دوره پرداخت یا قفل شده و تاریخش عوض نمی‌شود.")

        new_start = starts_on or period.starts_on
        new_end = ends_on or period.ends_on
        if new_end < new_start:
            raise ValidationError("پایان دوره نمی‌تواند قبل از شروعش باشد.")
        if (new_start, new_end) == (period.starts_on, period.ends_on):
            return period

        await self._require_no_overlap(period.book_id, new_start, new_end, period.id)

        had_payslips = await self.session.scalar(
            select(Payslip.id).where(Payslip.period_id == period_id).limit(1)
        )
        period.starts_on, period.ends_on = new_start, new_end
        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="period.rescheduled",
                subject=period.label,
                detail=f"{new_start}..{new_end}",
            )
        )
        await self.session.flush()

        if had_payslips:
            await self.calculate(actor_user_id, period_id)
        return period

    async def discard_calculation(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID
    ) -> int:
        """Throw a period's payslips away so the period can be worked on again.

        Calculating freezes a period's transactions, because a payslip is a
        snapshot and its inputs must not move underneath it. That is right for
        a period that has ended and wrong for one still running: a period
        covering today would otherwise block today's bookkeeping entirely, and
        there was no way back.

        Refused once money has been handed over: payments cascade with their
        payslips, so discarding would erase the record that money moved. Such a
        period needs recalculating instead, which keeps the payments.
        """
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.MANAGE_PAYROLL)

        if period.status in (PeriodStatus.PAID, PeriodStatus.LOCKED):
            raise PermissionDenied("این دوره پرداخت یا قفل شده است.")
        if await self.session.scalar(
            select(Payment.id)
            .join(Payslip, Payslip.id == Payment.payslip_id)
            .where(Payslip.period_id == period_id)
            .limit(1)
        ):
            raise PermissionDenied(
                "این دوره پرداخت ثبت‌شده دارد و باطل‌کردن محاسبه سابقهٔ پرداخت را "
                "پاک می‌کند. برای به‌روز شدن فیش‌ها «محاسبهٔ دوباره» را بزن؛ "
                "پرداخت‌ها سر جایشان می‌مانند."
            )

        slips = (
            await self.session.execute(
                select(Payslip).where(Payslip.period_id == period_id)
            )
        ).scalars().all()
        for slip in slips:
            await self.session.delete(slip)
        # The treasury allocation belongs to the run too, exactly as it does
        # when a run is replaced.
        for allocation in (
            await self.session.execute(
                select(TreasuryAllocation).where(
                    TreasuryAllocation.period_id == period_id
                )
            )
        ).scalars().all():
            await self.session.delete(allocation)

        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="period.calculation_discarded",
                subject=period.label,
                detail=str(len(slips)),
            )
        )
        await self.session.flush()
        return len(slips)

    async def rename_period(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID, label: str
    ) -> FinancialPeriod:
        """Change what a period is called. Its dates, and its payslips, stay.

        The label is the only part of a period a person writes, and until now a
        typo in one was permanent.
        """
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.MANAGE_PAYROLL)

        name = label.strip()
        if not name:
            raise ValidationError("نام دوره نمی‌تواند خالی باشد.")
        if len(name) > 40:
            raise ValidationError("نام دوره حداکثر ۴۰ حرف است.")

        clash = await self.session.scalar(
            select(FinancialPeriod.id).where(
                FinancialPeriod.book_id == period.book_id,
                FinancialPeriod.label == name,
                FinancialPeriod.id != period_id,
            ).limit(1)
        )
        if clash:
            raise ValidationError("دوره‌ای با همین نام در این دفتر هست.")

        period.label = name
        await self.session.flush()
        return period

    async def delete_period(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID
    ) -> None:
        """Remove a period that has not paid anyone yet.

        The bot's "new period" button creates one for the current month, and
        until now nothing could undo that. An unwanted period is not harmless:
        two periods covering the same day both count that day's income, so the
        same money can be divided twice.

        A period that has produced a payslip is history and stays. So does one
        that is paid or locked, whatever its payslips say.
        """
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.MANAGE_PAYROLL)

        if period.status in (PeriodStatus.PAID, PeriodStatus.LOCKED):
            raise PermissionDenied("این دوره پرداخت یا قفل شده و حذف نمی‌شود.")
        if await self.session.scalar(
            select(Payslip.id).where(Payslip.period_id == period_id).limit(1)
        ):
            raise ValidationError(
                "این دوره فیش صادر کرده؛ اول محاسبه را باطل کن یا دوره را نگه دار."
            )

        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="period.deleted",
                subject=period.label,
                detail=f"{period.starts_on}..{period.ends_on}",
            )
        )
        await self.session.delete(period)
        await self.session.flush()

    async def _require_editable(self, period: FinancialPeriod) -> None:
        if period.status is PeriodStatus.LOCKED:
            raise PermissionDenied(
                "this period is locked; record a correction in a later one"
            )

    # ------------------------------------------------------------- treasury
    async def compute_distribution(self, period_id: uuid.UUID) -> Distribution:
        """Income minus costs minus whatever the treasury rules take."""
        period = await self.get_period(period_id)
        book = await self.books.get_book(period.book_id)

        rows = (
            await self.session.execute(
                select(Transaction).where(
                    Transaction.book_id == period.book_id,
                    Transaction.occurred_on >= period.starts_on,
                    Transaction.occurred_on <= period.ends_on,
                )
            )
        ).scalars().all()

        result = Distribution(cost_policy=book.cost_policy)
        for tx in rows:
            if tx.flow is Flow.INCOME:
                result.gross_income += tx.converted_amount
                result.income_by_category[tx.category] = (
                    result.income_by_category.get(tx.category, ZERO) + tx.converted_amount
                )
            else:
                result.direct_costs += tx.converted_amount

        # A deactivated fund takes nothing more. Its rules are left active on
        # purpose — switching the fund back on should restore them — so the
        # fund itself has to be part of the question, or it keeps taking.
        rules = (
            await self.session.execute(
                select(TreasuryRule)
                .join(TreasuryFund, TreasuryFund.id == TreasuryRule.fund_id)
                .where(
                    TreasuryRule.book_id == period.book_id,
                    TreasuryRule.is_active.is_(True),
                    TreasuryFund.is_active.is_(True),
                )
            )
        ).scalars().all()

        for rule in rules:
            # A rule that had not started, or had already ended, takes nothing.
            if not rule.applies_on(period.ends_on):
                continue

            # A rule naming a category is charged on that category alone. The
            # column said so from the start and nothing read it, so a rule
            # meant for one kind of income quietly took a cut of all of it.
            # Only a percentage is narrowed by it: a flat amount read through
            # this branch became a percentage of itself, and a flat 5,000,000
            # took fifty billion.
            if rule.category and rule.basis is not RuleBasis.FIXED:
                # Charged on that category's income alone. Gross and net agree
                # here because a category carries one flow, so a category has
                # no costs of its own to net off.
                cut = (result.income_by_category.get(rule.category, ZERO)
                       * rule.value / HUNDRED)
            elif rule.basis is RuleBasis.GROSS_PERCENT:
                cut = result.gross_income * rule.value / HUNDRED
            elif rule.basis is RuleBasis.NET_PERCENT:
                cut = result.net_profit * rule.value / HUNDRED
            else:
                # A flat amount does not scale with anything, so a category
                # cannot change it.
                cut = rule.value

            cut = quantize(max(cut, ZERO))
            result.treasury_cuts.append((rule, cut))
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

        # set_share refuses this now, but rules written before it did are still
        # in the table. Paying them would overpay silently; refusing names it.
        promised = sum(
            (rule.value for rule in rules.values() if rule.basis is ShareBasis.PERCENT),
            ZERO,
        )
        if promised > HUNDRED:
            raise ValidationError(
                f"جمع سهم‌های درصدی اعضا {_fa_number(promised.normalize())} درصد است؛ "
                "پیش از محاسبه آن را به ۱۰۰ یا کمتر برسانید"
            )

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

        # Fixed claims can be more than a thin month holds. What is left for
        # the weighted members is then nothing — not a negative amount that
        # turns their payslips into bills.
        remaining = max(distributable - sum(direct.values(), ZERO), ZERO)
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

    async def set_share(
        self,
        book_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        user_id: uuid.UUID,
        basis: ShareBasis,
        value,
        effective_from: Optional[date] = None,
    ) -> ShareRule:
        """Set what one member's cut is, from today or from a chosen date.

        A previous rule is *closed*, never edited. Effective dating is the whole
        point of this table: a raise agreed today must not silently rewrite what
        the same person was paid last spring. So the old rule gets an end date
        the day before the new one starts, and both remain readable.
        """
        await self.books.require(book_id, actor_user_id, Permission.MANAGE_PAYROLL)

        if await self.books.membership(book_id, user_id) is None:
            raise ValidationError("این شخص عضو این دفتر نیست")

        amount = quantize(to_decimal(value))
        if amount <= ZERO:
            raise ValidationError("سهم باید بیشتر از صفر باشد")
        if basis is ShareBasis.PERCENT and amount > HUNDRED:
            raise ValidationError("درصد نمی‌تواند بیشتر از ۱۰۰ باشد")

        # The book's day, not the server's: at half past midnight in Tehran the
        # server's UTC date is still yesterday, and a share "from today" began
        # in the previous period.
        starts_on = effective_from or jalali.today_in(
            (await self.books.get_book(book_id)).timezone
        )

        if basis is ShareBasis.PERCENT:
            await self._refuse_percent_over_hundred(book_id, user_id, amount, starts_on)

        for existing in (
            await self.session.execute(
                select(ShareRule).where(
                    ShareRule.book_id == book_id,
                    ShareRule.user_id == user_id,
                    ShareRule.is_active.is_(True),
                )
            )
        ).scalars().all():
            if existing.effective_from >= starts_on:
                # A rule that had not taken effect yet is a mistake being
                # corrected, not history worth keeping.
                existing.is_active = False
            elif existing.effective_to is None or existing.effective_to >= starts_on:
                # Only a rule still in force on the new start date needs an end.
                # Closing every active rule instead widened the ones already
                # finished: set a share three times and the first claimed to
                # have been in force through the second period.
                existing.effective_to = starts_on - timedelta(days=1)

        rule = ShareRule(
            book_id=book_id, user_id=user_id, basis=basis,
            value=amount, effective_from=starts_on,
        )
        self.session.add(rule)
        self.session.add(
            AuditEvent(
                user_id=actor_user_id, action="share.set",
                subject=str(user_id), detail=f"{basis.value}:{amount}",
            )
        )
        await self.session.flush()
        return rule

    async def _refuse_percent_over_hundred(
        self, book_id: uuid.UUID, user_id: uuid.UUID, amount: Decimal, starts_on: date
    ) -> None:
        """Percentages that add up past 100 promise money that does not exist.

        70% and 60% of an 80,000,000 month paid out 104,000,000, and nothing in
        the books said where the other 24,000,000 came from. The new rule is in
        force from `starts_on` onwards — `set_share` retires any later rule of
        the same member — so it is checked on that day and on every later day
        someone else's rule changes. The member's own current rule is left out:
        lowering your own share to make room must not be refused.
        """
        days = {starts_on}
        for rule in (
            await self.session.execute(
                select(ShareRule).where(
                    ShareRule.book_id == book_id,
                    ShareRule.is_active.is_(True),
                    ShareRule.user_id != user_id,
                    ShareRule.effective_from > starts_on,
                )
            )
        ).scalars().all():
            days.add(rule.effective_from)

        for day in sorted(days):
            others = sum(
                (
                    rule.value
                    for member, rule in (await self.share_rules_for(book_id, day)).items()
                    if member != user_id and rule.basis is ShareBasis.PERCENT
                ),
                ZERO,
            )
            if others + amount > HUNDRED:
                free = max(HUNDRED - others, ZERO).normalize()
                raise ValidationError(
                    "جمع سهم‌های درصدی از ۱۰۰ بیشتر می‌شود؛ "
                    f"حداکثر {_fa_number(free)} درصد آزاد است"
                )

    async def shares(
        self, book_id: uuid.UUID, actor_user_id: uuid.UUID, on: Optional[date] = None
    ) -> Dict[uuid.UUID, ShareRule]:
        """The rule in force for each member, for a screen to display."""
        await self.books.require(book_id, actor_user_id, Permission.VIEW_REPORTS)
        return await self.share_rules_for(
            book_id, on or jalali.today_in((await self.books.get_book(book_id)).timezone)
        )

    async def clear_share(
        self, book_id: uuid.UUID, actor_user_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Stop this member taking a share from today.

        The rule is closed, not switched off. Switching it off erased it from
        history as well: share_rules_for() skips an inactive rule on every day,
        so a past period recalculated afterwards found no share for this member
        and paid them nothing — and since a period that has paid out can be
        recalculated, every payment to them would have read as an overpayment.
        Closing it is what set_share does to the rule it replaces, for the same
        reason. A rule that had not started yet is a mistake being withdrawn,
        and is switched off exactly as set_share does.
        """
        await self.books.require(book_id, actor_user_id, Permission.MANAGE_PAYROLL)
        book = await self.books.get_book(book_id)
        today = jalali.today_in(book.timezone)

        for rule in (
            await self.session.execute(
                select(ShareRule).where(
                    ShareRule.book_id == book_id,
                    ShareRule.user_id == user_id,
                    ShareRule.is_active.is_(True),
                )
            )
        ).scalars().all():
            if rule.effective_from >= today:
                rule.is_active = False
            elif rule.effective_to is None or rule.effective_to >= today:
                rule.effective_to = today - timedelta(days=1)
        self.session.add(
            AuditEvent(
                user_id=actor_user_id, action="share.cleared",
                subject=str(user_id), detail=str(today),
            )
        )
        await self.session.flush()

    # -------------------------------------------------------- performance
    async def record_performance(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID, user_id: uuid.UUID, **measures
    ) -> PerformanceRecord:
        """What a member actually did, for the bases that are paid by measure.

        Upserts by (period, user) because the unique constraint says there is
        one record per member per period — correcting a figure should change it
        rather than fail.
        """
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.MANAGE_PAYROLL)
        await self._require_editable(period)

        record = (
            await self.session.execute(
                select(PerformanceRecord).where(
                    PerformanceRecord.period_id == period_id,
                    PerformanceRecord.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

        if record is None:
            record = PerformanceRecord(
                book_id=period.book_id, period_id=period_id, user_id=user_id
            )
            self.session.add(record)

        for measure, value in measures.items():
            if not hasattr(record, measure):
                raise ValidationError(f"{measure} چنین چیزی ثبت نمی‌شود")
            setattr(record, measure, quantize(to_decimal(value)))

        await self.session.flush()
        return record

    async def performance(
        self, actor_user_id: uuid.UUID, period_id: uuid.UUID
    ) -> Dict[uuid.UUID, PerformanceRecord]:
        period = await self.get_period(period_id)
        await self.books.require(period.book_id, actor_user_id, Permission.VIEW_REPORTS)

        return {
            record.user_id: record
            for record in (
                await self.session.execute(
                    select(PerformanceRecord).where(
                        PerformanceRecord.period_id == period_id
                    )
                )
            ).scalars().all()
        }

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

        # Stored and then silently dropped: calculate() only applies
        # adjustments to people who have a payslip, and a stranger never does.
        if await self.books.membership(period.book_id, user_id) is None:
            raise ValidationError("این شخص عضو این دفتر نیست.")

        amount = quantize(value)
        if amount == ZERO:
            raise ValidationError("مبلغ تعدیل نمی‌تواند صفر باشد.")
        # The sign moves the money; the kind only names it. The bot derives the
        # kind from the sign, and the API let them disagree, so a "penalty" of
        # +1,000,000 raised someone's pay.
        if kind in RAISES_PAY and amount < ZERO:
            raise ValidationError("پاداش و اضافه‌کار مبلغ مثبت می‌خواهند.")
        if kind in LOWERS_PAY and amount > ZERO:
            raise ValidationError("جریمه، کسری و مساعده مبلغ منفی می‌خواهند.")

        adjustment = Adjustment(
            book_id=period.book_id,
            period_id=period_id,
            user_id=user_id,
            kind=kind,
            mode=mode,
            value=amount,
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
        await CategoryService(self.session).lock_book(period.book_id)
        await self.session.refresh(period)
        await self._require_editable(period)
        distribution = await self.compute_distribution(period_id)
        shares = await self._base_shares(period, distribution.distributable)

        adjustments_by_user: Dict[uuid.UUID, List[Adjustment]] = {}
        for adjustment in (
            await self.session.execute(
                select(Adjustment).where(Adjustment.period_id == period_id)
            )
        ).scalars().all():
            adjustments_by_user.setdefault(adjustment.user_id, []).append(adjustment)

        # A member's payslip is updated in place, never replaced. Payments hang
        # off it and cascade with it, so replacing a paid payslip deleted the
        # record that money had changed hands — and the wallet sprang back up as
        # if it never had. Updated, it keeps its payments, and what moves is
        # only what is still owed. That is what lets a period that has paid out
        # keep taking entries.
        existing = {
            slip.user_id: slip
            for slip in (
                await self.session.execute(
                    select(Payslip).where(Payslip.period_id == period_id)
                )
            ).scalars().all()
        }
        # The allocations belong to the run too. Deleting only the payslips left
        # every recalculation adding a second cut for the same period, so a book
        # recalculated twice reported a treasury balance twice the size of the
        # money that ever went into it — with nothing anywhere saying so.
        for stale_allocation in (
            await self.session.execute(
                select(TreasuryAllocation).where(
                    TreasuryAllocation.period_id == period_id
                )
            )
        ).scalars().all():
            await self.session.delete(stale_allocation)
        await self.session.flush()

        slips: List[Payslip] = []
        for user_id, (rule, base_share) in shares.items():
            adjustments_total = self._apply_adjustments(
                base_share, adjustments_by_user.get(user_id, [])
            )
            slip = existing.pop(user_id, None)
            if slip is None:
                slip = Payslip(
                    book_id=period.book_id,
                    period_id=period_id,
                    user_id=user_id,
                    currency=book.base_currency,
                    # A slip that was just built genuinely has no payments yet.
                    # Saying so avoids a lazy load the caller cannot await.
                    payments=[],
                )
                self.session.add(slip)
            slip.distributable_snapshot = distribution.distributable
            slip.share_basis_snapshot = rule.basis
            slip.share_value_snapshot = rule.value
            slip.base_share = base_share
            slip.adjustments_total = adjustments_total
            slip.net_pay = quantize(base_share + adjustments_total)
            slips.append(slip)

        # Whoever is left had a payslip and no longer has a share on the day
        # the period ends. Without payments the slip simply goes. With them it
        # stays, at nothing: deleting it would delete the record that they were
        # paid, and at nothing, every payment to them reads as paid beyond
        # their share — which, now, it is.
        for slip in existing.values():
            if not slip.payments:
                await self.session.delete(slip)
                continue
            slip.distributable_snapshot = distribution.distributable
            slip.share_value_snapshot = ZERO
            slip.base_share = ZERO
            slip.adjustments_total = ZERO
            slip.net_pay = ZERO
            slips.append(slip)

        # The treasury cut is recorded once, as fact, alongside the run — one
        # row per rule, with that rule's own basis and value. One row per fund
        # stamped every cut "gross percent" with the amount as its percentage,
        # so the history this table exists to keep could not be audited.
        for rule, amount in distribution.treasury_cuts:
            self.session.add(
                TreasuryAllocation(
                    book_id=period.book_id,
                    fund_id=rule.fund_id,
                    period_id=period_id,
                    amount=amount,
                    basis_snapshot=rule.basis,
                    value_snapshot=rule.value,
                )
            )

        await self.session.flush()
        return slips

    async def void_payment(
        self, actor_user_id: uuid.UUID, payment_id: uuid.UUID
    ) -> Payslip:
        """Take back a payment that should not have been recorded.

        A payment was permanent once written: there was no way to correct a
        wrong figure, a duplicate, or one entered against the wrong person.
        Removing it puts the payslip back where it was, which is what a
        correction means before the period is closed.

        A locked or paid-off period is history and keeps what it has.
        """
        payment = await self.session.get(Payment, payment_id)
        if payment is None:
            raise NotFound("پرداخت پیدا نشد.")
        slip = await self.session.get(Payslip, payment.payslip_id)
        await self.books.require(slip.book_id, actor_user_id, Permission.MANAGE_PAYROLL)

        period = await self.get_period(slip.period_id)
        if period.status in (PeriodStatus.PAID, PeriodStatus.LOCKED):
            raise PermissionDenied("این دوره پرداخت‌شده یا قفل است و اصلاح نمی‌شود.")

        self.session.add(
            AuditEvent(
                user_id=actor_user_id,
                action="payment.voided",
                subject=str(slip.user_id),
                detail=f"{payment.amount} {payment.currency}",
            )
        )
        await self.session.delete(payment)
        await self.session.flush()
        await self.session.refresh(slip, attribute_names=["payments"])
        return slip

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
        # Two payments in flight both read what was owed before either wrote,
        # and both passed the overpayment check. Calculation and recording
        # already queue on this lock; paying now does too.
        await CategoryService(self.session).lock_book(slip.book_id)

        period = await self.get_period(slip.period_id)
        if period.status is PeriodStatus.LOCKED:
            # Locked is the end of the line: void_payment already refused to
            # change a locked period, and accepting money into one is the same
            # change in the other direction.
            raise PermissionDenied("این دوره قفل است و پرداختی در آن ثبت نمی‌شود.")

        value = quantize(amount)
        if value <= ZERO:
            raise ValidationError("مبلغ پرداخت باید بیشتر از صفر باشد.")

        # Summed in SQL rather than through the relationship: the payslip may
        # already be in the identity map from a calculate() in the same session,
        # in which case its `payments` collection was never loaded.
        already = sum(
            (
                to_decimal(amount) * to_decimal(at_rate)
                for amount, at_rate in (
                    await self.session.execute(
                        select(Payment.amount, Payment.conversion_rate).where(
                            Payment.payslip_id == payslip_id
                        )
                    )
                ).all()
            ),
            ZERO,
        )
        owed = quantize(slip.net_pay - already)

        paid_in = (currency or slip.currency).upper()
        if paid_in == slip.currency:
            # The payslip's own currency is worth exactly itself, and a rate
            # sent with it is ignored — as the ledger ignores one on an entry
            # in the book's own currency. Counted, "100 toman at 2" settled 200
            # of the payslip while 100 left the wallet.
            rate = Decimal("1")
        else:
            if conversion_rate is None:
                raise ValidationError(
                    f"پرداخت به {paid_in} نرخ تبدیل به {slip.currency} می‌خواهد."
                )
            # Rounded as it will be stored, before it is judged. A rate below
            # the fourth decimal passed as positive and was then saved as zero,
            # so the payment counted for nothing while the token left the
            # wallet. It also keeps the check below and paid_total, which reads
            # the stored rate, working from the same number.
            rate = quantize(to_decimal(conversion_rate))
            if rate <= ZERO:
                raise ValidationError("نرخ تبدیل باید مثبت باشد (دست‌کم ۰٫۰۰۰۱).")

        # Compared in the payslip's own currency. Summing raw amounts counted
        # forty tethers as forty toman and left the payslip all but unpaid.
        #
        # The overshoot allowance is one unit of the currency being paid: a
        # token is stored to four places, so the exact figure owed is usually
        # not reachable in it, and settling a 27,000,000 payslip in tether
        # otherwise left a few toman outstanding that no amount of tether
        # could clear.
        if quantize(value * rate) > owed + quantize(SCALE * rate):
            # A person reads this. It used to arrive in English, and once a
            # period can be recalculated below what was paid, "only -300000
            # is still owed" is what it would have said.
            if owed <= ZERO:
                raise ValidationError("از این فیش چیزی مانده نیست.")
            unit = CURRENCY_NAMES.get(slip.currency, slip.currency)
            raise ValidationError(
                f"از این فیش فقط {owed.normalize():,f} {unit} مانده است."
            )

        book = await self.books.get_book(slip.book_id)
        exchange = ExchangeService(self.session)
        if paid_in not in await exchange.allowed(slip.book_id):
            raise ValidationError(f"این دفتر {paid_in} را پشتیبانی نمی‌کند.")
        # You cannot hand over a token the book does not hold.
        await exchange.require_funds(slip.book_id, paid_in, value)

        payment = Payment(
            payslip_id=payslip_id,
            amount=value,
            currency=paid_in,
            conversion_rate=rate,
            # The book's day, not the server's: a payment made in the evening
            # in Tehran is not yesterday because the server runs on UTC.
            paid_on=paid_on or jalali.today_in(book.timezone),
            reference=reference,
        )
        self.session.add(payment)
        await self.session.flush()
        # Reload the collection so the caller's `remaining` / `is_settled` are true.
        await self.session.refresh(slip, attribute_names=["payments"])
        return payment
