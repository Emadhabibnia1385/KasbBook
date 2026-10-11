"""The wallet in the bot: a book's currencies, its balances, and converting between them.

A conversion is not a transaction - it lives in its own table so a swap never
inflates the income and expense a payout is computed from - which is why it has
its own flow here rather than going through the entry screens.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from ...shared.parsing import parse_amount
from .. import screens
from .base import Feature


class WalletFeature(Feature):
    prefixes = ("cu",)
    flows = ("conversion",)

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""
        if area == "cu":
            return await self._currency_callback(action, argument, user, key)
        raise AssertionError(area)

    async def text(self, text, draft, user, key, event):
        if draft.get("flow") == "conversion":
            return await self._conversion_text(text, draft, user, key)
        raise AssertionError(draft.get("flow"))

    # ------------------------------------------------- wallet and currencies
    async def _currency_callback(self, action: str, argument: str, user, key: str):
        if action in ("home", "set", "conv"):
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            if action == "set":
                options = await self.ctx.exchange.options(user.id, book.id)
                await self.ctx.state.set(key, {"flow": "currency", "book_id": argument})
                return screens.currency_settings(book, options)

            balances, worth = await self.ctx.exchange.valuation(user.id, book.id)
            if action == "conv":
                # Nothing you do not hold can be converted, so the picker only
                # offers what has a balance.
                holdings = [b for b in balances if b.amount > Decimal("0")]
                if not holdings:
                    return screens.error("کیف پول این دفتر خالی است.")
                await self.ctx.state.set(key, {"flow": "conversion", "book_id": argument})
                return screens.conversion_pick_source(book, holdings)

            await self.ctx.state.clear(key)
            return screens.currency_home(book, balances, len(balances) > 1, worth)

        # Everything below reads the book from conversation state, where it was
        # put after a permission check, rather than from the button.
        draft = await self.ctx.state.get(key)

        if action == "tog":
            if draft.get("flow") != "currency":
                return screens.stale(None, user.display_name)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            enabled = {o.code for o in await self.ctx.exchange.options(user.id, book.id) if o.enabled}
            await self.ctx.exchange.set_enabled(
                user.id, book.id, argument, argument not in enabled
            )
            return screens.currency_settings(
                book, await self.ctx.exchange.options(user.id, book.id)
            )

        if action == "from":
            if draft.get("flow") != "conversion":
                return screens.stale(None, user.display_name)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            held = await self.ctx.exchange.balance_of(book.id, argument)
            draft["from"] = argument
            draft["awaiting"] = "amount"
            await self.ctx.state.set(key, draft)
            return screens.conversion_ask_amount(argument, held)

        if action == "to":
            if draft.get("flow") != "conversion" or not draft.get("amount"):
                return screens.stale(None, user.display_name)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            draft["to"] = argument
            draft["awaiting"] = "target"
            await self.ctx.state.set(key, draft)
            return screens.conversion_ask_target_amount(
                draft["from"], Decimal(draft["amount"]), argument
            )

        return screens.stale(None, user.display_name)

    async def _conversion_text(self, text: str, draft: dict, user, key: str):
        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        stage = draft.get("awaiting")

        if stage == "amount":
            amount = parse_amount(text)
            if amount is None or amount <= Decimal("0"):
                held = await self.ctx.exchange.balance_of(book.id, draft["from"])
                return screens.conversion_ask_amount(draft["from"], held)
            draft["amount"] = str(amount)
            draft["awaiting"] = "to"
            await self.ctx.state.set(key, draft)
            return screens.conversion_pick_target(
                draft["from"], await self.ctx.exchange.allowed(book.id)
            )

        if stage == "target":
            amount = parse_amount(text)
            if amount is None or amount <= Decimal("0"):
                return screens.conversion_ask_target_amount(
                    draft["from"], Decimal(draft["amount"]), draft["to"]
                )
            draft["target"] = str(amount)
            if book.base_currency not in (draft["from"], draft["to"]):
                draft["awaiting"] = "base"
                await self.ctx.state.set(key, draft)
                return screens.conversion_ask_base_value(book.base_currency)
            return await self._save_conversion(draft, user, key)

        if stage == "base":
            amount = parse_amount(text)
            if amount is None or amount <= Decimal("0"):
                return screens.conversion_ask_base_value(book.base_currency)
            draft["base"] = str(amount)
            return await self._save_conversion(draft, user, key)

        return screens.stale(None, user.display_name)

    async def _save_conversion(self, draft: dict, user, key: str):
        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        conversion = await self.ctx.exchange.convert(
            actor_user_id=user.id,
            book_id=book.id,
            from_currency=draft["from"],
            from_amount=Decimal(draft["amount"]),
            to_currency=draft["to"],
            to_amount=Decimal(draft["target"]),
            base_value=Decimal(draft["base"]) if draft.get("base") else None,
            occurred_on=self.ctx.today(user),
        )
        await self.ctx.state.clear(key)
        return screens.conversion_saved(book, conversion)
