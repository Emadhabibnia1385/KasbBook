"""Bank accounts and their links to books.

Who may do what, in one place:

  * The person who created an account owns it: only they edit its details, switch it off, or link it
    to one of their books. They are the only one who sees its balance across every book.
  * Whoever holds MANAGE_ACCOUNTS in a book decides how the account behaves *there*: switched on or
    off, the default, taken out again.
  * Anyone who can record in a book picks from its accounts by name; only the owner and the book's
    managers see the card, account and Sheba numbers.

The balance of an account is never stored: it is the opening balance plus what each book's ledger
account for it holds. See `models.py` for why that makes "the balances are always equal" a property of
the data and not a promise.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize
from ...shared.parsing import to_ascii_digits
from ..books.models import Book, Permission
from ..books.service import BookService
from ..capital.models import CapitalMovement
from ..debts.models import DebtMovement
from ..exchange.models import CurrencyConversion
from ..ledger.models import Account, AccountType, Flow, JournalLine, Transaction
from ..income.models import IncomeLink
from ..payroll.models import Payment
from ..recurring.models import RecurringRule
from .models import (
    CASH_TITLE, KIND_BANK, KIND_CASH, BankAccount, BankAccountLink, BankBookTransferLeg, BankTransfer,
)

# What a cash wallet stores where a bank account has a bank's name.
CASH_NAME = "نقد"

# "Not given" is not the same as "given as nothing": an edit that leaves a field out keeps it, and one
# that sends null clears it. The ledger shares this marker so the two services mean the same thing.
UNSET = object()

NOT_FOUND = "این حساب بانکی پیدا نشد."


# ------------------------------------------------------------------ the numbers on a card
def _digits(value: str) -> str:
    return to_ascii_digits(value).replace(" ", "").replace("-", "").replace("_", "")


def clean_card(value: Optional[str]) -> Optional[str]:
    """A 16-digit card number that passes the Luhn check, or nothing."""
    if value is None or not value.strip():
        return None
    number = _digits(value)
    if not (number.isdigit() and len(number) == 16):
        raise ValidationError("شمارهٔ کارت باید 16 رقم باشد.")
    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    if total % 10 != 0:
        raise ValidationError("شمارهٔ کارت درست نیست؛ ارقام را دوباره بررسی کن.")
    return number


def clean_sheba(value: Optional[str]) -> Optional[str]:
    """`IR` and 24 digits whose ISO 7064 check holds, with or without the `IR` typed."""
    if value is None or not value.strip():
        return None
    text = _digits(value).upper()
    if text.startswith("IR"):
        text = text[2:]
    if not (text.isdigit() and len(text) == 24):
        raise ValidationError("شمارهٔ شبا باید IR و 24 رقم باشد.")
    rearranged = text[2:] + "1827" + text[:2]  # I=18, R=27, moved to the end with the first digits
    if int(rearranged) % 97 != 1:
        raise ValidationError("شمارهٔ شبا درست نیست؛ ارقام را دوباره بررسی کن.")
    return "IR" + text


_ACCOUNT_NUMBER = re.compile(r"^[0-9][0-9./-]{0,31}$")


def clean_account_number(value: Optional[str]) -> Optional[str]:
    """Banks print these with dots or dashes, so those are allowed; letters are not."""
    if value is None or not value.strip():
        return None
    number = to_ascii_digits(value).replace(" ", "")
    if not _ACCOUNT_NUMBER.match(number):
        raise ValidationError("شمارهٔ حساب فقط می‌تواند رقم، نقطه و خط تیره داشته باشد.")
    return number


def _required(value: Optional[str], label: str, limit: int) -> str:
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"{label} را وارد کن.")
    if len(text) > limit:
        raise ValidationError(f"{label} حداکثر {limit} حرف است.")
    return text


def _optional(value: Optional[str], label: str, limit: int) -> Optional[str]:
    text = (value or "").strip()
    if len(text) > limit:
        raise ValidationError(f"{label} حداکثر {limit} حرف است.")
    return text or None


def mask_card(card: Optional[str]) -> Optional[str]:
    return f"•••• {card[-4:]}" if card else None


# ------------------------------------------------------------------ what the service returns
@dataclass
class BookBank:
    """An account as one book sees it: what a person recording a transaction chooses from."""

    bank: BankAccount
    link: BankAccountLink
    # Card, account and Sheba numbers are shown only to the owner and the book's managers.
    details: bool
    # This book's own share of the account; None for someone who may not view reports.
    balance: Optional[Decimal]


@dataclass
class LinkShare:
    book_id: uuid.UUID
    book_name: str
    link: BankAccountLink
    balance: Decimal


@dataclass
class BankSummary:
    """An account as its owner sees it: every book that uses it, and the one real balance."""

    bank: BankAccount
    shares: List[LinkShare] = field(default_factory=list)
    total: Decimal = ZERO


@dataclass
class ShareCheck:
    book_id: uuid.UUID
    book_name: str
    journal: Decimal
    transactions: Decimal


@dataclass
class Reconciliation:
    """Two independent ways of arriving at the same balance, side by side."""

    bank_id: uuid.UUID
    opening: Decimal
    shares: List[ShareCheck]
    from_journal: Decimal
    from_transactions: Decimal

    @property
    def consistent(self) -> bool:
        return self.from_journal == self.from_transactions and all(
            s.journal == s.transactions for s in self.shares
        )


class BankService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    # -------------------------------------------------------------- reading
    async def _owned(self, owner_id: uuid.UUID, bank_id: uuid.UUID) -> BankAccount:
        """The account, or NotFound: someone else's looks exactly like one that does not exist."""
        bank = await self.session.scalar(select(BankAccount).where(
            BankAccount.id == bank_id, BankAccount.owner_user_id == owner_id
        ).execution_options(populate_existing=True))
        if bank is None:
            raise NotFound(NOT_FOUND)
        return bank

    async def _shares_of(self, account_ids: Sequence[uuid.UUID]) -> Dict[uuid.UUID, Decimal]:
        """What each ledger account holds. Summed here, not in SQL: Money is text on SQLite."""
        totals: Dict[uuid.UUID, Decimal] = {account_id: ZERO for account_id in account_ids}
        if not account_ids:
            return totals
        rows = (await self.session.execute(
            select(JournalLine.account_id, JournalLine.debit, JournalLine.credit)
            .where(JournalLine.account_id.in_(list(account_ids)))
        )).all()
        for account_id, debit, credit in rows:
            totals[account_id] += debit - credit  # an asset grows with a debit
        return totals

    async def for_book(
        self, book_id: uuid.UUID, user_id: uuid.UUID, *, only_active: bool = False
    ) -> List[BookBank]:
        member = await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        rows = (await self.session.execute(
            select(BankAccountLink, BankAccount)
            .join(BankAccount, BankAccount.id == BankAccountLink.bank_account_id)
            .where(BankAccountLink.book_id == book_id)
            .order_by(BankAccountLink.is_default.desc(), BankAccount.bank_name, BankAccount.holder_name)
        )).all()
        manager = Permission.MANAGE_ACCOUNTS in member.permissions
        balances = (
            await self._shares_of([link.ledger_account_id for link, _ in rows])
            if Permission.VIEW_REPORTS in member.permissions else None
        )
        out: List[BookBank] = []
        for link, bank in rows:
            if only_active and not (link.is_active and bank.is_active):
                continue
            out.append(BookBank(
                bank=bank, link=link,
                details=manager or bank.owner_user_id == user_id,
                balance=balances[link.ledger_account_id] if balances is not None else None,
            ))
        return out

    async def mine(self, owner_id: uuid.UUID) -> List[BankSummary]:
        banks = (await self.session.scalars(
            select(BankAccount).where(BankAccount.owner_user_id == owner_id)
            .order_by(BankAccount.created_at)
        )).all()
        out: List[BankSummary] = []
        for bank in banks:
            out.append(await self._summary(bank))
        return out

    async def get_mine(self, owner_id: uuid.UUID, bank_id: uuid.UUID) -> BankSummary:
        return await self._summary(await self._owned(owner_id, bank_id))

    async def _summary(self, bank: BankAccount) -> BankSummary:
        rows = (await self.session.execute(
            select(BankAccountLink, Book.name)
            .join(Book, Book.id == BankAccountLink.book_id)
            .where(BankAccountLink.bank_account_id == bank.id)
            .order_by(Book.name)
        )).all()
        balances = await self._shares_of([link.ledger_account_id for link, _ in rows])
        shares = [
            LinkShare(link.book_id, name, link, balances[link.ledger_account_id]) for link, name in rows
        ]
        return BankSummary(
            bank=bank, shares=shares,
            total=quantize(bank.opening_balance) + sum((s.balance for s in shares), ZERO),
        )

    async def reconcile(self, owner_id: uuid.UUID, bank_id: uuid.UUID) -> Reconciliation:
        """The balance from the journal and the balance from the transactions and transfers, side by side.

        They are separate derivations on purpose. If a transaction's journal entry ever differed from
        the transaction, or something wrote to the account's ledger without one, they would disagree
        here, and so would the account's balance as every other screen shows it.
        """
        summary = await self.get_mine(owner_id, bank_id)
        rows = (await self.session.execute(
            select(Transaction.book_id, Transaction.flow, Transaction.converted_amount)
            .where(Transaction.bank_account_id == bank_id)
        )).all()
        spent: Dict[uuid.UUID, Decimal] = {}
        for book_id, flow, amount in rows:
            spent[book_id] = spent.get(book_id, ZERO) + (amount if flow is Flow.INCOME else -amount)
        # A transaction naming this account in a book that has no link to it is a broken row; counting
        # it here (and not in the journal) is exactly how the difference gets noticed.
        # What moved between this account and the book's others counts too: in is a gain, out a loss.
        for book_id, from_id, to_id, amount in (await self.session.execute(
            select(BankTransfer.book_id, BankTransfer.from_bank_account_id,
                   BankTransfer.to_bank_account_id, BankTransfer.amount)
            .where((BankTransfer.from_bank_account_id == bank_id) | (BankTransfer.to_bank_account_id == bank_id))
        )).all():
            spent[book_id] = spent.get(book_id, ZERO) + (amount if to_id == bank_id else -amount)
        # Cash that moved with an asset, a fund or a loan's principal: none of it is a transaction.
        for book_id, delta in (await self.session.execute(
            select(CapitalMovement.book_id, CapitalMovement.cash_delta)
            .where(CapitalMovement.bank_account_id == bank_id)
        )).all():
            spent[book_id] = spent.get(book_id, ZERO) + delta
        # Cash lent, borrowed, paid back or received back, through this account.
        for book_id, delta in (await self.session.execute(
            select(DebtMovement.book_id, DebtMovement.cash_delta).where(DebtMovement.bank_account_id == bank_id)
        )).all():
            spent[book_id] = spent.get(book_id, ZERO) + delta
        # Pay handed to members, and money exchanged into or out of another currency, through this account.
        for book_id, amount in (await self.session.execute(
            select(Payment.book_id, Payment.amount).where(Payment.bank_account_id == bank_id)
        )).all():
            spent[book_id] = spent.get(book_id, ZERO) - amount
        for book_id, from_currency, from_amount, to_amount, base in (await self.session.execute(
            select(CurrencyConversion.book_id, CurrencyConversion.from_currency,
                   CurrencyConversion.from_amount, CurrencyConversion.to_amount,
                   CurrencyConversion.base_currency)
            .where(CurrencyConversion.bank_account_id == bank_id)
        )).all():
            spent[book_id] = spent.get(book_id, ZERO) + (-from_amount if from_currency == base else to_amount)
        # Money moved to or from another book: in is a gain here, out a loss, and the account's total
        # follows only when the other end is a different account.
        for book_id, direction, amount in (await self.session.execute(
            select(BankBookTransferLeg.book_id, BankBookTransferLeg.direction, BankBookTransferLeg.amount)
            .where(BankBookTransferLeg.bank_account_id == bank_id)
        )).all():
            spent[book_id] = spent.get(book_id, ZERO) + (amount if direction == "in" else -amount)
        shares = [
            ShareCheck(s.book_id, s.book_name, s.balance, spent.pop(s.book_id, ZERO))
            for s in summary.shares
        ]
        stray = sum(spent.values(), ZERO)
        opening = quantize(summary.bank.opening_balance)
        return Reconciliation(
            bank_id=bank_id, opening=opening, shares=shares,
            from_journal=summary.total,
            from_transactions=opening + sum((s.transactions for s in shares), ZERO) + stray,
        )

    # -------------------------------------------------------------- writing
    async def create(
        self, owner_id: uuid.UUID, *, bank_name: str, holder_name: str,
        display_name: Optional[str] = None, card_number: Optional[str] = None,
        account_number: Optional[str] = None, sheba: Optional[str] = None,
        opening_balance=0, currency: Optional[str] = None,
        book_ids: Sequence[uuid.UUID] = (), kind: str = KIND_BANK,
    ) -> BankAccount:
        if kind not in (KIND_BANK, KIND_CASH):
            raise ValidationError("نوع حساب را «حساب بانکی» یا «کیف پول نقدی» بگذار.")
        books = [await self.books.get_book(book_id) for book_id in book_ids]
        # Checked before anything is written, so a refused link leaves no half-made account behind.
        for book_id in book_ids:
            await self.books.require(book_id, owner_id, Permission.MANAGE_ACCOUNTS)
        code = (currency or (books[0].base_currency if books else "IRT")).upper()
        opening = quantize(opening_balance)
        if kind == KIND_CASH:
            if any((bank_name, holder_name, card_number, account_number, sheba)):
                raise ValidationError("کیف پول نقدی بانک، صاحب حساب، شماره کارت و شبا ندارد.")
            existing = await self.session.scalar(select(BankAccount).where(
                BankAccount.owner_user_id == owner_id, BankAccount.currency == code,
                BankAccount.kind == KIND_CASH,
            ))
            if existing is not None:
                # One wallet per unit: asking for another turns the old one back on rather than adding it.
                if existing.is_active:
                    raise ValidationError(
                        f"کیف پول نقدی {code} از قبل داری و فعال است؛ حساب دوم لازم نیست."
                    )
                existing.is_active = True
                await self.session.flush()
                for book_id in book_ids:
                    await self.link(owner_id, book_id, existing.id)
                return existing
            bank = BankAccount(
                owner_user_id=owner_id, bank_name=CASH_NAME, holder_name=CASH_TITLE,
                display_name=_optional(display_name, "نام نمایشی", 80), currency=code,
                opening_balance=opening, kind=KIND_CASH,
            )
        else:
            bank = BankAccount(
                owner_user_id=owner_id,
                bank_name=_required(bank_name, "نام بانک", 80),
                holder_name=_required(holder_name, "نام و نام خانوادگی صاحب حساب", 120),
                display_name=_optional(display_name, "نام نمایشی", 80),
                card_number=clean_card(card_number),
                account_number=clean_account_number(account_number),
                sheba=clean_sheba(sheba),
                currency=code,
                opening_balance=opening,
            )
        self.session.add(bank)
        await self.session.flush()
        for book_id in book_ids:
            await self.link(owner_id, book_id, bank.id)
        return bank

    async def update(
        self, owner_id: uuid.UUID, bank_id: uuid.UUID, *, bank_name=UNSET, holder_name=UNSET,
        display_name=UNSET, card_number=UNSET, account_number=UNSET, sheba=UNSET,
        opening_balance=UNSET, is_active=UNSET, current_balance=UNSET,
    ) -> BankAccount:
        """Change what was given.

        `current_balance` is what the bank says the account holds right now: the opening balance is
        then worked out as whatever the books' own transactions do not explain, so the account's total
        equals the bank's and each book keeps exactly its own share. It replaces `opening_balance`.
        """
        bank = await self._owned(owner_id, bank_id)
        if bank.kind == KIND_CASH and any(
            value is not UNSET for value in (bank_name, holder_name, card_number, account_number, sheba)
        ):
            raise ValidationError("کیف پول نقدی بانک، صاحب حساب، شماره کارت و شبا ندارد.")
        if current_balance is not UNSET and opening_balance is not UNSET:
            raise ValidationError("یا موجودی اولیه را بنویس یا موجودی فعلی حساب را، نه هر دو.")
        if bank_name is not UNSET:
            bank.bank_name = _required(bank_name, "نام بانک", 80)
        if holder_name is not UNSET:
            bank.holder_name = _required(holder_name, "نام و نام خانوادگی صاحب حساب", 120)
        if display_name is not UNSET:
            bank.display_name = _optional(display_name, "نام نمایشی", 80)
        if card_number is not UNSET:
            bank.card_number = clean_card(card_number)
        if account_number is not UNSET:
            bank.account_number = clean_account_number(account_number)
        if sheba is not UNSET:
            bank.sheba = clean_sheba(sheba)
        if opening_balance is not UNSET:
            if opening_balance is None:
                raise ValidationError("موجودی اولیه نمی‌تواند خالی باشد.")
            bank.opening_balance = quantize(opening_balance)
        if current_balance is not UNSET:
            if current_balance is None:
                raise ValidationError("موجودی فعلی نمی‌تواند خالی باشد.")
            # Everything the books put in or took out, across every book that uses the account.
            shares = (await self._summary(bank)).shares
            bank.opening_balance = quantize(
                quantize(current_balance) - sum((share.balance for share in shares), ZERO)
            )
        if is_active is not UNSET:
            if is_active is None:
                raise ValidationError("فعال یا غیرفعال را مشخص کن.")
            bank.is_active = bool(is_active)
        await self.session.flush()
        # The ledger account carries the name the account is shown by, so a rename reaches it too.
        links = (await self.session.scalars(
            select(BankAccountLink).where(BankAccountLink.bank_account_id == bank.id)
        )).all()
        for link in links:
            account = await self.session.get(Account, link.ledger_account_id)
            if account is not None and account.name != bank.title:
                account.name = bank.title
        await self.session.flush()
        return bank

    async def delete(self, owner_id: uuid.UUID, bank_id: uuid.UUID) -> None:
        """Only an account nothing was ever recorded against can go; any other is switched off."""
        bank = await self._owned(owner_id, bank_id)
        if await self._used(bank.id):
            raise ValidationError("روی این حساب تراکنش یا انتقال ثبت شده؛ به‌جای حذف، غیرفعالش کن.")
        accounts = [row.ledger_account_id for row in (await self.session.scalars(
            select(BankAccountLink).where(BankAccountLink.bank_account_id == bank.id)
        )).all()]
        await self.session.delete(bank)
        await self.session.flush()
        if accounts:
            await self.session.execute(delete(Account).where(Account.id.in_(accounts)))
            await self.session.flush()

    # ---------------------------------------------------------- the link to a book
    async def _lock_book(self, book_id: uuid.UUID) -> None:
        # The same lock recording takes, so a default cannot change under a transaction being recorded.
        await self.session.execute(select(Book.id).where(Book.id == book_id).with_for_update())

    async def link(
        self, actor_id: uuid.UUID, book_id: uuid.UUID, bank_id: uuid.UUID, *,
        make_default: bool = False,
    ) -> BankAccountLink:
        await self.books.require(book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        bank = await self._owned(actor_id, bank_id)
        book = await self.books.get_book(book_id)
        if bank.currency != book.base_currency:
            raise ValidationError(
                f"این حساب به {bank.currency} است و واحد اصلی این دفتر {book.base_currency} است؛ "
                "حساب را فقط می‌شود به دفتری با همان واحد وصل کرد."
            )
        await self._lock_book(book_id)
        existing = await self.session.scalar(select(BankAccountLink).where(
            BankAccountLink.book_id == book_id, BankAccountLink.bank_account_id == bank.id
        ))
        if existing is not None:
            existing.is_active = True
            link = existing
        else:
            account = Account(
                book_id=book_id, code=f"bank-{bank.id.hex[:20]}", name=bank.title,
                type=AccountType.ASSET, currency=bank.currency,
            )
            self.session.add(account)
            await self.session.flush()
            link = BankAccountLink(
                book_id=book_id, bank_account_id=bank.id, ledger_account_id=account.id,
                is_active=True, is_default=False,
            )
            self.session.add(link)
            await self.session.flush()
        has_default = await self.session.scalar(select(BankAccountLink.id).where(
            BankAccountLink.book_id == book_id, BankAccountLink.is_default.is_(True)
        ).limit(1))
        # The first account of a book is its default: that is what a book with one account means.
        if make_default or (has_default is None and bank.is_active):
            await self._make_default(book_id, link)
        return link

    async def _make_default(self, book_id: uuid.UUID, link: BankAccountLink) -> None:
        # Cleared and flushed before the new one is set: the database allows one default per book, and
        # would refuse the moment two rows held it.
        await self.session.execute(
            BankAccountLink.__table__.update()
            .where(BankAccountLink.book_id == book_id, BankAccountLink.id != link.id)
            .values(is_default=False)
        )
        await self.session.flush()
        link.is_default = True
        await self.session.flush()

    async def set_link(
        self, actor_id: uuid.UUID, book_id: uuid.UUID, bank_id: uuid.UUID, *,
        is_active=UNSET, is_default=UNSET,
    ) -> BankAccountLink:
        """Switch the account on or off in this book, or make it this book's default."""
        await self.books.require(book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        link = await self._link(book_id, bank_id)
        await self._lock_book(book_id)
        if is_active is not UNSET:
            if is_active is None:
                raise ValidationError("فعال یا غیرفعال را مشخص کن.")
            link.is_active = bool(is_active)
            if not link.is_active:
                # An account that cannot be chosen cannot be what is chosen for you.
                link.is_default = False
        if is_default is not UNSET and is_default:
            bank = await self.session.get(BankAccount, bank_id)
            if not (link.is_active and bank is not None and bank.is_active):
                raise ValidationError("حساب غیرفعال را نمی‌شود پیش‌فرض کرد.")
            await self._make_default(book_id, link)
        elif is_default is not UNSET:
            link.is_default = False
        await self.session.flush()
        return link

    async def unlink(self, actor_id: uuid.UUID, book_id: uuid.UUID, bank_id: uuid.UUID) -> None:
        await self.books.require(book_id, actor_id, Permission.MANAGE_ACCOUNTS)
        link = await self._link(book_id, bank_id)
        await self._lock_book(book_id)
        if await self._used(bank_id, book_id):
            raise ValidationError(
                "در این دفتر روی این حساب تراکنش یا انتقال ثبت شده؛ به‌جای جدا کردن، غیرفعالش کن."
            )
        account_id = link.ledger_account_id
        await self.session.delete(link)
        await self.session.flush()
        await self.session.execute(delete(Account).where(Account.id == account_id))
        await self.session.flush()

    async def _used(self, bank_id: uuid.UUID, book_id: Optional[uuid.UUID] = None) -> bool:
        """Whether anything was recorded against the account: a transaction or either end of a transfer."""
        tx = select(Transaction.id).where(Transaction.bank_account_id == bank_id)
        moved = select(BankTransfer.id).where(
            (BankTransfer.from_bank_account_id == bank_id) | (BankTransfer.to_bank_account_id == bank_id)
        )
        capital = select(CapitalMovement.id).where(CapitalMovement.bank_account_id == bank_id)
        rules = select(RecurringRule.id).where(RecurringRule.bank_account_id == bank_id)
        legs = select(BankBookTransferLeg.id).where(BankBookTransferLeg.bank_account_id == bank_id)
        feeds = select(IncomeLink.id).where(IncomeLink.bank_account_id == bank_id)
        paid = select(Payment.id).where(Payment.bank_account_id == bank_id)
        lent = select(DebtMovement.id).where(DebtMovement.bank_account_id == bank_id)
        swapped = select(CurrencyConversion.id).where(CurrencyConversion.bank_account_id == bank_id)
        if book_id is not None:
            legs = legs.where(BankBookTransferLeg.book_id == book_id)
            feeds = feeds.where(IncomeLink.target_book_id == book_id)
            paid = paid.where(Payment.book_id == book_id)
            lent = lent.where(DebtMovement.book_id == book_id)
            swapped = swapped.where(CurrencyConversion.book_id == book_id)
        if book_id is not None:
            tx = tx.where(Transaction.book_id == book_id)
            moved = moved.where(BankTransfer.book_id == book_id)
            capital = capital.where(CapitalMovement.book_id == book_id)
            rules = rules.where(RecurringRule.book_id == book_id)
        for query in (tx, moved, capital, rules, legs, feeds, paid, swapped, lent):
            if await self.session.scalar(query.limit(1)):
                return True
        return False

    async def _link(self, book_id: uuid.UUID, bank_id: uuid.UUID) -> BankAccountLink:
        link = await self.session.scalar(select(BankAccountLink).where(
            BankAccountLink.book_id == book_id, BankAccountLink.bank_account_id == bank_id
        ).execution_options(populate_existing=True))
        if link is None:
            raise NotFound(NOT_FOUND)
        return link

    # ------------------------------------------------------ used when recording
    async def resolve(
        self, book_id: uuid.UUID, requested, *, in_base_currency: bool
    ) -> Optional[BankAccountLink]:
        """Which of this book's accounts a transaction is made through, if any.

        Called by the ledger after it has checked the person may record, so there is no permission
        check here. Left out (`UNSET`) means the book's default; `None` means none, on purpose.
        """
        if requested is UNSET:
            if not in_base_currency:
                return None
            return await self.session.scalar(
                select(BankAccountLink)
                .join(BankAccount, BankAccount.id == BankAccountLink.bank_account_id)
                .where(
                    BankAccountLink.book_id == book_id, BankAccountLink.is_default.is_(True),
                    BankAccountLink.is_active.is_(True), BankAccount.is_active.is_(True),
                )
            )
        if requested is None:
            return None
        if not in_base_currency:
            raise ValidationError("حساب بانکی فقط برای مبلغ به واحد اصلی دفتر انتخاب می‌شود.")
        row = (await self.session.execute(
            select(BankAccountLink, BankAccount)
            .join(BankAccount, BankAccount.id == BankAccountLink.bank_account_id)
            .where(BankAccountLink.book_id == book_id, BankAccountLink.bank_account_id == requested)
        )).first()
        if row is None:
            # Not linked here, belonging to someone else, or not there at all: one answer for all three.
            raise NotFound(NOT_FOUND)
        link, bank = row
        if not (link.is_active and bank.is_active):
            raise ValidationError("این حساب بانکی غیرفعال است.")
        return link

    async def titles(self, bank_ids: Sequence[Optional[uuid.UUID]]) -> Dict[uuid.UUID, str]:
        """The names accounts are shown by, for transactions already on screen: no permission check,
        because the caller was let see the transactions, and the name is what picking one showed."""
        wanted = list({bank_id for bank_id in bank_ids if bank_id is not None})
        if not wanted:
            return {}
        rows = (await self.session.scalars(
            select(BankAccount).where(BankAccount.id.in_(wanted))
        )).all()
        return {bank.id: bank.title for bank in rows}

    async def link_for(self, book_id: uuid.UUID, bank_id: Optional[uuid.UUID]) -> Optional[BankAccountLink]:
        """The link a stored transaction already points at, active or not."""
        if bank_id is None:
            return None
        return await self.session.scalar(select(BankAccountLink).where(
            BankAccountLink.book_id == book_id, BankAccountLink.bank_account_id == bank_id
        ))


def can_see_numbers(bank: BankAccount, user_id: uuid.UUID, manager: bool) -> bool:
    return manager or bank.owner_user_id == user_id


__all__ = [
    "BankService", "BookBank", "BankSummary", "LinkShare", "Reconciliation", "ShareCheck", "UNSET",
    "clean_account_number", "clean_card", "clean_sheba", "mask_card", "can_see_numbers",
]
