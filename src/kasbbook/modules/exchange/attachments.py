"""Files kept with a currency conversion (the exchange slip, the receipt of a transfer).

The same rules as a transaction's files (`ledger.attachments`): what a file is comes from its bytes, never
from its name, and it is read back only through the book's gate.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from ...shared.errors import NotFound, ValidationError
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.attachments import BAD_TYPE, EMPTY, MAX_BYTES, TOO_BIG, AttachmentInfo, clean_name, sniff
from .models import ConversionAttachment, CurrencyConversion

MAX_PER_CONVERSION = 5
TOO_MANY = "برای هر تبدیل حداکثر 5 فایل می‌شود پیوست کرد."


class ConversionAttachmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)

    async def _conversion(self, book_id, conversion_id) -> CurrencyConversion:
        row = await self.session.get(CurrencyConversion, conversion_id)
        if row is None or row.book_id != book_id:
            raise NotFound("این تبدیل پیدا نشد")
        return row

    async def list(self, book_id, user_id, conversion_id) -> List[AttachmentInfo]:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        await self._conversion(book_id, conversion_id)
        rows = (await self.session.execute(
            select(ConversionAttachment.id, ConversionAttachment.file_name,
                   ConversionAttachment.content_type, ConversionAttachment.size,
                   ConversionAttachment.created_at)
            .where(ConversionAttachment.conversion_id == conversion_id)
            .order_by(ConversionAttachment.created_at)
        )).all()
        return [AttachmentInfo(*row) for row in rows]

    async def add(self, book_id, user_id, conversion_id, raw_name: Optional[str], data: bytes) -> AttachmentInfo:
        await self.books.require(book_id, user_id, Permission.MANAGE_TREASURY)
        await self._conversion(book_id, conversion_id)
        if not data:
            raise ValidationError(EMPTY)
        if len(data) > MAX_BYTES:
            raise ValidationError(TOO_BIG)
        content_type = sniff(data)
        if content_type is None:
            raise ValidationError(BAD_TYPE)
        held = await self.session.scalar(
            select(func.count()).select_from(ConversionAttachment)
            .where(ConversionAttachment.conversion_id == conversion_id)
        )
        if (held or 0) >= MAX_PER_CONVERSION:
            raise ValidationError(TOO_MANY)
        row = ConversionAttachment(
            book_id=book_id, conversion_id=conversion_id, uploaded_by_id=user_id,
            file_name=clean_name(raw_name, content_type), content_type=content_type,
            size=len(data), data=data,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row, ["created_at"])
        return AttachmentInfo(row.id, row.file_name, row.content_type, row.size, row.created_at)

    async def read(self, book_id, user_id, conversion_id, attachment_id) -> ConversionAttachment:
        await self.books.require(book_id, user_id, Permission.VIEW_TRANSACTIONS)
        row = await self.session.get(
            ConversionAttachment, attachment_id, options=[undefer(ConversionAttachment.data)]
        )
        if row is None or row.book_id != book_id or row.conversion_id != conversion_id:
            raise NotFound("این فایل پیدا نشد")
        return row

    async def remove(self, book_id, user_id, conversion_id, attachment_id) -> None:
        await self.books.require(book_id, user_id, Permission.MANAGE_TREASURY)
        row = await self.session.get(ConversionAttachment, attachment_id)
        if row is None or row.book_id != book_id or row.conversion_id != conversion_id:
            raise NotFound("این فایل پیدا نشد")
        await self.session.delete(row)
        await self.session.flush()
