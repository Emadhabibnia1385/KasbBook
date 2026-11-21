"""Income that follows a person from a team or business book into their own.

These are a person's own settings: a link is visible and changeable only by the member it belongs to,
because what someone is paid is theirs to see (see `VIEW_OTHERS_PAY`).
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Query

from ...modules.income.service import IncomeSyncService, LinkView
from ..deps import CurrentUser, SessionDep, bank_choice
from ..schemas import (
    IncomeEntryResponse,
    IncomeLinkRequest,
    IncomeLinkResponse,
    IncomeLinkUpdate,
)

router = APIRouter(prefix="/income-links", tags=["income"])


def _link(view: LinkView) -> IncomeLinkResponse:
    link = view.link
    return IncomeLinkResponse(
        id=link.id, source_book_id=link.source_book_id, source_book_name=view.source_name,
        target_book_id=link.target_book_id, target_book_name=view.target_name, mode=link.mode,
        category=link.category, starts_on=link.starts_on, bank_account_id=link.bank_account_id,
        is_active=link.is_active, entries=view.entries, total=view.total, problems=view.problems,
        created_at=link.created_at,
    )


async def _one(session, user_id: uuid.UUID, link_id: uuid.UUID) -> IncomeLinkResponse:
    from ...shared.errors import NotFound

    for view in await IncomeSyncService(session).mine(user_id):
        if view.link.id == link_id:
            return _link(view)
    raise NotFound("این پیوند پیدا نشد.")


@router.get("", response_model=List[IncomeLinkResponse])
async def list_links(user: CurrentUser, session: SessionDep) -> List[IncomeLinkResponse]:
    """Your links: which book's income goes into which of yours, how, and how much so far."""
    return [_link(view) for view in await IncomeSyncService(session).mine(user.id)]


@router.post("", response_model=IncomeLinkResponse, status_code=201)
async def create_link(
    body: IncomeLinkRequest, user: CurrentUser, session: SessionDep
) -> IncomeLinkResponse:
    """Start writing your income from a team or business book into your own.

    It writes what is already due from `starts_on` at once, then keeps itself true: a payment, a closing
    period or a change on a day updates the entry for it, never writes a second one.
    """
    link = await IncomeSyncService(session).create_link(
        user.id, source_book_id=body.source_book_id, target_book_id=body.target_book_id,
        mode=body.mode, category=body.category, starts_on=body.starts_on,
        bank_account_id=bank_choice(body),
    )
    return await _one(session, user.id, link.id)


@router.patch("/{link_id}", response_model=IncomeLinkResponse)
async def update_link(
    link_id: uuid.UUID, body: IncomeLinkUpdate, user: CurrentUser, session: SessionDep
) -> IncomeLinkResponse:
    """Change how often it is written, what it is called, from when, or switch it off.

    A different mode takes back what the old one wrote and writes it again the new way.
    """
    await IncomeSyncService(session).update_link(
        user.id, link_id, **body.model_dump(exclude_unset=True)
    )
    return await _one(session, user.id, link_id)


@router.delete("/{link_id}", status_code=204)
async def delete_link(
    link_id: uuid.UUID, user: CurrentUser, session: SessionDep,
    remove_income: bool = Query(default=False, description="also take back the income it wrote"),
) -> None:
    """End the link. The income already written stays as ordinary transactions unless asked."""
    await IncomeSyncService(session).delete_link(user.id, link_id, remove_income=remove_income)


@router.post("/{link_id}/resync", response_model=IncomeLinkResponse)
async def resync(link_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> IncomeLinkResponse:
    """Work it all out again from the source: catches up, and retries what the book refused."""
    await IncomeSyncService(session).resync(user.id, link_id)
    return await _one(session, user.id, link_id)


@router.get("/{link_id}/entries", response_model=List[IncomeEntryResponse])
async def entries(
    link_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[IncomeEntryResponse]:
    rows = await IncomeSyncService(session).entries(user.id, link_id)
    return [IncomeEntryResponse(
        ref=row.ref, occurred_on=row.occurred_on, amount=row.amount,
        transaction_id=row.transaction_id, problem=row.problem,
    ) for row in rows]
