"""Moving money from one of the owner's books to another.

A person who keeps a business book and a personal one moves money between them: a draw, a
contribution, or the same shared account changing hands on paper. That is two journal entries, one in
each book, because a book never writes against another book's ledger. Each is the bank account against
«انتقال بین دفترها» (an equity account), so each book's trial balance closes by itself. It is not income
or an expense in either book, so no report, budget or share moves.

The same bank account may stand on both sides: the account's total is then unchanged and only how much of
it belongs to which book moves, which is exactly what a shared account's split is for.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import JournalEntry
from ..ledger.service import LedgerService
from .models import BankBookTransferLeg
from .service import BankService

EQUITY = "3100"
NOT_FOUND = "این انتقال پیدا نشد."


@dataclass
class LegRow:
    leg: BankBookTransferLeg
    bank_title: str
    # The other book's name, only for someone who is a member of it: a stranger learns nothing of it.
    other_book_name: Optional[str]


class BookTransferService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)
        self.banks = BankService(session)
        self.ledger = LedgerService(session)

    async def create(
        self, actor_id: uuid.UUID, *, from_book_id: uuid.UUID, to_book_id: uuid.UUID,
        from_bank_account_id: uuid.UUID, to_bank_account_id: uuid.UUID, amount,
        occurred_on: Optional[date] = None, note: Optional[str] = None,
    ) -> uuid.UUID:
        """Move money out of one book's account into another's; returns the pair's id."""
        if from_book_id == to_book_id:
            raise ValidationError("برای جابه‌جایی بین حساب‌های یک دفتر از «انتقال بین حساب‌ها» استفاده کن.")
        # Both books answer to the same person: managing accounts in each is what allows touching either.
        await self.books.require(from_book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        await self.books.require(to_book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        for locked in sorted((from_book_id, to_book_id), key=str):
            await self.banks._lock_book(locked)
        source = await self.books.get_book(from_book_id)
        target = await self.books.get_book(to_book_id)
        if source.base_currency != target.base_currency:
            raise ValidationError("واحد اصلی این دو دفتر یکی نیست؛ انتقال بین‌شان ممکن نیست.")
        on = occurred_on or jalali.today_in(source.timezone)
        await self.ledger._require_open_date(from_book_id, on)
        await self.ledger._require_open_date(to_book_id, on)
        value = quantize(amount)
        if value <= ZERO:
            raise ValidationError("مبلغ انتقال باید بیشتر از صفر باشد.")
        out_link = await self.banks.resolve(from_book_id, from_bank_account_id, in_base_currency=True)
        in_link = await self.banks.resolve(to_book_id, to_bank_account_id, in_base_currency=True)
        assert out_link is not None and in_link is not None
        text = LedgerService._description(note)
        pair = uuid.uuid4()
        for book_id, other_id, link, direction in (
            (from_book_id, to_book_id, out_link, "out"),
            (to_book_id, from_book_id, in_link, "in"),
        ):
            await self.ledger.ensure_chart_of_accounts(book_id)
            equity = await self.ledger.account(book_id, EQUITY)
            bank = await self.ledger._money_account(book_id, link)
            lines = ([(equity.id, value, ZERO), (bank.id, ZERO, value)] if direction == "out"
                     else [(bank.id, value, ZERO), (equity.id, ZERO, value)])
            entry = await self.ledger.post_entry(book_id, on, lines, memo="book transfer")
            self.session.add(BankBookTransferLeg(
                book_id=book_id, bank_account_id=link.bank_account_id, pair_id=pair,
                other_book_id=other_id, direction=direction, actor_user_id=actor_id,
                occurred_on=on, amount=value, note=text, entry_id=entry.id,
            ))
            await self.session.flush()
        return pair

    async def list(self, book_id: uuid.UUID, user_id: uuid.UUID) -> List[LegRow]:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        legs = (await self.session.scalars(
            select(BankBookTransferLeg).where(BankBookTransferLeg.book_id == book_id)
            .order_by(BankBookTransferLeg.occurred_on.desc(), BankBookTransferLeg.created_at.desc())
        )).all()
        titles = await self.banks.titles([leg.bank_account_id for leg in legs])
        names: dict = {}
        for other_id in {leg.other_book_id for leg in legs}:
            member = await self.books.membership(other_id, user_id)
            if member is not None and member.is_active:
                names[other_id] = (await self.books.get_book(other_id)).name
        return [LegRow(leg, titles.get(leg.bank_account_id, ""), names.get(leg.other_book_id))
                for leg in legs]

    async def delete(self, book_id: uuid.UUID, actor_id: uuid.UUID, pair_id: uuid.UUID) -> None:
        """Take back a transfer from both books at once; half of one would leave a book out of balance
        with the other."""
        await self.books.require(book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        legs = (await self.session.scalars(
            select(BankBookTransferLeg).where(BankBookTransferLeg.pair_id == pair_id)
        )).all()
        if not any(leg.book_id == book_id for leg in legs):
            raise NotFound(NOT_FOUND)
        for locked in sorted({leg.book_id for leg in legs}, key=str):
            await self.banks._lock_book(locked)
        for leg in legs:
            # The other side may be a book this person no longer manages: then neither can be removed
            # from here, rather than one side vanishing from under the other.
            await self.books.require(leg.book_id, actor_id, Permission.MANAGE_ACCOUNTS)
            await self.ledger._require_open_date(leg.book_id, leg.occurred_on)
        for leg in legs:
            entry = await self.session.get(JournalEntry, leg.entry_id)
            # The leg goes with its entry (ON DELETE CASCADE); removing the entry whole keeps its book balanced.
            if entry is not None:
                await self.session.delete(entry)
            else:
                await self.session.delete(leg)
        await self.session.flush()


__all__ = ["BookTransferService", "LegRow"]
