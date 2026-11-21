"""Moving money between two of a book's own bank accounts.

A transfer is one balanced journal entry (debit where the money arrives, credit where it left) and the
row that remembers it. It is not income and not an expense, so it never touches a report, a budget or
anyone's share. Both accounts must be linked to the same book: a transfer between two books would need
an account in each to stand against, and that is an owner's draw or contribution, not this.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import JournalEntry
from ..ledger.service import LedgerService
from .models import BankTransfer
from .service import UNSET, BankService

NOT_FOUND = "این انتقال پیدا نشد."


@dataclass
class TransferRow:
    transfer: BankTransfer
    from_title: str
    to_title: str


class TransferService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)
        self.banks = BankService(session)
        self.ledger = LedgerService(session)

    async def _accounts(self, book_id: uuid.UUID, from_id: uuid.UUID, to_id: uuid.UUID):
        if from_id == to_id:
            raise ValidationError("مبدأ و مقصد باید دو حساب متفاوت باشند.")
        # Each must be one of this book's own, and on: the same answers recording a transaction gives.
        source = await self.banks.resolve(book_id, from_id, in_base_currency=True)
        target = await self.banks.resolve(book_id, to_id, in_base_currency=True)
        assert source is not None and target is not None
        return source, target

    async def _post(self, transfer: BankTransfer, source, target) -> JournalEntry:
        return await self.ledger.post_entry(
            transfer.book_id, transfer.occurred_on,
            [(target.ledger_account_id, transfer.amount, ZERO), (source.ledger_account_id, ZERO, transfer.amount)],
            memo="transfer",
        )

    async def create(
        self, book_id: uuid.UUID, actor_id: uuid.UUID, *, from_bank_account_id: uuid.UUID,
        to_bank_account_id: uuid.UUID, amount, occurred_on: Optional[date] = None,
        note: Optional[str] = None,
    ) -> BankTransfer:
        await self.books.require(book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        await self.banks._lock_book(book_id)
        book = await self.books.get_book(book_id)
        on = occurred_on or jalali.today_in(book.timezone)
        await self.ledger._require_open_date(book_id, on)
        value = quantize(amount)
        if value <= ZERO:
            raise ValidationError("مبلغ انتقال باید بیشتر از صفر باشد.")
        source, target = await self._accounts(book_id, from_bank_account_id, to_bank_account_id)
        transfer = BankTransfer(
            book_id=book_id, from_bank_account_id=from_bank_account_id,
            to_bank_account_id=to_bank_account_id, actor_user_id=actor_id, occurred_on=on,
            amount=value, note=LedgerService._description(note), entry_id=uuid.uuid4(),
        )
        entry = await self._post(transfer, source, target)
        transfer.entry_id = entry.id
        self.session.add(transfer)
        await self.session.flush()
        return transfer

    async def _get(self, book_id: uuid.UUID, transfer_id: uuid.UUID) -> BankTransfer:
        row = await self.session.scalar(select(BankTransfer).where(
            BankTransfer.id == transfer_id, BankTransfer.book_id == book_id
        ).with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise NotFound(NOT_FOUND)
        return row

    async def update(
        self, book_id: uuid.UUID, actor_id: uuid.UUID, transfer_id: uuid.UUID, *,
        from_bank_account_id=UNSET, to_bank_account_id=UNSET, amount=UNSET, occurred_on=UNSET,
        note=UNSET,
    ) -> BankTransfer:
        await self.books.require(book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        await self.banks._lock_book(book_id)
        transfer = await self._get(book_id, transfer_id)
        if any(value is None for value in (from_bank_account_id, to_bank_account_id, amount, occurred_on)):
            raise ValidationError("مبدأ، مقصد، مبلغ و تاریخ نمی‌تواند خالی باشد.")
        # Judged on both dates, like a transaction: it has to be free to leave where it was and
        # welcome where it lands.
        await self.ledger._require_open_date(book_id, transfer.occurred_on)
        new_day = transfer.occurred_on if occurred_on is UNSET else occurred_on
        await self.ledger._require_open_date(book_id, new_day)
        new_from = transfer.from_bank_account_id if from_bank_account_id is UNSET else from_bank_account_id
        new_to = transfer.to_bank_account_id if to_bank_account_id is UNSET else to_bank_account_id
        value = transfer.amount if amount is UNSET else quantize(amount)
        if value <= ZERO:
            raise ValidationError("مبلغ انتقال باید بیشتر از صفر باشد.")
        source, target = await self._accounts(book_id, new_from, new_to)
        old_id = transfer.entry_id
        transfer.from_bank_account_id, transfer.to_bank_account_id = new_from, new_to
        transfer.amount, transfer.occurred_on = value, new_day
        if note is not UNSET:
            transfer.note = LedgerService._description(note)
        # The new entry is written and the row pointed at it before the old one goes: the row is removed
        # with its entry (ON DELETE CASCADE), so deleting the old one first would take the transfer too.
        entry = await self._post(transfer, source, target)
        transfer.entry_id = entry.id
        await self.session.flush()
        old = await self.session.get(JournalEntry, old_id)
        if old is not None:
            await self.session.delete(old)
            await self.session.flush()
        return transfer

    async def delete(self, book_id: uuid.UUID, actor_id: uuid.UUID, transfer_id: uuid.UUID) -> None:
        await self.books.require(book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        await self.banks._lock_book(book_id)
        transfer = await self._get(book_id, transfer_id)
        await self.ledger._require_open_date(book_id, transfer.occurred_on)
        entry = await self.session.get(JournalEntry, transfer.entry_id)
        # The row goes with its entry (ON DELETE CASCADE); deleting the entry whole keeps the book balanced.
        if entry is not None:
            await self.session.delete(entry)
        else:
            await self.session.delete(transfer)
        await self.session.flush()

    async def list(
        self, book_id: uuid.UUID, user_id: uuid.UUID, *, since: Optional[date] = None,
        until: Optional[date] = None, bank_account_id: Optional[uuid.UUID] = None,
    ) -> List[TransferRow]:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        stmt = select(BankTransfer).where(BankTransfer.book_id == book_id)
        if since is not None:
            stmt = stmt.where(BankTransfer.occurred_on >= since)
        if until is not None:
            stmt = stmt.where(BankTransfer.occurred_on <= until)
        if bank_account_id is not None:
            stmt = stmt.where(or_(
                BankTransfer.from_bank_account_id == bank_account_id,
                BankTransfer.to_bank_account_id == bank_account_id,
            ))
        rows = (await self.session.scalars(
            stmt.order_by(BankTransfer.occurred_on.desc(), BankTransfer.created_at.desc())
        )).all()
        titles = await self.banks.titles(
            [r.from_bank_account_id for r in rows] + [r.to_bank_account_id for r in rows]
        )
        return [TransferRow(r, titles.get(r.from_bank_account_id, ""), titles.get(r.to_bank_account_id, ""))
                for r in rows]


__all__ = ["TransferService", "TransferRow"]
