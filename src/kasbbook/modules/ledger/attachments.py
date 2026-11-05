"""Files attached to a transaction from the web panel.

The rules live here, once. What the file *is* is decided from its first bytes,
never from the name or the type the client sent: a name is typed by whoever
uploads, and a stored "image" that is really HTML served back from our own
origin is how a receipt box becomes a script injection.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from ...shared.errors import NotFound, ValidationError
from ..books.models import Permission
from ..books.service import BookService
from .models import Flow, Transaction, TransactionAttachment

# The reverse proxy in front of this refuses bodies over 2 MB, so a bigger file would die there with
# an error nobody here controls. The panel shrinks photos before sending; this is the limit it aims at.
MAX_BYTES = 1_500_000
MAX_PER_TRANSACTION = 5

TOO_BIG = "فایل بزرگ‌تر از 1.5 مگابایت است؛ عکس را کوچک‌تر بگیر یا فایل سبک‌تری بفرست."
TOO_MANY = "برای هر تراکنش حداکثر 5 فایل می‌شود پیوست کرد."
BAD_TYPE = "فقط عکس (JPEG، PNG، WebP، GIF) و PDF قابل پیوست است."
EMPTY = "فایل خالی است."


def sniff(data: bytes) -> Optional[str]:
    """The media type of the bytes, or None when they are none of the few we accept."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


_EXTENSION = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
              "image/gif": "gif", "application/pdf": "pdf"}


def clean_name(raw: Optional[str], content_type: str) -> str:
    """A name safe to store and to put in a header: no path, no control characters, bounded."""
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f\"<>|?*:]", "", name).strip(" .")
    if not name:
        name = "file"
    stem, dot, ext = name.rpartition(".")
    # The extension follows the bytes, not the claim: a "receipt.pdf" that is a PNG is a PNG.
    base = stem if dot else name
    return f"{base[:100]}.{_EXTENSION[content_type]}"


@dataclass(frozen=True)
class AttachmentInfo:
    id: uuid.UUID
    file_name: str
    content_type: str
    size: int
    created_at: object


class AttachmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    async def _transaction(self, book_id, transaction_id) -> Transaction:
        row = await self.session.get(Transaction, transaction_id)
        if row is None or row.book_id != book_id:
            raise NotFound("این تراکنش پیدا نشد")
        return row

    async def _may_attach(self, book_id, user_id, row: Transaction) -> None:
        """Whoever may edit it, or whoever recorded it and may record: the bot's own split."""
        member = await self.books.membership(book_id, user_id)
        if member is None or not member.is_active:
            raise NotFound("book")
        record = Permission.RECORD_INCOME if row.flow is Flow.INCOME else Permission.RECORD_EXPENSE
        if Permission.EDIT_TRANSACTION in member.permissions:
            return
        if record in member.permissions and row.actor_user_id == user_id:
            return
        await self.books.require(book_id, user_id, Permission.EDIT_TRANSACTION)

    async def list(self, book_id, user_id, transaction_id) -> List[AttachmentInfo]:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        await self._transaction(book_id, transaction_id)
        rows = (await self.session.execute(
            select(TransactionAttachment.id, TransactionAttachment.file_name,
                   TransactionAttachment.content_type, TransactionAttachment.size,
                   TransactionAttachment.created_at)
            .where(TransactionAttachment.transaction_id == transaction_id)
            .order_by(TransactionAttachment.created_at)
        )).all()
        return [AttachmentInfo(*row) for row in rows]

    async def counts(self, book_id, user_id, transaction_ids: Sequence[uuid.UUID]) -> Dict[uuid.UUID, int]:
        """How many files each transaction has, for a list page, in one query."""
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        if not transaction_ids:
            return {}
        rows = (await self.session.execute(
            select(TransactionAttachment.transaction_id, func.count())
            .where(TransactionAttachment.transaction_id.in_(list(transaction_ids)))
            .group_by(TransactionAttachment.transaction_id)
        )).all()
        return {tx: count for tx, count in rows}

    async def add(self, book_id, user_id, transaction_id, raw_name: Optional[str],
                  data: bytes) -> AttachmentInfo:
        row = await self._transaction(book_id, transaction_id)
        await self._may_attach(book_id, user_id, row)
        if not data:
            raise ValidationError(EMPTY)
        if len(data) > MAX_BYTES:
            raise ValidationError(TOO_BIG)
        content_type = sniff(data)
        if content_type is None:
            raise ValidationError(BAD_TYPE)
        held = await self.session.scalar(
            select(func.count()).select_from(TransactionAttachment)
            .where(TransactionAttachment.transaction_id == transaction_id)
        )
        if (held or 0) >= MAX_PER_TRANSACTION:
            raise ValidationError(TOO_MANY)
        attachment = TransactionAttachment(
            book_id=book_id, transaction_id=transaction_id, uploaded_by_id=user_id,
            file_name=clean_name(raw_name, content_type), content_type=content_type,
            size=len(data), data=data,
        )
        self.session.add(attachment)
        await self.session.flush()
        # created_at is filled by the database; reading it unloaded would query from async code.
        await self.session.refresh(attachment, ["created_at"])
        return AttachmentInfo(attachment.id, attachment.file_name, attachment.content_type,
                              attachment.size, attachment.created_at)

    async def read(self, book_id, user_id, transaction_id, attachment_id) -> TransactionAttachment:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        # The bytes are deferred everywhere else, so a list or a delete never reads them; a download does.
        row = await self.session.get(
            TransactionAttachment, attachment_id, options=[undefer(TransactionAttachment.data)]
        )
        # Both ids must agree with the path: a file id must not open under another book's URL.
        if row is None or row.book_id != book_id or row.transaction_id != transaction_id:
            raise NotFound("این فایل پیدا نشد")
        return row

    async def remove(self, book_id, user_id, transaction_id, attachment_id) -> None:
        tx = await self._transaction(book_id, transaction_id)
        await self._may_attach(book_id, user_id, tx)
        row = await self.session.get(TransactionAttachment, attachment_id)
        if row is None or row.book_id != book_id or row.transaction_id != transaction_id:
            raise NotFound("این فایل پیدا نشد")
        await self.session.delete(row)
        await self.session.flush()
