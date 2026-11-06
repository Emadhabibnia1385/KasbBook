"""The transactions of every book the person can reach, in one list.

The dashboard and the transactions page are about all of someone's books unless they pick one, so
this is the same list as a single book's, put together across them. Which books are listed is still
decided by `LedgerService.transactions`, which refuses a book the caller is not in: a book id that
is not theirs is answered like one that does not exist.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Query

from ...modules.books.service import BookService
from ...modules.ledger.attachments import AttachmentService
from ...modules.ledger.models import Flow
from ...modules.ledger.service import LedgerService
from ...shared.errors import NotFound, ValidationError
from ..deps import CurrentUser, SessionDep
from ..schemas import AllTransactionPage, BookedTransactionResponse, CurrencyTotal
from .books import _as_enum, _transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _day(value: Optional[str], field: str) -> Optional[date_type]:
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field} must be a date like 2026-08-25") from None


@router.get("", response_model=AllTransactionPage)
async def list_all_transactions(
    user: CurrentUser,
    session: SessionDep,
    book_id: Optional[List[uuid.UUID]] = Query(default=None, description="only these books; all when absent"),
    since: Optional[str] = None,
    until: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    flow: Optional[List[str]] = Query(default=None),
    category: Optional[List[str]] = Query(default=None),
    currency: Optional[List[str]] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=100),
    sort: str = Query(default="newest"),
) -> AllTransactionPage:
    books = await BookService(session).books_for_user(user.id)
    by_id = {book.id: book for book in books}
    if book_id:
        missing = [wanted for wanted in book_id if wanted not in by_id]
        if missing:
            raise NotFound("book")
        books = [by_id[wanted] for wanted in dict.fromkeys(book_id)]

    ledger = LedgerService(session)
    flows = [_as_enum(Flow, value, "flow") for value in flow] if flow else None
    rows = []
    totals: Dict[str, List[Decimal]] = {}
    for book in books:
        found = await ledger.transactions(
            book.id, user.id, _day(since, "since"), _day(until, "until"),
            flows=flows, categories=category or None, text=q,
            currencies=[c.upper() for c in currency] if currency else None, sort="oldest",
        )
        income, expense = LedgerService.split_totals(found)
        line = totals.setdefault(book.base_currency, [Decimal("0"), Decimal("0")])
        line[0] += income
        line[1] += expense
        rows.extend(found)
    rows = list(ledger._sorted(rows, sort))

    start = (page - 1) * per_page
    visible = rows[start:start + per_page]
    activities = await ledger.activities(user.id, visible)
    counts: Dict[uuid.UUID, int] = {}
    for book in books:
        ids = [row.id for row in visible if row.book_id == book.id]
        if ids:
            counts.update(await AttachmentService(session).counts(book.id, user.id, ids))

    items = []
    for row in visible:
        book = by_id[row.book_id]
        base = _transaction(row, activities[row.id], counts.get(row.id, 0))
        items.append(BookedTransactionResponse(
            **base.model_dump(), book_id=book.id, book_name=book.name, book_currency=book.base_currency,
        ))
    return AllTransactionPage(
        items=items, total=len(rows), page=page, per_page=per_page,
        totals=[CurrencyTotal(currency=code, income=pair[0], expense=pair[1]) for code, pair in totals.items()],
    )
