"""Assets, rotating funds and the debts they leave.

Money that changes shape without being earned or spent: buying gold (alone or on a loan), paying into
a rotating savings fund and being paid out of it. None of it is income or an expense, so it never
shows in those reports; it shows here, and in the wallet's cash.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter

from ...modules.capital.models import AssetKind
from ...modules.capital.service import CapitalService
from ...shared.errors import ValidationError
from ..deps import CurrentUser, SessionDep
from ..schemas import (
    AssetRequest,
    AssetResponse,
    AssetSaleRequest,
    CapitalOverviewResponse,
    CircleMovementRequest,
    CircleRequest,
    CircleResponse,
)

router = APIRouter(prefix="/books/{book_id}/capital", tags=["capital"])


def _asset(row) -> AssetResponse:
    return AssetResponse(
        id=row.id, name=row.name, kind=row.kind.value, cost=row.cost, quantity=row.quantity,
        unit=row.unit, acquired_on=row.acquired_on, loan_id=row.loan_id, note=row.note,
        sold_on=row.sold_on, sold_for=row.sold_for,
    )


def _fund(row) -> CircleResponse:
    return CircleResponse(
        id=row.id, name=row.name, monthly_amount=row.monthly_amount, months=row.months,
        payout_amount=row.payout_amount, starts_on=row.starts_on, turn_month=row.turn_month,
        paid_months=row.paid_months, claim=row.claim, owed=row.owed,
        received_on=row.received_on, received_amount=row.received_amount,
    )


@router.get("/overview", response_model=CapitalOverviewResponse)
async def overview(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> CapitalOverviewResponse:
    """What the book holds and owes beyond its cash: assets, claims on funds, and debts."""
    result = await CapitalService(session).overview(book_id, user.id)
    return CapitalOverviewResponse(
        assets=result.assets, fund_claims=result.fund_claims,
        liabilities=result.liabilities, net=result.net,
    )


@router.get("/assets", response_model=List[AssetResponse])
async def list_assets(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[AssetResponse]:
    return [_asset(row) for row in await CapitalService(session).list_assets(book_id, user.id)]


@router.post("/assets", response_model=AssetResponse, status_code=201)
async def buy_asset(
    book_id: uuid.UUID, body: AssetRequest, user: CurrentUser, session: SessionDep
) -> AssetResponse:
    """Buy something that is kept. With an installment and a count it is bought on a loan."""
    try:
        kind = AssetKind(body.kind)
    except ValueError:
        raise ValidationError(
            "kind must be one of: " + ", ".join(member.value for member in AssetKind)
        ) from None
    asset = await CapitalService(session).buy_asset(
        book_id, user.id, body.name, kind, body.cost, body.acquired_on,
        down_payment=body.down_payment, installment_amount=body.installment_amount,
        installment_count=body.installment_count, loan_starts_on=body.loan_starts_on,
        quantity=body.quantity, unit=body.unit, note=body.note,
    )
    return _asset(asset)


@router.post("/assets/{asset_id}/sell", response_model=AssetResponse)
async def sell_asset(
    book_id: uuid.UUID, asset_id: uuid.UUID, body: AssetSaleRequest,
    user: CurrentUser, session: SessionDep,
) -> AssetResponse:
    """Sell it: the cost returns as cash, and the gain or loss is recorded as income or an expense."""
    return _asset(await CapitalService(session).sell_asset(
        book_id, user.id, asset_id, body.price, body.sold_on))


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(
    book_id: uuid.UUID, asset_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await CapitalService(session).delete_asset(book_id, user.id, asset_id)


@router.get("/funds", response_model=List[CircleResponse])
async def list_funds(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[CircleResponse]:
    return [_fund(row) for row in await CapitalService(session).list_funds(book_id, user.id)]


@router.post("/funds", response_model=CircleResponse, status_code=201)
async def create_fund(
    book_id: uuid.UUID, body: CircleRequest, user: CurrentUser, session: SessionDep
) -> CircleResponse:
    fund = await CapitalService(session).create_fund(
        book_id, user.id, body.name, body.monthly_amount, body.months,
        body.payout_amount, body.starts_on, body.turn_month,
    )
    return _fund(fund)


@router.post("/funds/{fund_id}/contribute", response_model=CircleResponse)
async def contribute(
    book_id: uuid.UUID, fund_id: uuid.UUID, body: CircleMovementRequest,
    user: CurrentUser, session: SessionDep,
) -> CircleResponse:
    """Pay one month into the fund (or, after the turn, back what was received beyond what was paid)."""
    return _fund(await CapitalService(session).contribute(
        book_id, user.id, fund_id, body.on, body.amount))


@router.post("/funds/{fund_id}/receive", response_model=CircleResponse)
async def receive_payout(
    book_id: uuid.UUID, fund_id: uuid.UUID, body: CircleMovementRequest,
    user: CurrentUser, session: SessionDep,
) -> CircleResponse:
    """The turn comes: the pool is paid out. Not income."""
    return _fund(await CapitalService(session).receive_payout(
        book_id, user.id, fund_id, body.on, body.amount))


@router.delete("/funds/{fund_id}", status_code=204)
async def delete_fund(
    book_id: uuid.UUID, fund_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await CapitalService(session).delete_fund(book_id, user.id, fund_id)
