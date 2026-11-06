"""What a person holds, valued at today's price, and notes on what they put money into.

Prices of gold, coins and metals come from the market feeds (`rates/metals.py`); currencies and crypto
from the existing quote function. Nothing here touches the ledger.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Request

from ...modules.portfolio.catalog import CATALOG
from ...modules.portfolio.service import PortfolioService
from ..deps import CurrentUser, RatesDep, SessionDep
from ..schemas import (
    FinancialNoteRequest,
    FinancialNoteResponse,
    InstrumentResponse,
    NoteEntryRequest,
    NoteEntryResponse,
    PortfolioHoldingRequest,
    PortfolioHoldingResponse,
    PortfolioHoldingUpdate,
    PortfolioResponse,
)

router = APIRouter(prefix="/books/{book_id}/portfolio", tags=["portfolio"])
market = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _service(request: Request, session, rates) -> PortfolioService:
    return PortfolioService(
        session, request.app.state.metals, rates, request.app.state.fiat
    )


def _holding(view) -> PortfolioHoldingResponse:
    h = view.holding
    return PortfolioHoldingResponse(
        id=h.id, instrument=h.instrument, name=view.name, unit=view.unit, group=view.group,
        quantity=h.quantity, cost=h.cost, acquired_on=h.acquired_on, note=h.note,
        price=view.price, value=view.value, profit=view.profit,
        profit_percent=view.profit_percent, price_source=view.source, exact=view.exact,
        as_of=view.as_of,
    )


def _note(view) -> FinancialNoteResponse:
    return FinancialNoteResponse(
        id=view.note.id, title=view.note.title, text=view.note.text,
        entries=[
            NoteEntryResponse(id=e.id, kind=e.kind, occurred_on=e.occurred_on,
                              amount=e.amount, memo=e.memo)
            for e in view.entries
        ],
        spent=view.spent, value=view.value, value_on=view.value_on, gain=view.gain,
    )


@market.get("/instruments", response_model=List[InstrumentResponse])
async def instruments(
    request: Request, user: CurrentUser, session: SessionDep, rates: RatesDep
) -> List[InstrumentResponse]:
    """Everything that can be held, with today's price in toman where the market has one."""
    table = await _service(request, session, rates).prices()
    out = []
    for item in CATALOG:
        price = table.get(item.code)
        out.append(InstrumentResponse(
            code=item.code, name=item.name, unit=item.unit, group=item.group, source=item.source,
            price=price.value if price else None, exact=bool(price and price.exact),
            price_source=price.source if price else "", as_of=price.as_of if price else None,
        ))
    return out


@router.get("", response_model=PortfolioResponse)
async def portfolio(
    book_id: uuid.UUID, request: Request, user: CurrentUser, session: SessionDep, rates: RatesDep
) -> PortfolioResponse:
    """The holdings with what each is worth today, and the total."""
    view = await _service(request, session, rates).view(book_id, user.id)
    return PortfolioResponse(
        currency=view.currency, holdings=[_holding(row) for row in view.rows],
        total_value=view.total_value, total_cost=view.total_cost,
        total_profit=view.total_profit, unpriced=view.unpriced,
    )


@router.post("/holdings", response_model=PortfolioHoldingResponse, status_code=201)
async def add_holding(
    book_id: uuid.UUID, body: PortfolioHoldingRequest, request: Request,
    user: CurrentUser, session: SessionDep, rates: RatesDep,
) -> PortfolioHoldingResponse:
    service = _service(request, session, rates)
    created = await service.add_holding(
        book_id, user.id, body.instrument, body.quantity, cost=body.cost,
        acquired_on=body.acquired_on, label=body.label, unit_price=body.unit_price, note=body.note,
    )
    view = await service.view(book_id, user.id)
    return _holding(next(row for row in view.rows if row.holding.id == created.id))


@router.patch("/holdings/{holding_id}", response_model=PortfolioHoldingResponse)
async def update_holding(
    book_id: uuid.UUID, holding_id: uuid.UUID, body: PortfolioHoldingUpdate, request: Request,
    user: CurrentUser, session: SessionDep, rates: RatesDep,
) -> PortfolioHoldingResponse:
    service = _service(request, session, rates)
    await service.update_holding(
        book_id, user.id, holding_id, quantity=body.quantity, cost=body.cost,
        unit_price=body.unit_price, label=body.label, note=body.note, acquired_on=body.acquired_on,
    )
    view = await service.view(book_id, user.id)
    return _holding(next(row for row in view.rows if row.holding.id == holding_id))


@router.delete("/holdings/{holding_id}", status_code=204)
async def delete_holding(
    book_id: uuid.UUID, holding_id: uuid.UUID, request: Request,
    user: CurrentUser, session: SessionDep, rates: RatesDep,
) -> None:
    await _service(request, session, rates).delete_holding(book_id, user.id, holding_id)


@router.get("/notes", response_model=List[FinancialNoteResponse])
async def list_notes(
    book_id: uuid.UUID, request: Request, user: CurrentUser, session: SessionDep, rates: RatesDep
) -> List[FinancialNoteResponse]:
    return [_note(v) for v in await _service(request, session, rates).notes(book_id, user.id)]


@router.post("/notes", response_model=FinancialNoteResponse, status_code=201)
async def add_note(
    book_id: uuid.UUID, body: FinancialNoteRequest, request: Request,
    user: CurrentUser, session: SessionDep, rates: RatesDep,
) -> FinancialNoteResponse:
    service = _service(request, session, rates)
    created = await service.add_note(book_id, user.id, body.title, body.text)
    views = await service.notes(book_id, user.id)
    return _note(next(v for v in views if v.note.id == created.id))


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    book_id: uuid.UUID, note_id: uuid.UUID, request: Request,
    user: CurrentUser, session: SessionDep, rates: RatesDep,
) -> None:
    await _service(request, session, rates).delete_note(book_id, user.id, note_id)


@router.post("/notes/{note_id}/entries", response_model=FinancialNoteResponse, status_code=201)
async def add_entry(
    book_id: uuid.UUID, note_id: uuid.UUID, body: NoteEntryRequest, request: Request,
    user: CurrentUser, session: SessionDep, rates: RatesDep,
) -> FinancialNoteResponse:
    """Put money into the thing, say what it is worth now, or just write a remark."""
    service = _service(request, session, rates)
    await service.add_entry(
        book_id, user.id, note_id, body.kind, body.occurred_on, body.amount, body.memo
    )
    views = await service.notes(book_id, user.id)
    return _note(next(v for v in views if v.note.id == note_id))


@router.delete("/notes/{note_id}/entries/{entry_id}", response_model=FinancialNoteResponse)
async def delete_entry(
    book_id: uuid.UUID, note_id: uuid.UUID, entry_id: uuid.UUID, request: Request,
    user: CurrentUser, session: SessionDep, rates: RatesDep,
) -> FinancialNoteResponse:
    service = _service(request, session, rates)
    await service.delete_entry(book_id, user.id, note_id, entry_id)
    views = await service.notes(book_id, user.id)
    return _note(next(v for v in views if v.note.id == note_id))
