"""Payroll and treasury over HTTP.

The same services the bot calls, so a period locked from the API is locked in
Telegram and a share set in Telegram is what the API reports. If these routes
reimplemented any of it, the two would drift the first time a rule changed.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Dict, List

from fastapi import APIRouter

from ...modules.identity.service import IdentityService
from ...modules.payroll.models import (
    AdjustmentKind,
    AdjustmentMode,
    PeriodStatus,
    ShareBasis,
)
from ...modules.payroll.service import PayrollService
from ...modules.treasury.models import FundKind, RuleBasis
from ...modules.treasury.service import TreasuryService
from ...shared.errors import NotFound, ValidationError
from ..deps import CurrentUser, SessionDep
from ..schemas import (
    AdjustmentRequest,
    AdjustmentResponse,
    DistributionResponse,
    FundRequest,
    FundResponse,
    PayRequest,
    PaymentResponse,
    PayslipResponse,
    PeriodRequest,
    PeriodResponse,
    PerformanceRequest,
    PerformanceResponse,
    ShareRequest,
    ShareResponse,
    TreasuryRuleRequest,
    TreasuryRuleResponse,
)

router = APIRouter(prefix="/books/{book_id}", tags=["payroll"])

ZERO = Decimal("0")


def _as_enum(enum_class, value: str, field: str):
    try:
        return enum_class(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_class)
        raise ValidationError(f"{field} must be one of: {allowed}") from None


async def _names(session, book_id: uuid.UUID) -> Dict[uuid.UUID, str]:
    from ...modules.books.service import BookService

    identity = IdentityService(session)
    names: Dict[uuid.UUID, str] = {}
    for member in await BookService(session).members(book_id):
        person = await identity.get_user(member.user_id)
        names[member.user_id] = person.display_name
    return names


def _period(row) -> PeriodResponse:
    return PeriodResponse(
        id=row.id, label=row.label, status=row.status.value,
        starts_on=row.starts_on, ends_on=row.ends_on, locked_at=row.locked_at,
    )


# ---------------------------------------------------------------- periods
@router.get("/periods", response_model=List[PeriodResponse])
async def list_periods(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[PeriodResponse]:
    rows = await PayrollService(session).periods(book_id, user.id)
    return [_period(row) for row in rows]


@router.post("/periods", response_model=PeriodResponse, status_code=201)
async def open_period(
    book_id: uuid.UUID, body: PeriodRequest, user: CurrentUser, session: SessionDep
) -> PeriodResponse:
    period = await PayrollService(session).open_period(
        user.id, book_id, body.label, body.starts_on, body.ends_on
    )
    return _period(period)


@router.get("/periods/{period_id}/distribution", response_model=DistributionResponse)
async def distribution(
    book_id: uuid.UUID, period_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> DistributionResponse:
    """Income minus costs minus treasury — every line that produces a share."""
    payroll = PayrollService(session)
    period = await payroll.get_period(period_id)
    if period.book_id != book_id:
        raise NotFound("period")

    # Reading it is a report, so it needs the permission a report needs.
    await payroll.periods(book_id, user.id)

    result = await payroll.compute_distribution(period_id)
    return DistributionResponse(
        gross_income=result.gross_income, direct_costs=result.direct_costs,
        net_profit=result.net_profit, treasury_total=result.treasury_total,
        distributable=result.distributable,
    )


@router.post("/periods/{period_id}/status/{status}", response_model=PeriodResponse)
async def advance(
    book_id: uuid.UUID, period_id: uuid.UUID, status: str,
    user: CurrentUser, session: SessionDep,
) -> PeriodResponse:
    """Move a period along. Only the documented transitions are accepted."""
    period = await PayrollService(session).advance_period(
        user.id, period_id, _as_enum(PeriodStatus, status, "status")
    )
    return _period(period)


# ----------------------------------------------------------------- shares
@router.get("/shares", response_model=List[ShareResponse])
async def list_shares(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[ShareResponse]:
    rules = await PayrollService(session).shares(book_id, user.id)
    names = await _names(session, book_id)
    return [
        ShareResponse(
            user_id=user_id, display_name=names.get(user_id, "—"),
            basis=rule.basis.value, value=rule.value,
            effective_from=rule.effective_from,
        )
        for user_id, rule in rules.items()
    ]


@router.put("/shares", response_model=ShareResponse)
async def set_share(
    book_id: uuid.UUID, body: ShareRequest, user: CurrentUser, session: SessionDep
) -> ShareResponse:
    """Set one member's cut. The previous rule is end-dated, never edited."""
    payroll = PayrollService(session)
    rule = await payroll.set_share(
        book_id, user.id, body.user_id,
        _as_enum(ShareBasis, body.basis, "basis"), body.value, body.effective_from,
    )
    names = await _names(session, book_id)
    return ShareResponse(
        user_id=body.user_id, display_name=names.get(body.user_id, "—"),
        basis=rule.basis.value, value=rule.value, effective_from=rule.effective_from,
    )


@router.delete("/shares/{member_user_id}", status_code=204)
async def clear_share(
    book_id: uuid.UUID, member_user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await PayrollService(session).clear_share(book_id, user.id, member_user_id)


# ------------------------------------------------------------ performance
@router.get("/periods/{period_id}/performance", response_model=List[PerformanceResponse])
async def list_performance(
    book_id: uuid.UUID, period_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[PerformanceResponse]:
    records = await PayrollService(session).performance(user.id, period_id)
    names = await _names(session, book_id)
    return [
        PerformanceResponse(
            user_id=user_id, display_name=names.get(user_id, "—"),
            hours_worked=r.hours_worked, days_worked=r.days_worked,
            overtime_hours=r.overtime_hours, absence_days=r.absence_days,
            leave_days=r.leave_days, mission_days=r.mission_days,
            late_count=r.late_count, points=r.points,
        )
        for user_id, r in records.items()
    ]


@router.put("/periods/{period_id}/performance", response_model=PerformanceResponse)
async def record_performance(
    book_id: uuid.UUID, period_id: uuid.UUID, body: PerformanceRequest,
    user: CurrentUser, session: SessionDep,
) -> PerformanceResponse:
    """One record per member per period, so this corrects rather than duplicates."""
    measures = {
        name: value
        for name, value in body.model_dump(exclude={"user_id"}).items()
        if value is not None
    }
    if not measures:
        raise ValidationError("nothing to record")

    record = await PayrollService(session).record_performance(
        user.id, period_id, body.user_id, **measures
    )
    names = await _names(session, book_id)
    return PerformanceResponse(
        user_id=body.user_id, display_name=names.get(body.user_id, "—"),
        hours_worked=record.hours_worked, days_worked=record.days_worked,
        overtime_hours=record.overtime_hours, absence_days=record.absence_days,
        leave_days=record.leave_days, mission_days=record.mission_days,
        late_count=record.late_count, points=record.points,
    )


# ------------------------------------------------------------ adjustments
@router.get("/periods/{period_id}/adjustments", response_model=List[AdjustmentResponse])
async def list_adjustments(
    book_id: uuid.UUID, period_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[AdjustmentResponse]:
    rows = await PayrollService(session).adjustments(user.id, period_id)
    names = await _names(session, book_id)
    return [
        AdjustmentResponse(
            id=row.id, user_id=row.user_id, display_name=names.get(row.user_id, "—"),
            kind=row.kind.value, mode=row.mode.value, value=row.value,
            reason=row.reason, is_approved=row.approved_at is not None,
        )
        for row in rows
    ]


@router.post("/periods/{period_id}/adjustments", response_model=AdjustmentResponse,
             status_code=201)
async def add_adjustment(
    book_id: uuid.UUID, period_id: uuid.UUID, body: AdjustmentRequest,
    user: CurrentUser, session: SessionDep,
) -> AdjustmentResponse:
    row = await PayrollService(session).add_adjustment(
        user.id, period_id, body.user_id,
        _as_enum(AdjustmentKind, body.kind, "kind"),
        _as_enum(AdjustmentMode, body.mode, "mode"),
        body.value, reason=body.reason,
    )
    names = await _names(session, book_id)
    return AdjustmentResponse(
        id=row.id, user_id=row.user_id, display_name=names.get(row.user_id, "—"),
        kind=row.kind.value, mode=row.mode.value, value=row.value,
        reason=row.reason, is_approved=row.approved_at is not None,
    )


@router.post("/periods/{period_id}/adjustments/{adjustment_id}/approve",
             response_model=AdjustmentResponse)
async def approve_adjustment(
    book_id: uuid.UUID, period_id: uuid.UUID, adjustment_id: uuid.UUID,
    user: CurrentUser, session: SessionDep,
) -> AdjustmentResponse:
    """Recording and approving are separate on purpose."""
    row = await PayrollService(session).approve_adjustment(user.id, adjustment_id)
    names = await _names(session, book_id)
    return AdjustmentResponse(
        id=row.id, user_id=row.user_id, display_name=names.get(row.user_id, "—"),
        kind=row.kind.value, mode=row.mode.value, value=row.value,
        reason=row.reason, is_approved=row.approved_at is not None,
    )


# --------------------------------------------------------------- payslips
def _payslip(row, names) -> PayslipResponse:
    paid = sum((p.amount for p in row.payments), ZERO)
    return PayslipResponse(
        id=row.id, user_id=row.user_id, display_name=names.get(row.user_id, "—"),
        distributable_snapshot=row.distributable_snapshot,
        share_basis=row.share_basis_snapshot.value,
        share_value=row.share_value_snapshot,
        base_share=row.base_share, adjustments_total=row.adjustments_total,
        net_pay=row.net_pay, paid=paid, outstanding=row.net_pay - paid,
        currency=row.currency,
        payments=[
            PaymentResponse(id=p.id, amount=p.amount, currency=p.currency,
                            paid_on=p.paid_on, reference=p.reference)
            for p in row.payments
        ],
    )


@router.post("/periods/{period_id}/calculate", response_model=List[PayslipResponse])
async def calculate(
    book_id: uuid.UUID, period_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[PayslipResponse]:
    """Produce a payslip per member, freezing every input onto it.

    Refuses rather than returning an empty list when nobody has a share: a run
    that produces nothing because the question was never answered is not an
    empty result.
    """
    payroll = PayrollService(session)
    period = await payroll.get_period(period_id)
    if not await payroll.shares(book_id, user.id, period.ends_on):
        raise ValidationError(
            "no member has a share yet, so a calculation would produce nothing. "
            "Set shares first: PUT /books/{book_id}/shares"
        )

    slips = await payroll.calculate(user.id, period_id)
    names = await _names(session, book_id)
    return [_payslip(slip, names) for slip in slips]


@router.get("/periods/{period_id}/payslips", response_model=List[PayslipResponse])
async def list_payslips(
    book_id: uuid.UUID, period_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[PayslipResponse]:
    """Everyone's, or just your own — the service decides, by permission."""
    slips = await PayrollService(session).payslips(user.id, period_id)
    names = await _names(session, book_id)
    return [_payslip(slip, names) for slip in slips]


@router.post("/payslips/{payslip_id}/payments", response_model=PayslipResponse,
             status_code=201)
async def pay(
    book_id: uuid.UUID, payslip_id: uuid.UUID, body: PayRequest,
    user: CurrentUser, session: SessionDep,
) -> PayslipResponse:
    """Hand over some or all of what is owed. Instalments are the norm."""
    from ...modules.payroll.models import Payslip

    payroll = PayrollService(session)
    await payroll.pay(
        user.id, payslip_id, body.amount, paid_on=body.paid_on, reference=body.reference
    )

    slip = await session.get(Payslip, payslip_id)
    await session.refresh(slip)
    return _payslip(slip, await _names(session, book_id))


# --------------------------------------------------------------- treasury
@router.get("/funds", response_model=List[FundResponse])
async def list_funds(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[FundResponse]:
    treasury = TreasuryService(session)
    return [
        FundResponse(
            id=fund.id, name=fund.name, kind=fund.kind.value,
            is_active=fund.is_active,
            balance=await treasury.balance(book_id, user.id, fund.id),
        )
        for fund in await treasury.funds(book_id, user.id)
    ]


@router.post("/funds", response_model=FundResponse, status_code=201)
async def create_fund(
    book_id: uuid.UUID, body: FundRequest, user: CurrentUser, session: SessionDep
) -> FundResponse:
    fund = await TreasuryService(session).create_fund(
        book_id, user.id, body.name, _as_enum(FundKind, body.kind, "kind")
    )
    return FundResponse(id=fund.id, name=fund.name, kind=fund.kind.value,
                        is_active=fund.is_active, balance=ZERO)


@router.delete("/funds/{fund_id}", status_code=204)
async def delete_fund(
    book_id: uuid.UUID, fund_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Refused once the fund has taken money — deactivate it instead."""
    await TreasuryService(session).delete_fund(book_id, user.id, fund_id)


@router.get("/funds/{fund_id}/rules", response_model=List[TreasuryRuleResponse])
async def list_rules(
    book_id: uuid.UUID, fund_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[TreasuryRuleResponse]:
    rows = await TreasuryService(session).rules(book_id, user.id, fund_id)
    return [
        TreasuryRuleResponse(
            id=r.id, fund_id=r.fund_id, basis=r.basis.value, value=r.value,
            category=r.category, effective_from=r.effective_from, is_active=r.is_active,
        )
        for r in rows
    ]


@router.post("/funds/{fund_id}/rules", response_model=TreasuryRuleResponse, status_code=201)
async def add_rule(
    book_id: uuid.UUID, fund_id: uuid.UUID, body: TreasuryRuleRequest,
    user: CurrentUser, session: SessionDep,
) -> TreasuryRuleResponse:
    rule = await TreasuryService(session).add_rule(
        book_id, user.id, fund_id, _as_enum(RuleBasis, body.basis, "basis"),
        body.value, body.effective_from, body.category,
    )
    return TreasuryRuleResponse(
        id=rule.id, fund_id=rule.fund_id, basis=rule.basis.value, value=rule.value,
        category=rule.category, effective_from=rule.effective_from,
        is_active=rule.is_active,
    )


@router.delete("/funds/{fund_id}/rules/{rule_id}", status_code=204)
async def delete_rule(
    book_id: uuid.UUID, fund_id: uuid.UUID, rule_id: uuid.UUID,
    user: CurrentUser, session: SessionDep,
) -> None:
    """Always safe: what past periods took is snapshotted, not recomputed."""
    await TreasuryService(session).delete_rule(book_id, user.id, rule_id)
