"""The one place money that changes shape is written to the journal."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..ledger.service import LedgerService
from .models import CapitalMovement

# Accounts, by code; the ledger creates any a book does not have yet.
CASH = "1000"
ASSETS = "1500"
FUNDS = "1600"
LOANS = "2000"


async def post_movement(
    session: AsyncSession,
    book_id: uuid.UUID,
    actor_user_id: Optional[uuid.UUID],
    on: date,
    kind: str,
    lines: Sequence[Tuple[str, object, object]],
    cash_delta,
    memo: Optional[str] = None,
    asset_id: Optional[uuid.UUID] = None,
    fund_id: Optional[uuid.UUID] = None,
    loan_id: Optional[uuid.UUID] = None,
) -> CapitalMovement:
    """Write a balanced journal entry from `(account code, debit, credit)` lines, and remember it.

    A closed period refuses it like any other entry. The movement row carries the cash it moved so
    the wallet can follow without reading the journal.
    """
    ledger = LedgerService(session)
    await ledger._require_open_date(book_id, on)
    await ledger.ensure_chart_of_accounts(book_id)
    resolved = []
    for code, debit, credit in lines:
        resolved.append(((await ledger.account(book_id, code)).id, debit, credit))
    entry = await ledger.post_entry(book_id, on, resolved, memo=memo)
    amount = sum((debit for _, debit, _ in lines), 0)
    movement = CapitalMovement(
        book_id=book_id, actor_user_id=actor_user_id, occurred_on=on, kind=kind,
        amount=amount, cash_delta=cash_delta, memo=memo, asset_id=asset_id, fund_id=fund_id,
        loan_id=loan_id, journal_entry_id=entry.id,
    )
    session.add(movement)
    await session.flush()
    return movement
