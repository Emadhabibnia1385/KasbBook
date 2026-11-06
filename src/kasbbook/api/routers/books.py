"""Books, their members, and the transactions inside them.

Every route calls the same application services the bot calls. Permission
checks live in those services, not here — so a route cannot accidentally be
more permissive than the equivalent button.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import Response
from urllib.parse import quote

from ...modules.books.models import BookType, CostPolicy, Permission, Role
from ...modules.books.service import BookService
from ...modules.books.invitations import InvitationService
from ...modules.identity.models import MESSENGERS, Provider
from ...modules.identity.service import IdentityService
from ...modules.ledger.models import Flow, Scope
from ...modules.exchange.service import ExchangeService
from ...modules.ledger.attachments import MAX_BYTES, AttachmentService, sniff
from ...modules.ledger.service import LedgerService
from ...modules.ledger.categories import CategoryService
from ...shared.errors import NotFound, ValidationError
from ..deps import CurrentUser, SessionDep, SettingsDep
from ..schemas import (
    AttachmentResponse,
    BaseCurrencyRequest,
    BookRequest,
    ConversionRequest,
    ConversionResponse,
    CostPolicyRequest,
    CurrencyBalanceResponse,
    CurrencyOptionResponse,
    CurrencyToggleRequest,
    BookResponse,
    CalendarRequest,
    InviteRequest,
    MemberResponse,
    TransactionPage,
    TransactionRequest,
    TransactionResponse,
    TransactionUpdate,
    CategoryRequest,
    CategoryUpdate,
    CategoryResponse,
    TeamInviteRequest,
    InvitationResponse,
)

router = APIRouter(prefix="/books", tags=["books"])

SCOPE_FOR_BOOK = {
    BookType.PERSONAL: Scope.PERSONAL,
    BookType.BUSINESS: Scope.WORK,
    BookType.TEAM: Scope.TEAM,
    BookType.ORGANIZATION: Scope.TEAM,
}


def _as_enum(enum_class, value: str, field: str):
    """A bad enum value is the caller's mistake, not a 500."""
    try:
        return enum_class(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_class)
        raise ValidationError(f"{field} must be one of: {allowed}") from None


def _book_response(book) -> BookResponse:
    return BookResponse(
        id=book.id, name=book.name, type=book.type.value, currency=book.base_currency,
        cost_policy=book.cost_policy.value, calendar=book.calendar, created_at=book.created_at,
    )


@router.get("", response_model=List[BookResponse])
async def list_books(user: CurrentUser, session: SessionDep) -> List[BookResponse]:
    # An account made before every one started with a book gets its personal one now.
    await IdentityService(session).ensure_default_book(user.id)
    books = await BookService(session).books_for_user(user.id)
    return [
        _book_response(b)
        for b in books
    ]


@router.post("", response_model=BookResponse, status_code=201)
async def create_book(
    body: BookRequest, user: CurrentUser, session: SessionDep
) -> BookResponse:
    book = await BookService(session).create_book(
        user.id, body.name, _as_enum(BookType, body.type, "type"),
        body.currency or "IRT",
        _as_enum(CostPolicy, body.cost_policy, "cost_policy")
        if body.cost_policy else CostPolicy.BEFORE_SPLIT,
        body.calendar or "jalali",
    )
    return _book_response(book)


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> BookResponse:
    from ...modules.books.models import Permission

    books = BookService(session)
    await books.require(book_id, user.id, Permission.VIEW_TRANSACTIONS)
    book = await books.get_book(book_id)
    return _book_response(book)


@router.put("/{book_id}/calendar", response_model=BookResponse)
async def set_calendar(
    book_id: uuid.UUID, body: CalendarRequest, user: CurrentUser, session: SessionDep
) -> BookResponse:
    """Choose whether this book's months and years follow the Jalali or the Gregorian calendar."""
    book = await BookService(session).set_calendar(user.id, book_id, body.calendar)
    return _book_response(book)


@router.put("/{book_id}/cost-policy", response_model=BookResponse)
async def set_cost_policy(
    book_id: uuid.UUID, body: CostPolicyRequest, user: CurrentUser, session: SessionDep
) -> BookResponse:
    """Choose whether costs come off before the split or out of the treasury."""
    book = await BookService(session).set_cost_policy(
        user.id, book_id, _as_enum(CostPolicy, body.cost_policy, "cost_policy")
    )
    return _book_response(book)


# ------------------------------------------------------ wallet & currencies
def _option_response(o) -> CurrencyOptionResponse:
    return CurrencyOptionResponse(code=o.code, name=o.name, enabled=o.enabled,
                                  is_base=o.is_base, kind=o.kind, symbol=o.symbol,
                                  region=o.region)


@router.get("/{book_id}/currencies", response_model=List[CurrencyOptionResponse])
async def list_currencies(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[CurrencyOptionResponse]:
    """Every currency this book could hold, and whether it is ticked."""
    options = await ExchangeService(session).catalog_options(user.id, book_id)
    return [_option_response(o) for o in options]


@router.put("/{book_id}/currencies/{code}", response_model=List[CurrencyOptionResponse])
async def set_currency(
    book_id: uuid.UUID, code: str, body: CurrencyToggleRequest,
    user: CurrentUser, session: SessionDep,
) -> List[CurrencyOptionResponse]:
    exchange = ExchangeService(session)
    await exchange.set_enabled(user.id, book_id, code, body.enabled)
    return [_option_response(o) for o in await exchange.catalog_options(user.id, book_id)]


@router.put("/{book_id}/base-currency", response_model=BookResponse)
async def set_base_currency(
    book_id: uuid.UUID, body: BaseCurrencyRequest, user: CurrentUser, session: SessionDep
) -> BookResponse:
    """Choose the unit the book is kept in. Refused once the book has history."""
    await ExchangeService(session).set_base(user.id, book_id, body.code)
    book = await BookService(session).get_book(book_id)
    return _book_response(book)


@router.get("/{book_id}/wallet", response_model=List[CurrencyBalanceResponse])
async def wallet(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[CurrencyBalanceResponse]:
    """What the book holds, in the currency it holds it in."""
    balances = await ExchangeService(session).balances(user.id, book_id)
    return [
        CurrencyBalanceResponse(code=b.code, name=b.name, amount=b.amount,
                                is_base=b.is_base)
        for b in balances
    ]


@router.get("/{book_id}/conversions", response_model=List[ConversionResponse])
async def list_conversions(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep,
    limit: int = Query(20, ge=1, le=100),
) -> List[ConversionResponse]:
    rows = await ExchangeService(session).conversions(user.id, book_id, limit)
    return [_conversion(row) for row in rows]


@router.post("/{book_id}/conversions", response_model=ConversionResponse,
             status_code=201)
async def convert(
    book_id: uuid.UUID, body: ConversionRequest, user: CurrentUser, session: SessionDep
) -> ConversionResponse:
    """Move value from one of the book's currencies into another."""
    row = await ExchangeService(session).convert(
        actor_user_id=user.id,
        book_id=book_id,
        from_currency=body.from_currency,
        from_amount=body.from_amount,
        to_currency=body.to_currency,
        to_amount=body.to_amount,
        base_value=body.base_value,
        occurred_on=body.occurred_on,
        note=body.note,
    )
    return _conversion(row)


def _conversion(row) -> ConversionResponse:
    return ConversionResponse(
        id=row.id, occurred_on=row.occurred_on,
        from_currency=row.from_currency, from_amount=row.from_amount,
        to_currency=row.to_currency, to_amount=row.to_amount,
        base_value=row.base_value, base_currency=row.base_currency,
        note=row.note,
    )


# --------------------------------------------------------------- members
@router.get("/{book_id}/members", response_model=List[MemberResponse])
async def list_members(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[MemberResponse]:
    from ...modules.books.models import Permission

    books = BookService(session)
    await books.require(book_id, user.id, Permission.VIEW_TRANSACTIONS)

    identity = IdentityService(session)
    result = []
    for member in await books.members(book_id):
        person = await identity.get_user(member.user_id)
        result.append(MemberResponse(user_id=member.user_id,
                                     display_name=person.display_name,
                                     role=member.role.value))
    return result


@router.post("/{book_id}/members", response_model=MemberResponse, status_code=201)
async def add_member(
    book_id: uuid.UUID, body: InviteRequest, user: CurrentUser, session: SessionDep
) -> MemberResponse:
    """Add someone who already has an account, by email or phone."""
    await BookService(session).require(book_id, user.id, Permission.MANAGE_MEMBERS)
    invitee = await IdentityService(session).find_by_identifier(body.identifier)
    if invitee is None:
        raise NotFound("no account with those details")

    membership = await BookService(session).add_member(
        user.id, book_id, invitee.id, _as_enum(Role, body.role, "role")
    )
    return MemberResponse(user_id=invitee.id, display_name=invitee.display_name,
                          role=membership.role.value)


@router.delete("/{book_id}/members/{member_user_id}", status_code=204)
async def remove_member(
    book_id: uuid.UUID, member_user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await BookService(session).deactivate_member(user.id, book_id, member_user_id)


@router.get("/{book_id}/categories", response_model=List[CategoryResponse])
async def list_categories(book_id: uuid.UUID, user: CurrentUser, session: SessionDep, flow: Optional[str] = None):
    return await CategoryService(session).list(book_id, user.id, flow)


@router.post("/{book_id}/categories", response_model=CategoryResponse, status_code=201)
async def create_category(book_id: uuid.UUID, body: CategoryRequest, user: CurrentUser, session: SessionDep):
    return await CategoryService(session).create(book_id, user.id, body.name, body.flow)


@router.patch("/{book_id}/categories/{category_id}", response_model=CategoryResponse)
async def rename_category(book_id: uuid.UUID, category_id: uuid.UUID, body: CategoryUpdate,
                          user: CurrentUser, session: SessionDep):
    return await CategoryService(session).update(book_id, user.id, category_id, **body.model_dump(exclude_unset=True))


@router.delete("/{book_id}/categories/{category_id}", status_code=204)
async def delete_category(book_id: uuid.UUID, category_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    await CategoryService(session).delete(book_id, user.id, category_id)


@router.post("/{book_id}/invitations", response_model=InvitationResponse, status_code=201)
async def invite_teammate(book_id: uuid.UUID, body: TeamInviteRequest, user: CurrentUser, session: SessionDep):
    provider = _as_enum(Provider, body.provider, "provider")
    if provider not in MESSENGERS:
        raise ValidationError("پیام‌رسان معتبر انتخاب کن.")
    return await InvitationService(session).create(book_id, user.id, provider, body.identifier,
                                                   _as_enum(Role, body.role, "role"))


# ---------------------------------------------------------- transactions
@router.get("/{book_id}/transactions", response_model=TransactionPage)
async def list_transactions(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    since: Optional[str] = None,
    until: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    flow: Optional[List[str]] = Query(default=None, description="income and/or expense; repeat for both"),
    category: Optional[List[str]] = Query(default=None, description="repeat for several categories"),
    currency: Optional[List[str]] = Query(default=None, description="the money it was paid in; repeat for several"),
    q: Optional[str] = Query(default=None, max_length=100, description="words in the category or the note"),
    sort: str = Query(default="newest", description="newest, oldest, amount_desc, amount_asc or category"),
) -> TransactionPage:
    from datetime import date as date_type

    def parse(value: Optional[str], field: str) -> Optional[date_type]:
        if not value:
            return None
        try:
            return date_type.fromisoformat(value)
        except ValueError:
            raise ValidationError(f"{field} must be a date like 2026-08-25") from None

    rows = await LedgerService(session).transactions(
        book_id, user.id, parse(since, "since"), parse(until, "until"),
        flows=[_as_enum(Flow, value, "flow") for value in flow] if flow else None,
        categories=category or None, text=q,
        currencies=[c.upper() for c in currency] if currency else None, sort=sort,
    )
    totals = LedgerService.split_totals(rows)
    rows = list(rows)
    start = (page - 1) * per_page
    visible = rows[start:start + per_page]
    activities = await LedgerService(session).activities(user.id, visible)
    counts = await AttachmentService(session).counts(book_id, user.id, [row.id for row in visible])

    return TransactionPage(
        items=[_transaction(row, activities[row.id], counts.get(row.id, 0)) for row in visible],
        total=len(rows), page=page, per_page=per_page,
        total_income=totals[0], total_expense=totals[1],
    )


@router.post("/{book_id}/transactions", response_model=TransactionResponse, status_code=201)
async def record_transaction(
    book_id: uuid.UUID, body: TransactionRequest, user: CurrentUser, session: SessionDep
) -> TransactionResponse:
    books = BookService(session)
    flow = _as_enum(Flow, body.flow, "flow")
    await books.require(book_id, user.id, Permission.VIEW_TRANSACTIONS)
    book = await books.get_book(book_id)

    scope = (
        _as_enum(Scope, body.scope, "scope") if body.scope
        else SCOPE_FOR_BOOK.get(book.type, Scope.WORK)
    )
    transaction = await LedgerService(session).record(
        book_id=book_id,
        actor_user_id=user.id,
        flow=flow,
        scope=scope,
        category=body.category,
        amount=body.amount,
        occurred_on=body.occurred_on,
        description=body.description,
        currency=body.currency,
        conversion_rate=body.conversion_rate,
    )
    activity = (await LedgerService(session).activities(user.id, [transaction]))[transaction.id]
    return _transaction(transaction, activity)


@router.get("/{book_id}/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    book_id: uuid.UUID, transaction_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> TransactionResponse:
    row = await LedgerService(session).get_transaction(book_id, user.id, transaction_id)
    if row is None:
        raise NotFound("transaction")
    activity = (await LedgerService(session).activities(user.id, [row]))[row.id]
    count = (await AttachmentService(session).counts(book_id, user.id, [row.id])).get(row.id, 0)
    return _transaction(row, activity, count)


@router.delete("/{book_id}/transactions/{transaction_id}", status_code=204)
async def delete_transaction(
    book_id: uuid.UUID, transaction_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await LedgerService(session).delete(book_id, user.id, transaction_id)


@router.patch("/{book_id}/transactions/{transaction_id}", response_model=TransactionResponse)
async def edit_transaction(book_id: uuid.UUID, transaction_id: uuid.UUID, body: TransactionUpdate,
                            user: CurrentUser, session: SessionDep):
    changes = body.model_dump(exclude_unset=True)
    if "flow" in changes and changes["flow"] is not None:
        changes["flow"] = _as_enum(Flow, changes["flow"], "flow")
    ledger = LedgerService(session)
    target = changes.pop("book_id", None)
    if target is not None and target != book_id:
        # The rest of the edit is judged in the book it lands in, so the move goes first.
        await ledger.move(book_id, user.id, transaction_id, target)
        book_id = target
        if not changes:
            row = await ledger.get_transaction(book_id, user.id, transaction_id)
            activity = (await ledger.activities(user.id, [row]))[row.id]
            count = (await AttachmentService(session).counts(book_id, user.id, [row.id])).get(row.id, 0)
            return _transaction(row, activity, count)
    row = await ledger.update(book_id, user.id, transaction_id, **changes)
    activity = (await LedgerService(session).activities(user.id, [row]))[row.id]
    count = (await AttachmentService(session).counts(book_id, user.id, [row.id])).get(row.id, 0)
    return _transaction(row, activity, count)


def _transaction(row, activity, attachment_count: int = 0) -> TransactionResponse:
    return TransactionResponse(
        id=row.id,
        flow=row.flow.value,
        scope=row.scope.value,
        category=row.category,
        original_amount=row.original_amount,
        original_currency=row.original_currency,
        conversion_rate=row.conversion_rate,
        converted_amount=row.converted_amount,
        description=row.description,
        occurred_on=row.occurred_on,
        created_at=row.created_at,
        activity=activity,
        has_receipt=row.receipt_file_id is not None,
        receipt_kind=row.receipt_kind,
        receipt_file_name=row.receipt_file_name,
        attachment_count=attachment_count,
    )


# ---------------------------------------------------------- attachments
@router.get("/{book_id}/transactions/{transaction_id}/attachments",
            response_model=List[AttachmentResponse])
async def list_attachments(
    book_id: uuid.UUID, transaction_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[AttachmentResponse]:
    rows = await AttachmentService(session).list(book_id, user.id, transaction_id)
    return [AttachmentResponse(id=r.id, file_name=r.file_name, content_type=r.content_type,
                               size=r.size, created_at=r.created_at) for r in rows]


@router.post("/{book_id}/transactions/{transaction_id}/attachments",
             response_model=AttachmentResponse, status_code=201)
async def add_attachment(
    book_id: uuid.UUID, transaction_id: uuid.UUID, user: CurrentUser, session: SessionDep,
    file: UploadFile = File(...),
) -> AttachmentResponse:
    """Attach a photo or a PDF (up to 1.5 MB). The type is read from the bytes, not the name."""
    # One byte past the limit is enough to know it is too big without reading the rest.
    data = await file.read(MAX_BYTES + 1)
    row = await AttachmentService(session).add(book_id, user.id, transaction_id, file.filename, data)
    return AttachmentResponse(id=row.id, file_name=row.file_name, content_type=row.content_type,
                              size=row.size, created_at=row.created_at)


@router.get("/{book_id}/transactions/{transaction_id}/attachments/{attachment_id}")
async def download_attachment(
    book_id: uuid.UUID, transaction_id: uuid.UUID, attachment_id: uuid.UUID,
    user: CurrentUser, session: SessionDep,
) -> Response:
    row = await AttachmentService(session).read(book_id, user.id, transaction_id, attachment_id)
    return Response(
        content=row.data,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(row.file_name)}",
            # Served from our own origin, so it must not be able to do anything but be looked at.
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{book_id}/transactions/{transaction_id}/attachments/{attachment_id}",
               status_code=204)
async def delete_attachment(
    book_id: uuid.UUID, transaction_id: uuid.UUID, attachment_id: uuid.UUID,
    user: CurrentUser, session: SessionDep,
) -> None:
    await AttachmentService(session).remove(book_id, user.id, transaction_id, attachment_id)


# ----------------------------------------------- receipts held by the messenger
RECEIPT_MAX_BYTES = 8_000_000
RECEIPT_GONE = "این رسید از پیام‌رسان گرفته نشد؛ شاید حذف شده یا در پنل وب قابل نمایش نیست."


@router.get("/{book_id}/transactions/{transaction_id}/receipt")
async def download_receipt(
    book_id: uuid.UUID, transaction_id: uuid.UUID, request: Request, user: CurrentUser,
    session: SessionDep, settings: SettingsDep,
) -> Response:
    """The receipt the bot stored, fetched from the messenger that holds it.

    The receipt is the messenger's own file id, never our bytes, so this asks the provider for the
    file on the person's behalf, after the usual book gate, and hands it over without keeping it.
    Only a receipt held by the provider this process speaks to can be fetched; any other, and any
    failure to fetch, is one answer: it is not available.
    """
    row = await LedgerService(session).get_transaction(book_id, user.id, transaction_id)
    if not row.receipt_file_id or row.receipt_provider != settings.provider.value:
        raise NotFound(RECEIPT_GONE)

    from dataclasses import replace

    adapter = getattr(request.app.state, "adapters", {}).get(settings.provider.value)
    temporary = adapter is None
    if temporary:
        from apps.bot.runner import build_adapter

        if not settings.token:
            raise NotFound(RECEIPT_GONE)
        adapter = build_adapter(replace(settings))
    try:
        data = await adapter.download_file(row.receipt_file_id, RECEIPT_MAX_BYTES)
    finally:
        if temporary:
            await adapter.aclose()
    if data is None:
        raise NotFound(RECEIPT_GONE)
    # What it is comes from its bytes, as for an upload. Anything that is not a photo or a PDF is
    # handed over as a download and never rendered.
    content_type = sniff(data)
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                "inline" if content_type else "attachment"
            ) + f"; filename*=UTF-8''{quote(row.receipt_file_name or 'receipt')}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'",
            "Cache-Control": "private, no-store",
        },
    )
