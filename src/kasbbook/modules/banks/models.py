"""Bank accounts: one real account, any number of books.

A bank account belongs to a person (`owner_user_id`), not to a book, because the same account can be
used from a personal book and a business book at once. A `BankAccountLink` is what puts it in a book.

Each link owns its own ledger account inside that book. That is what keeps every book's trial balance
closed on its own: a book never writes a line against an account that lives in another book. The
account's real balance is not stored anywhere. It is the opening balance plus what every linked book's
ledger account holds, so it cannot drift from the transactions the way a stored number would.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey
from ...shared.money import Money


class BankAccount(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "bank_accounts"

    # RESTRICT: a person whose accounts are still used by other people's books is anonymised, not
    # dropped (see IdentityService._delete_account), so the account keeps a name to answer to.
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # The bank and the holder are what make it recognisable, so both are required; the rest is for
    # the person who needs to copy a number, and is optional.
    bank_name: Mapped[str] = mapped_column(String(80), nullable=False)
    holder_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # What the screens show. Empty means "bank name and holder", worked out in `title`, never stored,
    # so renaming the bank renames the account everywhere it is not given a name of its own.
    display_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    card_number: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sheba: Mapped[Optional[str]] = mapped_column(String(26), nullable=True)

    # Money in the book's base currency only: a book's journal is in its base currency, and adding two
    # currencies together means nothing. A book of another base currency cannot link it.
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="IRT")
    # What was in the account before anything was recorded here. A fact about the account, not a
    # transaction, so it never counts as income and never moves anyone's share.
    opening_balance: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0"), server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @property
    def title(self) -> str:
        return (self.display_name or "").strip() or f"{self.bank_name} {self.holder_name}"


class BankAccountLink(UUIDPrimaryKey, Timestamped, Base):
    """A bank account as one book sees it."""

    __tablename__ = "bank_account_links"
    __table_args__ = (
        UniqueConstraint("book_id", "bank_account_id", name="one_link_per_book_and_bank"),
        # One default per book, enforced by the database rather than hoped for: two requests making
        # different accounts the default at once cannot both succeed.
        Index(
            "one_default_bank_per_book", "book_id", unique=True,
            sqlite_where=text("is_default"), postgresql_where=text("is_default"),
        ),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False
    )
    # This book's ledger account for the bank. Removed with the book, never on its own.
    ledger_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    # Off means: not offered for new transactions here, still shown on the ones that used it.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BankTransfer(UUIDPrimaryKey, Timestamped, Base):
    """Money moved from one of a book's accounts to another of the same book.

    Deliberately not a transaction. `compute_distribution` adds up income and expense to decide what
    everyone is paid, so a transfer recorded as both would inflate the pie and move every member's
    share for money that never left the book. It is a journal entry of its own: debit where the money
    arrives, credit where it left. Both accounts must be linked to this book, which is what keeps each
    book's trial balance closed; moving money between two *books* is a different thing (an owner's
    draw or contribution) and is not this.
    """

    __tablename__ = "bank_transfers"
    __table_args__ = (
        CheckConstraint("from_bank_account_id != to_bank_account_id", name="transfer_between_two_accounts"),
        Index("ix_bank_transfers_book_day", "book_id", "occurred_on"),
        ForeignKeyConstraint(
            ["book_id", "from_bank_account_id"],
            ["bank_account_links.book_id", "bank_account_links.bank_account_id"],
            name="fk_transfer_from_book", deferrable=True, initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["book_id", "to_bank_account_id"],
            ["bank_account_links.book_id", "bank_account_links.bank_account_id"],
            name="fk_transfer_to_book", deferrable=True, initially="DEFERRED",
        ),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    from_bank_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    to_bank_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # The journal entry that carries it. Removed with it: the transfer is the entry's only meaning.
    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False
    )
