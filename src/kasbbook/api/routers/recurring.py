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
from ...modules.recurring.models import Period
from ...modules.recurring.service import RecurringService
from ...shared.errors import ValidationError
from ..deps import CurrentUser, SessionDep
from ..schemas import RecurringRequest, RecurringResponse

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
        is_active=row.is_active,
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
        description=body.description,
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
