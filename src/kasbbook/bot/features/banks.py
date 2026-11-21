"""Bank accounts in the bot: see a book's accounts, make one the default, move a transaction to one.

Adding an account takes a card number and a Sheba, which are better typed in the panel than in a chat,
so the bot reads and arranges accounts but does not create them. Every rule is the service's: the bot
only chooses which account to ask about and draws the answer.
"""

from __future__ import annotations

import uuid

from ...shared.errors import KasbBookError, NotFound
from .. import screens
from .base import Feature


class BanksFeature(Feature):
    prefixes = ("ba",)

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        if action == "home":
            book = await self.ctx.books.get_book(uuid.UUID(parts[2]))
            return screens.bank_home(book, await self.ctx.ledger.banks.for_book(book.id, user.id))
        if action == "df":
            return await self._make_default(parts, user)
        if action in ("pk", "st"):
            return await self._for_transaction(action, parts, user)
        raise AssertionError(action)

    async def _make_default(self, parts, user):
        book = await self.ctx.books.get_book(uuid.UUID(parts[2]))
        rows = await self.ctx.ledger.banks.for_book(book.id, user.id)
        chosen = next((row for row in rows if screens.bank_code(row.bank) == parts[3]), None)
        if chosen is None:
            return screens.error("این حساب دیگر در این دفتر نیست.", back=f"ba:home:{book.id}")
        await self.ctx.ledger.banks.set_link(user.id, book.id, chosen.bank.id, is_default=True)
        return screens.bank_home(book, await self.ctx.ledger.banks.for_book(book.id, user.id))

    async def _book_and_tx(self, user, tx_id: uuid.UUID):
        for book in await self.ctx.books.books_for_user(user.id):
            try:
                return book, await self.ctx.ledger.get_transaction(book.id, user.id, tx_id)
            except KasbBookError:
                continue
        raise NotFound("transaction")

    async def _for_transaction(self, action, parts, user):
        try:
            book, tx = await self._book_and_tx(user, uuid.UUID(parts[2]))
        except NotFound:
            return screens.error("این تراکنش دیگر وجود ندارد؛ شاید حذف شده است.", back="tx:new")
        origin = parts[-1] if parts[-1] in ("a", "b") and len(parts) > (3 if action == "pk" else 4) else ""
        tail = f":{origin}" if origin else ""
        rows = await self.ctx.ledger.banks.for_book(book.id, user.id)
        if action == "pk":
            return screens.pick_for_transaction(book, tx, rows, tail)
        wanted = parts[3]
        chosen = next((row for row in rows if screens.bank_code(row.bank) == wanted), None)
        if wanted != "-" and chosen is None:
            return screens.error("این حساب دیگر در این دفتر نیست.", back=f"td:open:{tx.id}{tail}")
        await self.ctx.ledger.update(
            book.id, user.id, tx.id, bank_account_id=chosen.bank.id if chosen else None
        )
        return screens.bank_changed(tx, chosen.bank.title if chosen else "", tail)
