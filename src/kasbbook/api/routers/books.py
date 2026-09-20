"""Books, their members, and the transactions inside them.

Every route calls the same application services the bot calls. Permission
checks live in those services, not here — so a route cannot accidentally be
more permissive than the equivalent button.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Query

from ...modules.books.models import BookType, CostPolicy, Permission, Role
from ...modules.books.service import BookService
from ...modules.books.invitations import InvitationService
from ...modules.identity.models import MESSENGERS, Provider
from ...modules.identity.service import IdentityService
from ...modules.ledger.models import Flow, Scope
from ...modules.ledger.service import LedgerService
from ...modules.ledger.categories import CategoryService
from ...shared.errors import NotFound, ValidationError
from ..deps import CurrentUser, SessionDep
from ..schemas import (
    BookRequest,
    CostPolicyRequest,
    BookResponse,
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


@router.get("", response_model=List[BookResponse])
async def list_books(user: CurrentUser, session: SessionDep) -> List[BookResponse]:
    books = await BookService(session).books_for_user(user.id)
    return [
        BookResponse(id=b.id, name=b.name, type=b.type.value,
                     currency=b.base_currency, cost_policy=b.cost_policy.value,
                     created_at=b.created_at)
        for b in books
    ]


@router.post("", response_model=BookResponse, status_code=201)
async def create_book(
    body: BookRequest, user: CurrentUser, session: SessionDep
) -> BookResponse:
    book = await BookService(session).create_book(
        user.id, body.name, _as_enum(BookType, body.type, "type"), body.currency,
        _as_enum(CostPolicy, body.cost_policy, "cost_policy")
        if body.cost_policy else CostPolicy.BEFORE_SPLIT,
    )
    return BookResponse(id=book.id, name=book.name, type=book.type.value,
                        currency=book.base_currency,
                        cost_policy=book.cost_policy.value,
                        created_at=book.created_at)


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> BookResponse:
    from ...modules.books.models import Permission

    books = BookService(session)
    await books.require(book_id, user.id, Permission.VIEW_TRANSACTIONS)
    book = await books.get_book(book_id)
    return BookResponse(id=book.id, name=book.name, type=book.type.value,
                        currency=book.base_currency,
                        cost_policy=book.cost_policy.value,
                        created_at=book.created_at)


@router.put("/{book_id}/cost-policy", response_model=BookResponse)
async def set_cost_policy(
    book_id: uuid.UUID, body: CostPolicyRequest, user: CurrentUser, session: SessionDep
) -> BookResponse:
    """Choose whether costs come off before the split or out of the treasury."""
    book = await BookService(session).set_cost_policy(
        user.id, book_id, _as_enum(CostPolicy, body.cost_policy, "cost_policy")
    )
    return BookResponse(id=book.id, name=book.name, type=book.type.value,
                        currency=book.base_currency,
                        cost_policy=book.cost_policy.value,
                        created_at=book.created_at)


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
        book_id, user.id, parse(since, "since"), parse(until, "until")
    )
    # Newest first, which is what a list is read for.
    rows = list(reversed(rows))
    start = (page - 1) * per_page
    visible = rows[start:start + per_page]
    activities = await LedgerService(session).activities(user.id, visible)

    return TransactionPage(
        items=[_transaction(row, activities[row.id]) for row in visible],
        total=len(rows), page=page, per_page=per_page,
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
    return _transaction(row, activity)


@router.delete("/{book_id}/transactions/{transaction_id}", status_code=204)
async def delete_transaction(
    book_id: uuid.UUID, transaction_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await LedgerService(session).delete(book_id, user.id, transaction_id)


@router.patch("/{book_id}/transactions/{transaction_id}", response_model=TransactionResponse)
async def edit_transaction(book_id: uuid.UUID, transaction_id: uuid.UUID, body: TransactionUpdate,
                            user: CurrentUser, session: SessionDep):
    changes = body.model_dump(exclude_unset=True)
    row = await LedgerService(session).update(book_id, user.id, transaction_id, **changes)
    activity = (await LedgerService(session).activities(user.id, [row]))[row.id]
    return _transaction(row, activity)


def _transaction(row, activity) -> TransactionResponse:
    return TransactionResponse(
        id=row.id,
        flow=row.flow.value,
        scope=row.scope.value,
        category=row.category,
        original_amount=row.original_amount,
        original_currency=row.original_currency,
        converted_amount=row.converted_amount,
        description=row.description,
        occurred_on=row.occurred_on,
        created_at=row.created_at,
        activity=activity,
        has_receipt=row.receipt_file_id is not None,
        receipt_kind=row.receipt_kind,
        receipt_file_name=row.receipt_file_name,
    )
