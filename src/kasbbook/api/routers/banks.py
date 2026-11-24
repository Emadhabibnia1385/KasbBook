"""Bank accounts: the ones a person owns, and the ones a book uses.

The routes are in two groups on purpose. `/bank-accounts` is the owner's: the account itself, its
numbers, and the one real balance across every book. `/books/{id}/bank-accounts` is a book's: which
accounts it uses, what its own share of each is, and which is the default. A member of a book sees
only the second, so nothing here lets one book learn what another did with the same account.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter

from ...modules.banks.models import BankAccount
from ...modules.banks.booktransfers import BookTransferService, LegRow
from ...modules.banks.transfers import TransferRow, TransferService
from ...modules.ledger.service import LedgerService
from ...modules.banks.service import (
    UNSET,
    BankService,
    BankSummary,
    BookBank,
    mask_card,
)
from ..deps import CurrentUser, SessionDep
from ..schemas import (
    BookTransferRequest,
    BookTransferResponse,
    BankAssignRequest,
    BankAssignResponse,
    BankTransferRequest,
    BankTransferResponse,
    BankTransferUpdate,
    BankAccountRequest,
    BankAccountResponse,
    BankAccountUpdate,
    BankLinkRequest,
    BankLinkUpdate,
    BankReconciliationResponse,
    BankShareCheckResponse,
    BankShareResponse,
    BookBankResponse,
)

router = APIRouter(prefix="/bank-accounts", tags=["banks"])
book_router = APIRouter(prefix="/books", tags=["banks"])
between_books = APIRouter(prefix="/book-transfers", tags=["banks"])


def _owner_view(summary: BankSummary) -> BankAccountResponse:
    bank = summary.bank
    return BankAccountResponse(
        id=bank.id, title=bank.title, bank_name=bank.bank_name, holder_name=bank.holder_name,
        display_name=bank.display_name, card_number=bank.card_number,
        account_number=bank.account_number, sheba=bank.sheba, currency=bank.currency, kind=bank.kind,
        opening_balance=bank.opening_balance, is_active=bank.is_active,
        total_balance=summary.total, created_at=bank.created_at,
        shares=[
            BankShareResponse(
                book_id=s.book_id, book_name=s.book_name, balance=s.balance,
                is_active=s.link.is_active, is_default=s.link.is_default,
            ) for s in summary.shares
        ],
    )


def _book_view(row: BookBank, user_id: uuid.UUID) -> BookBankResponse:
    bank: BankAccount = row.bank
    return BookBankResponse(
        id=bank.id, title=bank.title, bank_name=bank.bank_name, holder_name=bank.holder_name,
        display_name=bank.display_name, card_last4=mask_card(bank.card_number),
        card_number=bank.card_number if row.details else None,
        account_number=bank.account_number if row.details else None,
        sheba=bank.sheba if row.details else None,
        currency=bank.currency, is_active=row.link.is_active and bank.is_active,
        is_default=row.link.is_default, is_owner=bank.owner_user_id == user_id, balance=row.balance,
    )


# ------------------------------------------------------------ the owner's accounts
@router.get("", response_model=List[BankAccountResponse])
async def list_mine(user: CurrentUser, session: SessionDep) -> List[BankAccountResponse]:
    """Every account you own, with its balance and how much of it belongs to each book."""
    return [_owner_view(summary) for summary in await BankService(session).mine(user.id)]


@router.post("", response_model=BankAccountResponse, status_code=201)
async def create(
    body: BankAccountRequest, user: CurrentUser, session: SessionDep
) -> BankAccountResponse:
    """Add an account. Only the bank and the holder are required; `book_ids` links it right away.

    `kind: "cash"` adds the cash wallet instead: no bank or numbers, one per unit; asking again while an
    inactive one exists turns it back on."""
    service = BankService(session)
    bank = await service.create(
        user.id, bank_name=body.bank_name, holder_name=body.holder_name,
        display_name=body.display_name, card_number=body.card_number,
        account_number=body.account_number, sheba=body.sheba,
        opening_balance=body.opening_balance, currency=body.currency, book_ids=body.book_ids,
        kind=body.kind,
    )
    return _owner_view(await service.get_mine(user.id, bank.id))


@router.get("/{bank_id}", response_model=BankAccountResponse)
async def get(bank_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> BankAccountResponse:
    return _owner_view(await BankService(session).get_mine(user.id, bank_id))


@router.patch("/{bank_id}", response_model=BankAccountResponse)
async def update(
    bank_id: uuid.UUID, body: BankAccountUpdate, user: CurrentUser, session: SessionDep
) -> BankAccountResponse:
    """Change what was sent. A field left out stays; a null clears the optional ones."""
    changes = body.model_dump(exclude_unset=True)
    service = BankService(session)
    await service.update(user.id, bank_id, **changes)
    return _owner_view(await service.get_mine(user.id, bank_id))


@router.delete("/{bank_id}", status_code=204)
async def delete(bank_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    """Only an account nothing was recorded against; any other is switched off instead."""
    await BankService(session).delete(user.id, bank_id)


@router.get("/{bank_id}/reconciliation", response_model=BankReconciliationResponse)
async def reconcile(
    bank_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> BankReconciliationResponse:
    """The balance worked out two independent ways, per book and in total. They must agree."""
    result = await BankService(session).reconcile(user.id, bank_id)
    return BankReconciliationResponse(
        bank_id=result.bank_id, opening=result.opening, from_journal=result.from_journal,
        from_transactions=result.from_transactions, consistent=result.consistent,
        shares=[
            BankShareCheckResponse(
                book_id=s.book_id, book_name=s.book_name, journal=s.journal,
                transactions=s.transactions,
            ) for s in result.shares
        ],
    )


# ------------------------------------------------------------ a book's accounts
@book_router.get("/{book_id}/bank-accounts", response_model=List[BookBankResponse])
async def list_for_book(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[BookBankResponse]:
    """The accounts this book uses, the default first. What the transaction form chooses from."""
    rows = await BankService(session).for_book(book_id, user.id)
    return [_book_view(row, user.id) for row in rows]


async def _one(session, book_id: uuid.UUID, bank_id: uuid.UUID, user_id: uuid.UUID) -> BookBankResponse:
    from ...shared.errors import NotFound

    for row in await BankService(session).for_book(book_id, user_id):
        if row.bank.id == bank_id:
            return _book_view(row, user_id)
    raise NotFound("این حساب بانکی پیدا نشد.")


@book_router.put("/{book_id}/bank-accounts/{bank_id}", response_model=BookBankResponse)
async def link(
    book_id: uuid.UUID, bank_id: uuid.UUID, body: BankLinkRequest, user: CurrentUser,
    session: SessionDep,
) -> BookBankResponse:
    """Use one of your accounts in this book. The book's first account becomes its default."""
    await BankService(session).link(user.id, book_id, bank_id, make_default=body.make_default)
    return await _one(session, book_id, bank_id, user.id)


@book_router.patch("/{book_id}/bank-accounts/{bank_id}", response_model=BookBankResponse)
async def update_link(
    book_id: uuid.UUID, bank_id: uuid.UUID, body: BankLinkUpdate, user: CurrentUser,
    session: SessionDep,
) -> BookBankResponse:
    """Switch the account on or off in this book, or make it this book's default."""
    changes = body.model_dump(exclude_unset=True)
    await BankService(session).set_link(
        user.id, book_id, bank_id,
        is_active=changes.get("is_active", UNSET), is_default=changes.get("is_default", UNSET),
    )
    return await _one(session, book_id, bank_id, user.id)


@book_router.delete("/{book_id}/bank-accounts/{bank_id}", status_code=204)
async def unlink(
    book_id: uuid.UUID, bank_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Stop using the account in this book; refused once a transaction here used it."""
    await BankService(session).unlink(user.id, book_id, bank_id)


@book_router.post("/{book_id}/bank-accounts/{bank_id}/assign", response_model=BankAssignResponse)
async def assign(
    book_id: uuid.UUID, bank_id: uuid.UUID, body: BankAssignRequest, user: CurrentUser,
    session: SessionDep,
) -> BankAssignResponse:
    """Put the transactions that name no account on this one, for a book that predates accounts."""
    moved, left = await LedgerService(session).assign_bank(
        book_id, user.id, bank_id, since=body.since, until=body.until
    )
    return BankAssignResponse(moved=moved, left=left)


# ------------------------------------------------------------ transfers
def _transfer(row: TransferRow) -> BankTransferResponse:
    t = row.transfer
    return BankTransferResponse(
        id=t.id, from_bank_account_id=t.from_bank_account_id, from_title=row.from_title,
        to_bank_account_id=t.to_bank_account_id, to_title=row.to_title, amount=t.amount,
        occurred_on=t.occurred_on, note=t.note, created_at=t.created_at,
    )


async def _one_transfer(session, book_id: uuid.UUID, user_id: uuid.UUID, transfer_id: uuid.UUID):
    from ...shared.errors import NotFound

    for row in await TransferService(session).list(book_id, user_id):
        if row.transfer.id == transfer_id:
            return _transfer(row)
    raise NotFound("این انتقال پیدا نشد.")


@book_router.get("/{book_id}/bank-transfers", response_model=List[BankTransferResponse])
async def list_transfers(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep,
    since: Optional[date] = None, until: Optional[date] = None,
    bank_account_id: Optional[uuid.UUID] = None,
) -> List[BankTransferResponse]:
    """Money moved between this book's accounts, newest first."""
    rows = await TransferService(session).list(
        book_id, user.id, since=since, until=until, bank_account_id=bank_account_id
    )
    return [_transfer(row) for row in rows]


@book_router.post("/{book_id}/bank-transfers", response_model=BankTransferResponse, status_code=201)
async def create_transfer(
    book_id: uuid.UUID, body: BankTransferRequest, user: CurrentUser, session: SessionDep
) -> BankTransferResponse:
    """Move money from one of the book's accounts to another. Not income and not an expense."""
    transfer = await TransferService(session).create(
        book_id, user.id, from_bank_account_id=body.from_bank_account_id,
        to_bank_account_id=body.to_bank_account_id, amount=body.amount,
        occurred_on=body.occurred_on, note=body.note,
    )
    return await _one_transfer(session, book_id, user.id, transfer.id)


@book_router.patch("/{book_id}/bank-transfers/{transfer_id}", response_model=BankTransferResponse)
async def update_transfer(
    book_id: uuid.UUID, transfer_id: uuid.UUID, body: BankTransferUpdate, user: CurrentUser,
    session: SessionDep,
) -> BankTransferResponse:
    await TransferService(session).update(
        book_id, user.id, transfer_id, **body.model_dump(exclude_unset=True)
    )
    return await _one_transfer(session, book_id, user.id, transfer_id)


@book_router.delete("/{book_id}/bank-transfers/{transfer_id}", status_code=204)
async def delete_transfer(
    book_id: uuid.UUID, transfer_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await TransferService(session).delete(book_id, user.id, transfer_id)


# ------------------------------------------------------ transfers between books
def _leg(row: LegRow) -> BookTransferResponse:
    leg = row.leg
    return BookTransferResponse(
        pair_id=leg.pair_id, direction=leg.direction, bank_account_id=leg.bank_account_id,
        bank_title=row.bank_title, other_book_id=leg.other_book_id,
        other_book_name=row.other_book_name, amount=leg.amount, occurred_on=leg.occurred_on,
        note=leg.note, created_at=leg.created_at,
    )


@between_books.post("", response_model=BookTransferResponse, status_code=201)
async def create_book_transfer(
    body: BookTransferRequest, user: CurrentUser, session: SessionDep
) -> BookTransferResponse:
    """Move money from one of your books to another. Needs account management in both.

    Written to each book as its own balanced entry, so neither book's accounts depend on the other.
    Not income and not an expense in either. The answer is the leaving book's side.
    """
    service = BookTransferService(session)
    pair = await service.create(
        user.id, from_book_id=body.from_book_id, to_book_id=body.to_book_id,
        from_bank_account_id=body.from_bank_account_id, to_bank_account_id=body.to_bank_account_id,
        amount=body.amount, occurred_on=body.occurred_on, note=body.note,
    )
    for row in await service.list(body.from_book_id, user.id):
        if row.leg.pair_id == pair:
            return _leg(row)
    raise AssertionError("the leg just written is missing")


@book_router.get("/{book_id}/book-transfers", response_model=List[BookTransferResponse])
async def list_book_transfers(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[BookTransferResponse]:
    """This book's side of every transfer to or from another book, newest first."""
    return [_leg(row) for row in await BookTransferService(session).list(book_id, user.id)]


@book_router.delete("/{book_id}/book-transfers/{pair_id}", status_code=204)
async def delete_book_transfer(
    book_id: uuid.UUID, pair_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Take a transfer back from both books at once."""
    await BookTransferService(session).delete(book_id, user.id, pair_id)
