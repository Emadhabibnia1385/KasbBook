"""Rules that repeat: rent, a salary, a subscription.

Defining one here is the same act as defining one in the bot. Booking what has
come due belongs to the reminder loop, so nothing in this module writes a
transaction.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter

from ...modules.ledger.models import Flow
from ...modules.recurring.models import Mode, Period
from ...modules.recurring.service import RecurringService
from ...shared.errors import ValidationError
from ..deps import CurrentUser, SessionDep
from ..schemas import (
    ConfirmOccurrence,
    PendingOccurrenceResponse,
    RecurringRequest,
    RecurringResponse,
    RecurringUpdate,
)

router = APIRouter(prefix="/books/{book_id}/recurring", tags=["recurring"])


def _as_enum(enum_class, value: str, field: str):
    try:
        return enum_class(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_class)
        raise ValidationError(f"{field} must be one of: {allowed}") from None


def _rule(row) -> RecurringResponse:
    return RecurringResponse(
        id=row.id, flow=row.flow.value, category=row.category, amount=row.amount,
        description=row.description, period=row.period.value,
        next_run_on=row.next_run_on, last_run_on=row.last_run_on,
        is_active=row.is_active, mode=row.mode.value,
    )


@router.get("", response_model=List[RecurringResponse])
async def list_rules(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[RecurringResponse]:
    return [_rule(row) for row in await RecurringService(session).list_rules(book_id, user.id)]


@router.post("", response_model=RecurringResponse, status_code=201)
async def create_rule(
    book_id: uuid.UUID, body: RecurringRequest, user: CurrentUser, session: SessionDep
) -> RecurringResponse:
    rule = await RecurringService(session).create(
        book_id, user.id, _as_enum(Flow, body.flow, "flow"), body.category,
        body.amount, _as_enum(Period, body.period, "period"), body.starts_on,
        description=body.description, mode=_as_enum(Mode, body.mode, "mode"),
        first_booked=body.first_booked,
    )
    return _rule(rule)


def pending_response(occurrence, rule, book) -> PendingOccurrenceResponse:
    return PendingOccurrenceResponse(
        id=occurrence.id, rule_id=rule.id, book_id=book.id, book_name=book.name,
        currency=book.base_currency, due_on=occurrence.due_on, flow=rule.flow.value,
        category=rule.category, amount=rule.amount, description=rule.description,
    )


@router.get("/pending", response_model=List[PendingOccurrenceResponse])
async def list_pending(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[PendingOccurrenceResponse]:
    """Due dates of rules that ask first, waiting for someone to confirm or skip them."""
    from ...modules.books.service import BookService

    book = await BookService(session).get_book(book_id)
    rows = await RecurringService(session).pending(book_id, user.id)
    return [pending_response(occurrence, rule, book) for occurrence, rule in rows]


@router.post("/occurrences/{occurrence_id}/confirm", status_code=204)
async def confirm_occurrence(
    book_id: uuid.UUID, occurrence_id: uuid.UUID, body: ConfirmOccurrence,
    user: CurrentUser, session: SessionDep,
) -> None:
    """Record one waiting date as a real transaction, on its own day."""
    await RecurringService(session).confirm(book_id, user.id, occurrence_id, body.amount)


@router.post("/occurrences/{occurrence_id}/skip", status_code=204)
async def skip_occurrence(
    book_id: uuid.UUID, occurrence_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Leave one waiting date unrecorded; the rule carries on with the next."""
    await RecurringService(session).skip(book_id, user.id, occurrence_id)


@router.patch("/{rule_id}", response_model=RecurringResponse)
async def update_rule(
    book_id: uuid.UUID, rule_id: uuid.UUID, body: RecurringUpdate,
    user: CurrentUser, session: SessionDep,
) -> RecurringResponse:
    """Change a rule's mode, amount or note. What it already recorded does not change."""
    rule = await RecurringService(session).update_rule(
        book_id, user.id, rule_id,
        mode=_as_enum(Mode, body.mode, "mode") if body.mode else None,
        amount=body.amount, description=body.description,
    )
    return _rule(rule)


@router.post("/{rule_id}/toggle", response_model=RecurringResponse)
async def toggle_rule(
    book_id: uuid.UUID, rule_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RecurringResponse:
    """Pause an active rule, or resume a paused one."""
    return _rule(await RecurringService(session).toggle(book_id, user.id, rule_id))


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    book_id: uuid.UUID, rule_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await RecurringService(session).delete(book_id, user.id, rule_id)


# Every book the person can reach, in one list: what the transactions page shows when no single book is chosen.
everywhere = APIRouter(prefix="/recurring", tags=["recurring"])


@everywhere.get("/pending", response_model=List[PendingOccurrenceResponse])
async def list_pending_everywhere(
    user: CurrentUser, session: SessionDep
) -> List[PendingOccurrenceResponse]:
    from ...modules.books.service import BookService
    from ...shared.errors import NotFound, PermissionDenied

    service = RecurringService(session)
    out: List[PendingOccurrenceResponse] = []
    for book in await BookService(session).books_for_user(user.id):
        try:
            rows = await service.pending(book.id, user.id)
        except (NotFound, PermissionDenied):
            continue
        out.extend(pending_response(occurrence, rule, book) for occurrence, rule in rows)
    out.sort(key=lambda row: row.due_on)
    return out
