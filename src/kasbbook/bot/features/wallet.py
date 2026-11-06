"""The wallet in the bot: a book's currencies, its balances, and converting between them.

A conversion is not a transaction - it lives in its own table so a swap never
inflates the income and expense a payout is computed from - which is why it has
its own flow here rather than going through the entry screens.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from ...modules.books.models import Permission
from ...shared.errors import ValidationError
from ...shared.money import quantize
from ...shared.parsing import parse_amount
from .. import screens
from .base import Feature


class WalletFeature(Feature):
    prefixes = ("cu",)
    flows = ("conversion", "currency")

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""
        if area == "cu":
            return await self._currency_callback(action, argument, user, key)
        raise AssertionError(area)

    async def text(self, text, draft, user, key, event):
        if draft.get("flow") == "conversion":
            return await self._conversion_text(text, draft, user, key)
        if draft.get("flow") == "currency":
            return await self._currency_find_text(text, draft, user)
        raise AssertionError(draft.get("flow"))

    async def _currency_find_text(self, text, draft, user):
        """A typed name or code, answered with the catalog's matches for this book."""
        from ...modules.exchange.catalog import search

        if draft.get("awaiting") != "find":
            # A line typed on the tick screen is not an answer to anything.
            return screens.stale(None, user.display_name)
        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        options = await self.ctx.exchange.options(user.id, book.id)
        enabled = {o.code for o in options if o.enabled}
        matches = search(text)
        # What was found may need switching on, so the tick handler's own check
        # (the book from the draft, not from the button) still applies to it.
        return screens.currency_find_results(book, matches, enabled)

    async def _prices(self, book):
        """Crypto the market publishes, and national currencies as labelled estimates, in toman."""
        rates = self.ctx.rates
        table = getattr(rates, "table", None)
        if table is None:
            return screens.prices_screen(book, [], [], 0)
        crypto = await table(["USDT", "BTC", "ETH", "TON", "TRX"], "IRT")
        countries = await table(["USD", "EUR", "GBP", "AED", "TRY"], "IRT")
        stamps = [q.fetched_at for _, q in crypto + countries if q.fetched_at]
        from ...shared.security import utcnow

        age = int((utcnow() - min(stamps)).total_seconds()) if stamps else 0
        return screens.prices_screen(book, crypto, countries, max(0, age))

    # ------------------------------------------------- wallet and currencies
    async def _currency_callback(self, action: str, argument: str, user, key: str):
        if action == "prices":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.books.require(book.id, user.id, Permission.VIEW_REPORTS)
            return await self._prices(book)

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
                    # The wallet this was tapped from is one level up, so a
                    # refusal goes back there rather than dropping the person
                    # home from a book they were in the middle of.
                    return screens.error("کیف پول این دفتر خالی است.",
                                         back=f"cu:home:{argument}")
                await self.ctx.state.set(key, {"flow": "conversion", "book_id": argument})
                return screens.conversion_pick_source(book, holdings)

            await self.ctx.state.clear(key)
            return screens.currency_home(book, balances, len(balances) > 1, worth)

        # Everything below reads the book from conversation state, where it was
        # put after a permission check, rather than from the button.
        draft = await self.ctx.state.get(key)

        if action == "find":
            if draft.get("flow") != "currency":
                return screens.stale(None, user.display_name)
            draft["awaiting"] = "find"
            await self.ctx.state.set(key, draft)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            return screens.currency_find_ask(book)

        if action == "tog":
            if draft.get("flow") != "currency":
                return screens.stale(None, user.display_name)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            enabled = {o.code for o in await self.ctx.exchange.options(user.id, book.id) if o.enabled}
            await self.ctx.exchange.set_enabled(
                user.id, book.id, argument, argument not in enabled
            )
            if draft.get("awaiting") == "find":
                # Came from a search: stay on the search so several can be switched on in a row.
                options = await self.ctx.exchange.options(user.id, book.id)
                from ...modules.exchange.catalog import BY_CODE

                return screens.currency_find_results(
                    book, [BY_CODE[argument]], {o.code for o in options if o.enabled}
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
            return screens.conversion_ask_amount(book, argument, held)

        if action == "all":
            # The whole balance, taken from the button that printed it. It is
            # read again here rather than carried in the callback: a figure a
            # person is about to spend is worth one query.
            if draft.get("flow") != "conversion" or draft.get("from") != argument:
                return screens.stale(None, user.display_name)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            held = await self.ctx.exchange.balance_of(book.id, argument)
            if held <= Decimal("0"):
                # Drawn when there was a balance, tapped after it went.
                return screens.conversion_ask_amount(book, argument, held)
            draft["amount"] = str(held)
            draft["awaiting"] = "to"
            await self.ctx.state.set(key, draft)
            return screens.conversion_pick_target(
                book, argument, await self.ctx.exchange.allowed(book.id)
            )

        if action == "to":
            if draft.get("flow") != "conversion" or not draft.get("amount"):
                return screens.stale(None, user.display_name)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            amount = Decimal(draft["amount"])
            draft["to"] = argument
            draft["awaiting"] = "target"
            suggested = await self._quoted(book, draft["from"], amount, argument)
            # Kept in the draft so the button settles the very figure the screen
            # showed, not whatever the rate has moved to by the time it is
            # tapped. "" means there was no quote and nothing to confirm.
            draft["suggest"] = str(suggested) if suggested is not None else ""
            await self.ctx.state.set(key, draft)
            return screens.conversion_ask_target_amount(
                book, draft["from"], amount, argument, suggested
            )

        if action == "ok":
            # The rate-derived figure, accepted as typed. Everything below the
            # amount is the typed path's, so this joins it at the same point.
            if (draft.get("flow") != "conversion" or draft.get("awaiting") != "target"
                    or not draft.get("suggest")):
                return screens.stale(None, user.display_name)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            draft["target"] = draft["suggest"]
            if book.base_currency not in (draft["from"], draft["to"]):
                draft["awaiting"] = "base"
                await self.ctx.state.set(key, draft)
                return screens.conversion_ask_base_value(book, book.base_currency)
            return await self._save_conversion(draft, user, key)

        return screens.stale(None, user.display_name)

    async def _quoted(self, book, from_code: str, from_amount: Decimal, to_code: str):
        """What today's rates say comes back, or None when nobody knows.

        Both sides are priced in the book's own currency, so a swap between two
        tokens crosses through it. A missing price on either side means there is
        no figure to offer and the person types what they actually got — the
        same answer as a deployment with no rate source at all.
        """
        rates = []
        for code in (from_code, to_code):
            if code == book.base_currency:
                rates.append(Decimal("1"))
                continue
            rate = await self.ctx.exchange.quote(code, book.base_currency)
            if not rate:
                return None
            rates.append(rate)

        from_rate, to_rate = rates
        try:
            figure = quantize(from_amount * from_rate / to_rate)
        except ValidationError:
            # A holding large enough to overflow the column still deserves a
            # working screen; it just gets no suggestion.
            return None
        if to_code in screens.WHOLE_UNIT_CURRENCIES:
            # Shown without decimals, so offer the figure that was shown rather
            # than record a fraction nobody saw on the button they tapped.
            figure = figure.quantize(Decimal("1"))
        return figure if figure > Decimal("0") else None

    async def _conversion_text(self, text: str, draft: dict, user, key: str):
        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        stage = draft.get("awaiting")

        if stage == "amount":
            amount = parse_amount(text)
            if amount is None or amount <= Decimal("0"):
                held = await self.ctx.exchange.balance_of(book.id, draft["from"])
                return screens.conversion_ask_amount(book, draft["from"], held)
            draft["amount"] = str(amount)
            draft["awaiting"] = "to"
            await self.ctx.state.set(key, draft)
            return screens.conversion_pick_target(
                book, draft["from"], await self.ctx.exchange.allowed(book.id)
            )

        if stage == "target":
            amount = parse_amount(text)
            if amount is None or amount <= Decimal("0"):
                # The offer survives a mistyped number: it was the rate's
                # answer, and the rate has not changed because of a typo.
                suggested = Decimal(draft["suggest"]) if draft.get("suggest") else None
                return screens.conversion_ask_target_amount(
                    book, draft["from"], Decimal(draft["amount"]), draft["to"],
                    suggested,
                )
            draft["target"] = str(amount)
            if book.base_currency not in (draft["from"], draft["to"]):
                draft["awaiting"] = "base"
                await self.ctx.state.set(key, draft)
                return screens.conversion_ask_base_value(book, book.base_currency)
            return await self._save_conversion(draft, user, key)

        if stage == "base":
            amount = parse_amount(text)
            if amount is None or amount <= Decimal("0"):
                return screens.conversion_ask_base_value(book, book.base_currency)
            draft["base"] = str(amount)
            return await self._save_conversion(draft, user, key)

        return screens.stale(None, user.display_name)

    async def _save_conversion(self, draft: dict, user, key: str):
        # Claimed before it is recorded, so a second confirm in flight finds
        # nothing to record. It matters now that a button can get here: webhook
        # mode runs updates concurrently, and two taps used to mean two swaps.
        claimed = await self.ctx.state.pop(key)
        if claimed.get("flow") != "conversion":
            if claimed:
                # Another flow began in between; its draft is not ours to eat.
                await self.ctx.state.set(key, claimed)
            return screens.stale(None, user.display_name)

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        try:
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
        except Exception:
            # A refused conversion must not eat the draft: give it back, so a
            # figure the wallet cannot cover can be corrected where it was typed.
            await self.ctx.state.set(key, draft)
            raise
        return screens.conversion_saved(book, conversion)
