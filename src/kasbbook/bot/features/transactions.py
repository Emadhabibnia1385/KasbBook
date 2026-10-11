"""Entries in the bot: recording, the quick line, the daily list, a card, receipts, search.

The heart of what people do every day, and the only feature that also owns the
plain typed line: `quick_line` is what the conversation falls back to when no
draft is waiting, and `attachment` is how a photo or file becomes a receipt.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime
from decimal import Decimal

from ...adapters.base import IncomingEvent
from ...modules.books.models import Permission
from ...modules.ledger.models import Flow, Scope
from ...shared.errors import KasbBookError, ValidationError
from ...shared.parsing import parse_amount, parse_date
from .. import quick, screens
from .base import SCOPE_FOR_BOOK, Feature, read_amount


class TransactionsFeature(Feature):
    prefixes = ("tx", "qk", "td", "dl", "sr")
    flows = ("tx", "tx_edit", "daily_date", "search")

    # Transactions per page of a book's list.
    TX_PAGE = 8

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""
        if area == "tx":
            return await self._tx_callback(action, argument, user, key)
        if area == "qk":
            nonce = parts[3] if len(parts) > 3 else ""
            return await self._quick_callback(action, argument, nonce, user, key)
        if area == "td":
            return await self._tx_detail_callback(action, argument, user, key, event)
        if area == "dl":
            return await self._daily_callback(parts, user, key)
        if area == "sr":
            return await self._search_callback(action, argument, user, key)
        raise AssertionError(area)

    async def text(self, text, draft, user, key, event):
        if draft.get("flow") == "tx":
            return await self._tx_text(text, draft, user, key)
        if draft.get("flow") == "tx_edit":
            return await self._edit_tx_text(text, draft, user, key)
        if draft.get("flow") == "daily_date":
            return await self._daily_date_text(text, draft, user, key)
        if draft.get("flow") == "search":
            return await self._search_text(text, draft, user, key)
        raise AssertionError(draft.get("flow"))

    async def _tx_callback(self, action: str, argument: str, user, key: str):
        if action == "skip":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") == "tx" and draft.get("awaiting") == "description":
                return await self._save_tx(draft, user, key)
            # Nothing to skip: the entry was recorded already (a double tap) or
            # this button belongs to an old message.
            return screens.stale(None, user.display_name)
        if action == "new":
            await self.ctx.state.clear(key)
            return screens.tx_home(self.ctx.today(user))

        if action == "one":
            await self.ctx.state.clear(key)
            books = await self.ctx.books.books_for_user(user.id)
            if len(books) == 1:
                return await self._start_single(books[0], user, key)
            return screens.pick_book(books, "tx")

        if action == "book":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            return await self._start_single(book, user, key)

        if action == "on":
            draft = await self.ctx.state.get(key)
            if not draft.get("book_id"):
                return screens.tx_home(self.ctx.today(user))
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))

            if argument == "ask":
                draft["awaiting"] = "date"
                await self.ctx.state.set(key, draft)
                return screens.ask_date("tx:new")

            draft["on"] = self.ctx.today(user).isoformat()
            await self.ctx.state.set(key, draft)
            return screens.pick_type(book, self.ctx.today(user))

        if action == "type":
            entry = screens.ENTRY_TYPES.get(argument)
            draft = await self.ctx.state.get(key)
            if entry is None or not draft.get("book_id"):
                return screens.tx_home(self.ctx.today(user))

            draft["direction"] = entry[0].value
            draft["scope"] = entry[1].value
            return await self._ask_category(draft, user, key)

        if action == "flow":
            # Buttons from before the date and type steps existed may still be
            # on somebody's screen. They keep working: the book's own scope,
            # and a date left for record() to fill in with the book's today.
            draft = await self.ctx.state.get(key)
            if not draft.get("book_id"):
                return screens.pick_book(await self.ctx.books.books_for_user(user.id), "tx")

            draft["direction"] = argument
            return await self._ask_category(draft, user, key)

        if action == "cur":
            draft = await self.ctx.state.get(key)
            if draft.get("awaiting") != "currency" or not draft.get("book_id"):
                return screens.stale(None, user.display_name)

            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            if argument not in await self.ctx.exchange.allowed(book.id):
                return screens.error("این ارز برای این دفتر فعال نیست.")

            draft["currency"] = argument
            if argument == book.base_currency:
                draft.pop("rate", None)
                draft["awaiting"] = "description"
                await self.ctx.state.set(key, draft)
                return screens.ask_description()

            live = await self.ctx.exchange.quote(argument, book.base_currency)
            if live is not None:
                # Today's market price, applied so the person does not have to
                # type it. It is shown rather than hidden, and overridable,
                # because an OTC deal is often not the market price.
                draft["rate"] = str(live)
                draft["awaiting"] = "description"
                await self.ctx.state.set(key, draft)
                return screens.ask_description_with_rate(
                    argument, live, book.base_currency,
                    Decimal(draft["amount"]) * live,
                )

            draft["awaiting"] = "rate"
            await self.ctx.state.set(key, draft)
            return screens.ask_rate(argument, book.base_currency)

        if action == "rate":
            draft = await self.ctx.state.get(key)
            if not draft.get("currency") or not draft.get("book_id"):
                return screens.stale(None, user.display_name)
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            draft["awaiting"] = "rate"
            await self.ctx.state.set(key, draft)
            return screens.ask_rate(draft["currency"], book.base_currency)

        if action == "cat":
            draft = await self.ctx.state.get(key)
            recent = draft.get("recent") or []
            try:
                if int(argument) < 0:
                    raise IndexError
                draft["category"] = recent[int(argument)]
            except (ValueError, IndexError):
                # The suggestions moved on since this screen was drawn.
                return screens.ask_category(Flow(draft.get("direction", "expense")), recent)

            if draft.get("flow") == "tx_edit" and draft.get("field") == "category":
                return await self._edit_tx_text(draft["category"], draft, user, key)
            await self.ctx.state.set(key, draft)
            return screens.ask_amount(draft["category"])

        return screens.tx_home(self.ctx.today(user))

    @staticmethod
    def _day_from_token(token: str, fallback: date) -> date:
        try:
            return datetime.strptime(token, "%Y%m%d").date()
        except (ValueError, TypeError):
            return fallback

    async def _start_single(self, book, user, key: str):
        # Checked before anything is drawn: the next screen names the book, and
        # a crafted button should not be a way to learn another book's name.
        await self.ctx.books.require(book.id, user.id, Permission.VIEW_TRANSACTIONS)
        await self.ctx.state.set(key, {"flow": "tx", "book_id": str(book.id)})
        return screens.pick_date(book, self.ctx.today(user))

    async def _ask_category(self, draft: dict, user, key: str):
        flow = Flow(draft["direction"])
        # Kept in the draft so a press can name one by position. The callback
        # payload has sixty-four bytes; a Persian category does not reliably
        # fit, and a button that overflows it fails silently.
        recent = [row.name for row in await self.ctx.categories.list(uuid.UUID(draft["book_id"]), user.id, flow)]
        draft["recent"] = recent
        await self.ctx.state.set(key, draft)
        return screens.ask_category(flow, recent)

    async def _daily_callback(self, parts, user, key: str):
        """dl:v shows a day, dl:go asks for one, dl:ab and dl:add record into one."""
        action = parts[1] if len(parts) > 1 else ""
        today = self.ctx.today(user)
        on = self._day_from_token(parts[2] if len(parts) > 2 else "", today)

        if action == "v":
            view = parts[3] if len(parts) > 3 else "a"
            page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
            await self.ctx.state.clear(key)
            return await self._daily_screen(user, on, view, page)

        if action == "go":
            view = parts[2] if len(parts) > 2 else "a"
            await self.ctx.state.set(key, {"flow": "daily_date", "view": view})
            return screens.ask_date(f"dl:v:{screens.day_token(today)}:{view}:0")

        if action == "ab" and len(parts) > 3:
            book = await self.ctx.books.get_book(uuid.UUID(parts[3]))
            await self.ctx.books.require(book.id, user.id, Permission.VIEW_TRANSACTIONS)
            return screens.daily_pick_type(book, on)

        if action == "add" and len(parts) > 4:
            book = await self.ctx.books.get_book(uuid.UUID(parts[3]))
            entry = screens.ENTRY_TYPES.get(parts[4])
            if entry is None:
                return await self._daily_screen(user, on, "a", 0)

            origin = parts[5] if len(parts) > 5 else "a"
            draft = {
                "flow": "tx",
                "book_id": str(book.id),
                "on": on.isoformat(),
                "direction": entry[0].value,
                "scope": entry[1].value,
                # Recorded from the list, so the list is what comes back.
                "back": {"on": on.isoformat(),
                         "view": str(book.id) if origin == "b" else "a"},
            }
            return await self._ask_category(draft, user, key)

        return await self._daily_screen(user, today, "a", 0)

    async def _daily_screen(self, user, on: date, view: str, page: int):
        books = await self.ctx.books.books_for_user(user.id)
        if not books:
            return screens.pick_book(books, "tx")

        book_id = None
        if view and view != "a":
            try:
                book_id = uuid.UUID(view)
            except ValueError:
                book_id = None

        sheets = await self.ctx.reports.day(user.id, on, book_id)
        return screens.daily_view(on, self.ctx.today(user), sheets, books, book_id, page)

    async def attachment(self, event: IncomingEvent, user, key: str):
        """A file only means something while a receipt is being asked for."""
        draft = await self.ctx.state.get(key)
        if draft.get("flow") == "tx" and draft.get("awaiting") == "description":
            return await self._save_tx(draft, user, key, event.text, event.attachment)
        if draft.get("flow") != "receipt" or event.attachment is None:
            return None

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        await self.ctx.ledger.attach_receipt(
            book.id, user.id, uuid.UUID(draft["tx_id"]),
            event.attachment.file_id, self.ctx.provider.value,
            kind=event.attachment.kind,
            file_name=event.attachment.file_name,
            mime_type=event.attachment.mime_type,
        )
        await self.ctx.state.clear(key)

        tx = await self.ctx.ledger.get_transaction(
            book.id, user.id, uuid.UUID(draft["tx_id"])
        )
        return await self._transaction_screen(book, tx, user, draft.get("origin", ""))

    async def _tx_list(self, book, user, page: int = 0):
        rows = await self.ctx.ledger.transactions(book.id, user.id)
        start = max(0, page) * self.TX_PAGE
        return screens.transaction_list(
            book, rows[start:start + self.TX_PAGE], page, len(rows), self.TX_PAGE
        )

    async def _tx_and_book(self, user, transaction_id: uuid.UUID):
        for book in await self.ctx.books.books_for_user(user.id):
            try:
                tx = await self.ctx.ledger.get_transaction(book.id, user.id, transaction_id)
            except KasbBookError:
                continue
            return book, tx
        return None, None

    async def _tx_detail_callback(self, action: str, argument: str, user, key: str, event):
        if action == "clear_description":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "tx_edit" or draft.get("field") != "description":
                return screens.stale(None, user.display_name)
            return await self._edit_tx_text(None, draft, user, key)
        parts = (event.callback_data or "").split(":")

        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            return await self._tx_list(book, user)

        if action == "page":
            book = await self.ctx.books.get_book(uuid.UUID(parts[2]))
            return await self._tx_list(book, user, int(parts[3]))

        # Opened from the daily list: see screens.transaction_detail.
        origin = parts[3] if len(parts) > 3 and parts[3] in ("a", "b") else ""
        tail = f":{origin}" if origin else ""

        target = uuid.UUID(argument)
        book, tx = await self._tx_and_book(user, target)
        if tx is None:
            return screens.error("این تراکنش دیگر وجود ندارد؛ شاید حذف شده است.", back="tx:new")

        if action == "open":
            return await self._transaction_screen(book, tx, user, origin)

        if action in ("ec", "ea", "ed", "eo"):
            await self.ctx.books.require(book.id, user.id, Permission.EDIT_TRANSACTION)
            field = {"ec": "category", "ea": "amount", "ed": "description",
                     "eo": "occurred_on"}[action]
            await self.ctx.state.set(key, {"flow": "tx_edit", "book_id": str(book.id),
                                      "tx_id": str(tx.id), "field": field, "origin": origin})
            if field == "category":
                draft = await self.ctx.state.get(key)
                draft["recent"] = [row.name for row in await self.ctx.categories.list(book.id, user.id, tx.flow)]
                await self.ctx.state.set(key, draft)
                return screens.ask_category(tx.flow, draft["recent"])
            if field == "amount":
                return screens.ask_amount(
                    tx.category, self._foreign(tx, book),
                    current=screens.fmt(tx.original_amount, tx.original_currency),
                )
            if field == "occurred_on":
                return screens.ask_date(f"td:open:{tx.id}{origin and ':' + origin}")
            return screens.ask_description(editing=True)

        if action == "rcp":
            await self.ctx.state.set(key, {"flow": "receipt", "tx_id": str(tx.id),
                                       "book_id": str(book.id), "origin": origin})
            return screens.ask_receipt()

        if action == "rcpv":
            # The file lives on the provider; hand its id back so the adapter
            # can forward it without us ever holding the bytes.
            return await self._transaction_screen(book, tx, user, origin)

        if action == "rcpd":
            await self.ctx.ledger.attach_receipt(book.id, user.id, tx.id, None, None)
            fresh = await self.ctx.ledger.get_transaction(book.id, user.id, tx.id)
            return await self._transaction_screen(book, fresh, user, origin)

        if action == "del":
            return screens.confirm_delete(
                f"تراکنش «{tx.category}»", f"td:delok:{tx.id}{tail}", f"td:open:{tx.id}{tail}"
            )

        if action == "delok":
            on = tx.occurred_on
            await self.ctx.ledger.delete(book.id, user.id, tx.id)
            if origin:
                return await self._daily_screen(
                    user, on, str(book.id) if origin == "b" else "a", 0
                )
            return await self._tx_list(book, user)

        return await self._transaction_screen(book, tx, user, origin)

    @staticmethod
    def _foreign(tx, book):
        """The transaction's currency when it is not the book's, else None: the
        "original amount is in X" sentence is only true of foreign money."""
        return tx.original_currency if tx.original_currency != book.base_currency else None

    async def _transaction_screen(self, book, tx, user, origin=""):
        activity = (await self.ctx.ledger.activities(user.id, [tx]))[tx.id]
        text, buttons = screens.transaction_detail(book, tx, origin, activity)
        if tx.receipt_file_id:
            if tx.receipt_provider == self.ctx.provider.value:
                self.ctx.forward_file_id, self.ctx.forward_file_kind = tx.receipt_file_id, tx.receipt_kind
            else:
                text += "\n\nپیوست را در پیام‌رسانی که رسید را ثبت کرده‌ای مشاهده کن."
        return text, buttons

    async def _edit_tx_text(self, text, draft, user, key):
        field = draft["field"]
        value = text
        origin = draft.get("origin", "")
        if field == "amount":
            value, problem = read_amount(text or "")
            if problem:
                # Stay on this step: the old prompt is what the next line answers.
                tx = await self.ctx.ledger.get_transaction(
                    uuid.UUID(draft["book_id"]), user.id, uuid.UUID(draft["tx_id"])
                )
                book = await self.ctx.books.get_book(tx.book_id)
                return screens.ask_amount(
                    tx.category, self._foreign(tx, book), problem,
                    screens.fmt(tx.original_amount, tx.original_currency),
                )
        if field == "occurred_on":
            value = parse_date(text or "", self.ctx.today(user))
            if value is None:
                return screens.ask_date(
                    f"td:open:{draft['tx_id']}{origin and ':' + origin}", (text or "")[:30]
                )
        tx = await self.ctx.ledger.update(uuid.UUID(draft["book_id"]), user.id,
                                      uuid.UUID(draft["tx_id"]), **{field: value})
        await self.ctx.state.clear(key)
        book = await self.ctx.books.get_book(tx.book_id)
        return screens.with_notice("✅ ویرایش شد", await self._transaction_screen(book, tx, user, origin))

    # --------------------------------------------------------------- search
    async def _search_callback(self, action: str, argument: str, user, key: str):
        if action == "new":
            await self.ctx.state.set(key, {"flow": "search", "book_id": argument})
            return screens.ask_search()

        if action == "page":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "search" or not draft.get("query"):
                return screens.stale(None, user.display_name)
            return await self._search_screen(user, draft, int(argument))

        return screens.stale(None, user.display_name)

    async def _search_screen(self, user, draft: dict, page: int):
        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        rows, total, amount = await self.ctx.reports.search(
            book.id, user.id, draft["query"], page
        )
        return screens.search_results(book, draft["query"], rows, total, amount, page)

    async def quick_line(self, text: str, user, key: str):
        # Nothing in flight, so try to read the line as a transaction.
        entry = quick.read(text, self.ctx.today(user))
        if isinstance(entry, quick.Unclear):
            # Numbers were seen but none can be trusted as the amount: nothing
            # is recorded, and the person is told which ones were seen.
            return screens.unclear_line(entry.reason, entry.numbers)
        if entry is None:
            return screens.unreadable_line()

        books = await self.ctx.books.books_for_user(user.id)
        if not books:
            return screens.pick_book(books, "tx")

        pending = {
            "flow": "quick",
            "category": entry.category,
            "amount": str(entry.amount),
            "description": entry.description,
            "on": entry.on.isoformat() if entry.on else None,
            # Names this draft on its buttons; see _quick_callback.
            "nonce": secrets.token_hex(3),
        }
        await self.ctx.state.set(key, pending)

        if len(books) == 1:
            pending["book_id"] = str(books[0].id)
            await self.ctx.state.set(key, pending)
            return screens.quick_pick_flow(entry, pending["nonce"], books[0], self.ctx.today(user))

        return screens.quick_pick_book(entry, books, pending["nonce"], self.ctx.today(user))

    async def _daily_date_text(self, text: str, draft: dict, user, key: str):
        view = draft.get("view", "a")
        on = parse_date(text, self.ctx.today(user))
        if on is None:
            return screens.ask_date(
                f"dl:v:{screens.day_token(self.ctx.today(user))}:{view}:0", text[:30]
            )
        await self.ctx.state.clear(key)
        return await self._daily_screen(user, on, view, 0)

    async def _search_text(self, text: str, draft: dict, user, key: str):
        if len(text) < 2:
            return screens.ask_search("حداقل دو حرف بنویس.")
        draft["query"] = text[:60]
        await self.ctx.state.set(key, draft)
        return await self._search_screen(user, draft, 0)

    async def _quick_callback(self, action: str, argument: str, nonce: str, user, key: str):
        draft = await self.ctx.state.get(key)
        if draft.get("flow") != "quick" or draft.get("nonce", "") != nonce:
            # A draft made before nonces existed has none, and neither do its
            # buttons, so it keeps working until it is replaced.
            # The chat keeps every old message, so this button may belong to an
            # earlier line than the draft now waiting. Acting on whatever is
            # current would record the wrong thing; instead say it is old and
            # show what is actually waiting.
            return screens.stale(await self._quick_screen(draft, user), user.display_name)

        if action == "book":
            # Checked before the next screen names the book: a crafted button
            # must not be a way to read another account's book name.
            await self.ctx.books.require(uuid.UUID(argument), user.id, Permission.VIEW_TRANSACTIONS)
            draft["book_id"] = argument
            await self.ctx.state.set(key, draft)
            return await self._quick_screen(draft, user)

        if action == "flow":
            # Claimed before it is recorded: two taps in flight (webhook mode)
            # must not both see the draft. The loser gets the "old" answer.
            draft = await self.ctx.state.pop(key)
            if draft.get("flow") != "quick" or draft.get("nonce", "") != nonce:
                if draft:
                    await self.ctx.state.set(key, draft)
                return screens.stale(None, user.display_name)
            try:
                book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
                flow = Flow(argument)
                transaction = await self.ctx.ledger.record(
                    book_id=book.id,
                    actor_user_id=user.id,
                    flow=flow,
                    scope=SCOPE_FOR_BOOK.get(book.type, Scope.WORK),
                    category=draft["category"],
                    amount=Decimal(draft["amount"]),
                    description=draft.get("description"),
                    occurred_on=date.fromisoformat(draft["on"]) if draft.get("on") else None,
                )
            except Exception:
                # A refused record must not eat the draft: give it back.
                await self.ctx.state.set(key, draft)
                raise
            return screens.transaction_saved(
                book, flow, transaction.category,
                transaction.converted_amount, book.base_currency,
                transaction.occurred_on, transaction.description,
            )

        return screens.stale(None, user.display_name)

    async def _quick_screen(self, draft: dict, user):
        """The screen a quick draft is currently waiting on, or None."""
        if draft.get("flow") != "quick":
            return None
        entry = quick.QuickEntry(
            draft["category"], Decimal(draft["amount"]), draft.get("description"),
            date.fromisoformat(draft["on"]) if draft.get("on") else None,
        )
        if draft.get("book_id"):
            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            return screens.quick_pick_flow(entry, draft.get("nonce", ""), book, self.ctx.today(user))
        return screens.quick_pick_book(
            entry, await self.ctx.books.books_for_user(user.id), draft.get("nonce", ""),
            self.ctx.today(user),
        )

    async def _tx_text(self, text: str, draft: dict, user, key: str):
        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))

        if draft.get("awaiting") == "description":
            return await self._save_tx(draft, user, key, text)

        if draft.get("awaiting") == "rate":
            rate = parse_amount(text)
            if rate is None or rate <= Decimal("0"):
                return screens.ask_rate(
                    draft["currency"], book.base_currency,
                    f"«{text[:30]}» نرخ معتبر نیست؛ یک عدد بیشتر از صفر بنویس.",
                )
            draft["rate"] = str(rate)
            draft["awaiting"] = "description"
            await self.ctx.state.set(key, draft)
            return screens.ask_description()

        if draft.get("awaiting") == "date":
            on = parse_date(text, self.ctx.today(user))
            if on is None:
                return screens.ask_date("tx:new", text[:30])
            draft.pop("awaiting")
            draft["on"] = on.isoformat()
            await self.ctx.state.set(key, draft)
            return screens.pick_type(book, on)

        if not draft.get("direction"):
            on = date.fromisoformat(draft["on"]) if draft.get("on") else self.ctx.today(user)
            return screens.pick_type(book, on)

        if not draft.get("category"):
            try:
                draft["category"] = self.ctx.categories.name(text)
            except ValidationError:
                return screens.ask_category(
                    Flow(draft["direction"]), draft.get("recent") or [],
                    "نام دسته باید بین 1 تا 80 حرف باشد.",
                )
            await self.ctx.state.set(key, draft)
            return screens.ask_amount(draft["category"])

        # Refused here, with the reason and the same prompt, rather than let it
        # through to a ledger error that used to trap the person in this step.
        amount, problem = read_amount(text)
        if problem:
            return screens.ask_amount(draft["category"], problem=problem)

        draft["amount"] = str(amount)
        codes = await self.ctx.exchange.allowed(book.id)
        if len(codes) > 1:
            # Only asked where there is a choice. On a single-currency book the
            # question has one answer, and a tap that never varies is noise.
            draft["awaiting"] = "currency"
            await self.ctx.state.set(key, draft)
            balances = {
                b.code: b.amount
                for b in await self.ctx.exchange.balances(user.id, book.id)
            }
            return screens.pick_currency(codes, balances)

        draft["awaiting"] = "description"
        await self.ctx.state.set(key, draft)
        return screens.ask_description()

    async def _save_tx(self, draft, user, key, description=None, attachment=None):
        # Claimed before it is recorded, so a second tap in flight finds nothing
        # to record (webhook mode runs updates concurrently).
        draft = await self.ctx.state.pop(key)
        if draft.get("flow") != "tx" or draft.get("awaiting") != "description":
            if draft:
                # Somebody else's draft (another flow began in between) is not
                # ours to consume.
                await self.ctx.state.set(key, draft)
            return screens.stale(None, user.display_name)

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        flow = Flow(draft["direction"])
        try:
            transaction = await self.ctx.ledger.record(
                book_id=book.id,
                actor_user_id=user.id,
                flow=flow,
                scope=(Scope(draft["scope"]) if draft.get("scope")
                       else SCOPE_FOR_BOOK.get(book.type, Scope.WORK)),
                category=draft["category"],
                amount=Decimal(draft["amount"]),
                currency=draft.get("currency"),
                conversion_rate=Decimal(draft["rate"]) if draft.get("rate") else None,
                occurred_on=date.fromisoformat(draft["on"]) if draft.get("on") else None,
                description=description,
                receipt_file_id=attachment.file_id if attachment else None,
                receipt_provider=self.ctx.provider.value if attachment else None,
                receipt_kind=attachment.kind if attachment else None,
                receipt_file_name=attachment.file_name if attachment else None,
                receipt_mime_type=attachment.mime_type if attachment else None,
            )
        except Exception:
            # A refused record must not eat the draft: give it back.
            await self.ctx.state.set(key, draft)
            raise

        back = draft.get("back")
        if back:
            # The list comes back with the new line in it, which is a better
            # confirmation than a sentence saying so.
            return await self._daily_screen(
                user, date.fromisoformat(back["on"]), back["view"], 0
            )

        text, buttons = await self._transaction_screen(book, transaction, user)
        # The notice is joined with a blank line; it used to be glued onto the
        # card's first line because a trailing newline is not a line.
        saved = screens.with_notice("✅ تراکنش ثبت شد", (text, buttons))
        return saved[0], saved[1] + [[screens.Button("➕ ثبت بعدی", data="tx:new")]]
