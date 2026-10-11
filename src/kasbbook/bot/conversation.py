"""One event in, one screen out.

This is the layer every messenger shares. It knows about books and transactions
because it calls the application services; it knows nothing about Telegram,
Bale or Rubika, because the adapter already turned their payload into an
`IncomingEvent` and will turn the reply back into their own format.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.base import EventKind, IncomingEvent, OutgoingFile, OutgoingMessage
from ..modules.books.models import Permission
from ..modules.identity.models import Provider
from ..modules.ledger.models import Flow, Scope
from ..modules.reports import service as reports_service
from ..shared.errors import KasbBookError, ValidationError
from ..shared.parsing import parse_amount, parse_date
from . import quick, screens
from .features.base import (
    CANCEL_WORDS, SCOPE_FOR_BOOK, Context, index,
    read_amount,
)
from .features.account import AccountFeature
from .features.books import BooksFeature
from .features.payroll import PayrollFeature
from .features.planning import PlanningFeature
from .features.wallet import WalletFeature
from .state import StateStore, conversation_key

# Every feature moved out of this file, in one list. `index` refuses two that
# claim the same callback prefix or draft flow — at import, not at the first
# unlucky button press.
FEATURES: tuple = (
    AccountFeature,
    BooksFeature,
    PayrollFeature,
    PlanningFeature,
    WalletFeature,
)
FEATURE_BY_PREFIX, FEATURE_BY_FLOW = index(FEATURES)

# The context's services, aliased onto the conversation for the handlers that
# have not moved into a feature yet. Shrinks to nothing as they move.
SERVICES = (
    "identity", "books", "ledger", "reports", "budgets", "debts", "loans",
    "recurring", "payroll", "treasury", "exchange", "categories", "invitations",
    "account_login",
)


class Conversation:
    """Handles one update for one person."""

    def __init__(
        self,
        session: AsyncSession,
        state: StateStore,
        provider: Provider,
        rates=None,
    ) -> None:
        self.ctx = Context(session, state, provider, rates)
        self.session = session
        self.state = state
        self.provider = provider
        self.rates = rates
        # The handlers not yet moved into a feature still read the services
        # off the conversation; they are the context's, shared, not copies.
        for name in SERVICES:
            setattr(self, name, getattr(self.ctx, name))
        self._features = [feature(self.ctx) for feature in FEATURES]
        self._by_prefix = {p: f for f in self._features for p in f.prefixes}
        self._by_flow = {name: f for f in self._features for name in f.flows}

    # ------------------------------------------------------------- entry
    async def handle(self, event: IncomingEvent) -> OutgoingMessage:
        self.ctx.reset_outbox()
        key = conversation_key(self.provider.value, event.identity.external_id)

        try:
            # A savepoint around this update's work, so a refusal undoes exactly
            # that work. The caller commits after an answer, and whatever a
            # service had flushed before it refused would otherwise be kept
            # behind a message saying nothing was done.
            async with self.session.begin_nested():
                text, buttons = await self._route(event, key)
        except KasbBookError as exc:
            # Domain errors are answers, not crashes: the user sees why.
            text, buttons = screens.error(screens.user_message(exc))

        return OutgoingMessage(
            chat_id=event.chat_id,
            text=text,
            buttons=buttons,
            document=self.ctx.pending_file,
            forward_file_id=self.ctx.forward_file_id,
            forward_file_kind=self.ctx.forward_file_kind,
            hidden=self.ctx.hidden,
            notifications=self.ctx.notifications,
            # Editing the screen in place is what keeps the chat a panel rather
            # than a transcript; the adapter falls back to a new message if the
            # anchor is gone.
            edit_message_id=event.message_id if event.kind is EventKind.CALLBACK else None,
        )

    async def _route(self, event: IncomingEvent, key: str):
        await self.identity.observe_username(self.provider, event.identity.external_id, event.identity.username)
        user = await self.identity.user_for_identity(
            self.provider, event.identity.external_id
        )

        if user is None:
            return await self._unlinked(event, key)

        if event.kind is EventKind.COMMAND:
            return await self._command(event, user, key)
        if event.kind is EventKind.CALLBACK:
            return await self._callback(event, user, key)
        if event.kind is EventKind.ATTACHMENT or (
            event.attachment is not None and event.kind is EventKind.MESSAGE
        ):
            handled = await self._attachment(event, user, key)
            if handled is not None:
                return handled

        if event.kind is EventKind.MESSAGE and event.text:
            return await self._text(event, user, key)

        return screens.welcome(user.display_name)

    # -------------------------------------------------------- not linked yet
    async def _unlinked(self, event: IncomingEvent, key: str):
        """Nobody owns this messenger account yet."""
        payload = (event.args or "").strip()

        # A deep link from the web panel carries a token that names the account.
        if event.kind is EventKind.COMMAND and event.command == "start" and payload:
            identity = await self.identity.complete_link_from_messenger(
                payload,
                self.provider,
                event.identity.external_id,
                external_username=event.identity.username,
                display_name=event.identity.display_name,
            )
            user = await self.identity.get_user(identity.user_id)
            return await self._home(user)

        user = await self.identity.create_account_from_messenger(
            self.provider,
            event.identity.external_id,
            display_name=event.identity.display_name,
            external_username=event.identity.username,
        )
        return await self._home(user)

    # ------------------------------------------------------------ commands
    async def _command(self, event: IncomingEvent, user, key: str):
        if event.command == "cancel":
            await self.state.clear(key)
            return screens.cancelled(user.display_name)
        # /start on an already-linked account is just "go home".
        await self.state.clear(key)
        return await self._home(user)

    async def _home(self, user):
        return await self.ctx.home(user)

    # ----------------------------------------------------------- callbacks
    async def _callback(self, event: IncomingEvent, user, key: str):
        parts = (event.callback_data or "").split(":")
        area = parts[0] if parts else ""
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""

        feature = self._by_prefix.get(area)
        if feature is not None:
            return await feature.callback(area, parts, user, key, event)

        if area == "nav":
            await self.state.clear(key)
            if action == "cancel":
                return screens.cancelled(user.display_name)
            return await self._home(user)

        if area == "tx":
            return await self._tx_callback(action, argument, user, key)

        if area == "dl":
            return await self._daily_callback(parts, user, key)

        if area == "rep":
            return await self._report_callback(action, argument, user)

        if area in ("rp", "rb", "rc"):
            return await self._period_screen(parts, user, area)

        if area == "qk":
            nonce = parts[3] if len(parts) > 3 else ""
            return await self._quick_callback(action, argument, nonce, user, key)

        if area == "td":
            return await self._tx_detail_callback(action, argument, user, key, event)

        if area == "sr":
            return await self._search_callback(action, argument, user, key)

        if area == "noop":
            # No screen emits this any more: a label that cannot act is a dead
            # end, so lists put the name on the button that does something. An
            # old message may still carry one, and it is told so rather than
            # silently sent home.
            return screens.stale(None, user.display_name)

        return screens.stale(None, user.display_name)

    async def _tx_callback(self, action: str, argument: str, user, key: str):
        if action == "skip":
            draft = await self.state.get(key)
            if draft.get("flow") == "tx" and draft.get("awaiting") == "description":
                return await self._save_tx(draft, user, key)
            # Nothing to skip: the entry was recorded already (a double tap) or
            # this button belongs to an old message.
            return screens.stale(None, user.display_name)
        if action == "new":
            await self.state.clear(key)
            return screens.tx_home(self._today(user))

        if action == "one":
            await self.state.clear(key)
            books = await self.books.books_for_user(user.id)
            if len(books) == 1:
                return await self._start_single(books[0], user, key)
            return screens.pick_book(books, "tx")

        if action == "book":
            book = await self.books.get_book(uuid.UUID(argument))
            return await self._start_single(book, user, key)

        if action == "on":
            draft = await self.state.get(key)
            if not draft.get("book_id"):
                return screens.tx_home(self._today(user))
            book = await self.books.get_book(uuid.UUID(draft["book_id"]))

            if argument == "ask":
                draft["awaiting"] = "date"
                await self.state.set(key, draft)
                return screens.ask_date("tx:new")

            draft["on"] = self._today(user).isoformat()
            await self.state.set(key, draft)
            return screens.pick_type(book, self._today(user))

        if action == "type":
            entry = screens.ENTRY_TYPES.get(argument)
            draft = await self.state.get(key)
            if entry is None or not draft.get("book_id"):
                return screens.tx_home(self._today(user))

            draft["direction"] = entry[0].value
            draft["scope"] = entry[1].value
            return await self._ask_category(draft, user, key)

        if action == "flow":
            # Buttons from before the date and type steps existed may still be
            # on somebody's screen. They keep working: the book's own scope,
            # and a date left for record() to fill in with the book's today.
            draft = await self.state.get(key)
            if not draft.get("book_id"):
                return screens.pick_book(await self.books.books_for_user(user.id), "tx")

            draft["direction"] = argument
            return await self._ask_category(draft, user, key)

        if action == "cur":
            draft = await self.state.get(key)
            if draft.get("awaiting") != "currency" or not draft.get("book_id"):
                return screens.stale(None, user.display_name)

            book = await self.books.get_book(uuid.UUID(draft["book_id"]))
            if argument not in await self.exchange.allowed(book.id):
                return screens.error("این ارز برای این دفتر فعال نیست.")

            draft["currency"] = argument
            if argument == book.base_currency:
                draft.pop("rate", None)
                draft["awaiting"] = "description"
                await self.state.set(key, draft)
                return screens.ask_description()

            live = await self.exchange.quote(argument, book.base_currency)
            if live is not None:
                # Today's market price, applied so the person does not have to
                # type it. It is shown rather than hidden, and overridable,
                # because an OTC deal is often not the market price.
                draft["rate"] = str(live)
                draft["awaiting"] = "description"
                await self.state.set(key, draft)
                return screens.ask_description_with_rate(
                    argument, live, book.base_currency,
                    Decimal(draft["amount"]) * live,
                )

            draft["awaiting"] = "rate"
            await self.state.set(key, draft)
            return screens.ask_rate(argument, book.base_currency)

        if action == "rate":
            draft = await self.state.get(key)
            if not draft.get("currency") or not draft.get("book_id"):
                return screens.stale(None, user.display_name)
            book = await self.books.get_book(uuid.UUID(draft["book_id"]))
            draft["awaiting"] = "rate"
            await self.state.set(key, draft)
            return screens.ask_rate(draft["currency"], book.base_currency)

        if action == "cat":
            draft = await self.state.get(key)
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
            await self.state.set(key, draft)
            return screens.ask_amount(draft["category"])

        return screens.tx_home(self._today(user))

    def _today(self, user) -> date:
        return self.ctx.today(user)

    @staticmethod
    def _day_from_token(token: str, fallback: date) -> date:
        try:
            return datetime.strptime(token, "%Y%m%d").date()
        except (ValueError, TypeError):
            return fallback

    async def _start_single(self, book, user, key: str):
        # Checked before anything is drawn: the next screen names the book, and
        # a crafted button should not be a way to learn another book's name.
        await self.books.require(book.id, user.id, Permission.VIEW_TRANSACTIONS)
        await self.state.set(key, {"flow": "tx", "book_id": str(book.id)})
        return screens.pick_date(book, self._today(user))

    async def _ask_category(self, draft: dict, user, key: str):
        flow = Flow(draft["direction"])
        # Kept in the draft so a press can name one by position. The callback
        # payload has sixty-four bytes; a Persian category does not reliably
        # fit, and a button that overflows it fails silently.
        recent = [row.name for row in await self.categories.list(uuid.UUID(draft["book_id"]), user.id, flow)]
        draft["recent"] = recent
        await self.state.set(key, draft)
        return screens.ask_category(flow, recent)

    async def _daily_callback(self, parts, user, key: str):
        """dl:v shows a day, dl:go asks for one, dl:ab and dl:add record into one."""
        action = parts[1] if len(parts) > 1 else ""
        today = self._today(user)
        on = self._day_from_token(parts[2] if len(parts) > 2 else "", today)

        if action == "v":
            view = parts[3] if len(parts) > 3 else "a"
            page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
            await self.state.clear(key)
            return await self._daily_screen(user, on, view, page)

        if action == "go":
            view = parts[2] if len(parts) > 2 else "a"
            await self.state.set(key, {"flow": "daily_date", "view": view})
            return screens.ask_date(f"dl:v:{screens.day_token(today)}:{view}:0")

        if action == "ab" and len(parts) > 3:
            book = await self.books.get_book(uuid.UUID(parts[3]))
            await self.books.require(book.id, user.id, Permission.VIEW_TRANSACTIONS)
            return screens.daily_pick_type(book, on)

        if action == "add" and len(parts) > 4:
            book = await self.books.get_book(uuid.UUID(parts[3]))
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
        books = await self.books.books_for_user(user.id)
        if not books:
            return screens.pick_book(books, "tx")

        book_id = None
        if view and view != "a":
            try:
                book_id = uuid.UUID(view)
            except ValueError:
                book_id = None

        sheets = await self.reports.day(user.id, on, book_id)
        return screens.daily_view(on, self._today(user), sheets, books, book_id, page)

    async def _report_callback(self, action: str, argument: str, user):
        if action == "book":
            book = await self.books.get_book(uuid.UUID(argument))
            years = await self.reports.years_with_data(book.id, user.id)
            return screens.period_menu(book, years, self._today(user))

        return screens.report_menu(await self.books.books_for_user(user.id))

    async def _period_screen(self, parts, user, kind: str):
        """rp / rb / rc all name a book and a period the same way."""
        book = await self.books.get_book(uuid.UUID(parts[1]))
        spec = ":".join(parts[2:])
        period = reports_service.parse_spec(spec)
        if period is None:
            years = await self.reports.years_with_data(book.id, user.id)
            return screens.period_menu(book, years, self._today(user))

        if kind == "rb":
            buckets = await self.reports.by_category(book.id, user.id, period)
            return screens.category_breakdown(book, period.label, buckets, spec)

        if kind == "rc":
            payload = await self.reports.to_csv(book.id, user.id, period)
            self.ctx.pending_file = OutgoingFile(
                content=payload,
                filename="kasbbook-" + spec.replace(":", "-") + ".csv",
                caption="خروجی " + period.label,
            )
            summary = await self.reports.summary(book.id, user.id, period)
            return screens.period_report(book, period.label, summary, spec)

        summary = await self.reports.summary(book.id, user.id, period)
        comparison = None
        compared = await self.reports.compare(book.id, user.id, period)
        if compared is not None:
            previous, before, after = compared
            comparison = screens.comparison_line(previous.label, before, after)

        return screens.period_report(book, period.label, summary, spec, comparison)

    async def _attachment(self, event: IncomingEvent, user, key: str):
        """A file only means something while a receipt is being asked for."""
        draft = await self.state.get(key)
        if draft.get("flow") == "tx" and draft.get("awaiting") == "description":
            return await self._save_tx(draft, user, key, event.text, event.attachment)
        if draft.get("flow") != "receipt" or event.attachment is None:
            return None

        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        await self.ledger.attach_receipt(
            book.id, user.id, uuid.UUID(draft["tx_id"]),
            event.attachment.file_id, self.provider.value,
            kind=event.attachment.kind,
            file_name=event.attachment.file_name,
            mime_type=event.attachment.mime_type,
        )
        await self.state.clear(key)

        tx = await self.ledger.get_transaction(
            book.id, user.id, uuid.UUID(draft["tx_id"])
        )
        return await self._transaction_screen(book, tx, user, draft.get("origin", ""))

    # -------------------------------------------------- transactions & receipts
    TX_PAGE = 8

    async def _tx_list(self, book, user, page: int = 0):
        rows = await self.ledger.transactions(book.id, user.id)
        start = max(0, page) * self.TX_PAGE
        return screens.transaction_list(
            book, rows[start:start + self.TX_PAGE], page, len(rows), self.TX_PAGE
        )

    async def _tx_and_book(self, user, transaction_id: uuid.UUID):
        for book in await self.books.books_for_user(user.id):
            try:
                tx = await self.ledger.get_transaction(book.id, user.id, transaction_id)
            except KasbBookError:
                continue
            return book, tx
        return None, None

    async def _tx_detail_callback(self, action: str, argument: str, user, key: str, event):
        if action == "clear_description":
            draft = await self.state.get(key)
            if draft.get("flow") != "tx_edit" or draft.get("field") != "description":
                return screens.stale(None, user.display_name)
            return await self._edit_tx_text(None, draft, user, key)
        parts = (event.callback_data or "").split(":")

        if action == "list":
            book = await self.books.get_book(uuid.UUID(argument))
            return await self._tx_list(book, user)

        if action == "page":
            book = await self.books.get_book(uuid.UUID(parts[2]))
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
            await self.books.require(book.id, user.id, Permission.EDIT_TRANSACTION)
            field = {"ec": "category", "ea": "amount", "ed": "description",
                     "eo": "occurred_on"}[action]
            await self.state.set(key, {"flow": "tx_edit", "book_id": str(book.id),
                                      "tx_id": str(tx.id), "field": field, "origin": origin})
            if field == "category":
                draft = await self.state.get(key)
                draft["recent"] = [row.name for row in await self.categories.list(book.id, user.id, tx.flow)]
                await self.state.set(key, draft)
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
            await self.state.set(key, {"flow": "receipt", "tx_id": str(tx.id),
                                       "book_id": str(book.id), "origin": origin})
            return screens.ask_receipt()

        if action == "rcpv":
            # The file lives on the provider; hand its id back so the adapter
            # can forward it without us ever holding the bytes.
            return await self._transaction_screen(book, tx, user, origin)

        if action == "rcpd":
            await self.ledger.attach_receipt(book.id, user.id, tx.id, None, None)
            fresh = await self.ledger.get_transaction(book.id, user.id, tx.id)
            return await self._transaction_screen(book, fresh, user, origin)

        if action == "del":
            return screens.confirm_delete(
                f"تراکنش «{tx.category}»", f"td:delok:{tx.id}{tail}", f"td:open:{tx.id}{tail}"
            )

        if action == "delok":
            on = tx.occurred_on
            await self.ledger.delete(book.id, user.id, tx.id)
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
        activity = (await self.ledger.activities(user.id, [tx]))[tx.id]
        text, buttons = screens.transaction_detail(book, tx, origin, activity)
        if tx.receipt_file_id:
            if tx.receipt_provider == self.provider.value:
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
                tx = await self.ledger.get_transaction(
                    uuid.UUID(draft["book_id"]), user.id, uuid.UUID(draft["tx_id"])
                )
                book = await self.books.get_book(tx.book_id)
                return screens.ask_amount(
                    tx.category, self._foreign(tx, book), problem,
                    screens.fmt(tx.original_amount, tx.original_currency),
                )
        if field == "occurred_on":
            value = parse_date(text or "", self._today(user))
            if value is None:
                return screens.ask_date(
                    f"td:open:{draft['tx_id']}{origin and ':' + origin}", (text or "")[:30]
                )
        tx = await self.ledger.update(uuid.UUID(draft["book_id"]), user.id,
                                      uuid.UUID(draft["tx_id"]), **{field: value})
        await self.state.clear(key)
        book = await self.books.get_book(tx.book_id)
        return screens.with_notice("✅ ویرایش شد", await self._transaction_screen(book, tx, user, origin))

    # --------------------------------------------------------------- search
    async def _search_callback(self, action: str, argument: str, user, key: str):
        if action == "new":
            await self.state.set(key, {"flow": "search", "book_id": argument})
            return screens.ask_search()

        if action == "page":
            draft = await self.state.get(key)
            if draft.get("flow") != "search" or not draft.get("query"):
                return screens.stale(None, user.display_name)
            return await self._search_screen(user, draft, int(argument))

        return screens.stale(None, user.display_name)

    async def _search_screen(self, user, draft: dict, page: int):
        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        rows, total, amount = await self.reports.search(
            book.id, user.id, draft["query"], page
        )
        return screens.search_results(book, draft["query"], rows, total, amount, page)

    # ----------------------------------------------------------- payroll
    async def _member_names(self, book_id) -> dict:
        return await self.ctx.member_names(book_id)

    # ----------------------------------------------------- free text steps
    async def _text(self, event: IncomingEvent, user, key: str):
        draft = await self.state.get(key)
        text = (event.text or "").strip()

        # The word means cancel wherever a line is being waited for. Without
        # this it was taken as the answer: a book named «انصراف», or the next
        # line swallowed as a name. Checked here, once, not in every flow.
        if draft.get("flow") and text in CANCEL_WORDS:
            await self.state.clear(key)
            return screens.cancelled(user.display_name)

        feature = self._by_flow.get(draft.get("flow"))
        if feature is not None:
            return await feature.text(text, draft, user, key, event)

        if draft.get("flow") == "tx_edit":
            return await self._edit_tx_text(text, draft, user, key)

        if draft.get("flow") == "tx":
            return await self._tx_text(text, draft, user, key)

        if draft.get("flow") == "daily_date":
            view = draft.get("view", "a")
            on = parse_date(text, self._today(user))
            if on is None:
                return screens.ask_date(
                    f"dl:v:{screens.day_token(self._today(user))}:{view}:0", text[:30]
                )
            await self.state.clear(key)
            return await self._daily_screen(user, on, view, 0)

        if draft.get("flow") == "search":
            if len(text) < 2:
                return screens.ask_search("حداقل دو حرف بنویس.")
            draft["query"] = text[:60]
            await self.state.set(key, draft)
            return await self._search_screen(user, draft, 0)

        # Nothing in flight, so try to read the line as a transaction.
        entry = quick.read(text, self._today(user))
        if isinstance(entry, quick.Unclear):
            # Numbers were seen but none can be trusted as the amount: nothing
            # is recorded, and the person is told which ones were seen.
            return screens.unclear_line(entry.reason, entry.numbers)
        if entry is None:
            return screens.unreadable_line()

        books = await self.books.books_for_user(user.id)
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
        await self.state.set(key, pending)

        if len(books) == 1:
            pending["book_id"] = str(books[0].id)
            await self.state.set(key, pending)
            return screens.quick_pick_flow(entry, pending["nonce"], books[0], self._today(user))

        return screens.quick_pick_book(entry, books, pending["nonce"], self._today(user))

    async def _quick_callback(self, action: str, argument: str, nonce: str, user, key: str):
        draft = await self.state.get(key)
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
            await self.books.require(uuid.UUID(argument), user.id, Permission.VIEW_TRANSACTIONS)
            draft["book_id"] = argument
            await self.state.set(key, draft)
            return await self._quick_screen(draft, user)

        if action == "flow":
            # Claimed before it is recorded: two taps in flight (webhook mode)
            # must not both see the draft. The loser gets the "old" answer.
            draft = await self.state.pop(key)
            if draft.get("flow") != "quick" or draft.get("nonce", "") != nonce:
                if draft:
                    await self.state.set(key, draft)
                return screens.stale(None, user.display_name)
            try:
                book = await self.books.get_book(uuid.UUID(draft["book_id"]))
                flow = Flow(argument)
                transaction = await self.ledger.record(
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
                await self.state.set(key, draft)
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
            book = await self.books.get_book(uuid.UUID(draft["book_id"]))
            return screens.quick_pick_flow(entry, draft.get("nonce", ""), book, self._today(user))
        return screens.quick_pick_book(
            entry, await self.books.books_for_user(user.id), draft.get("nonce", ""),
            self._today(user),
        )

    async def _tx_text(self, text: str, draft: dict, user, key: str):
        book = await self.books.get_book(uuid.UUID(draft["book_id"]))

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
            await self.state.set(key, draft)
            return screens.ask_description()

        if draft.get("awaiting") == "date":
            on = parse_date(text, self._today(user))
            if on is None:
                return screens.ask_date("tx:new", text[:30])
            draft.pop("awaiting")
            draft["on"] = on.isoformat()
            await self.state.set(key, draft)
            return screens.pick_type(book, on)

        if not draft.get("direction"):
            on = date.fromisoformat(draft["on"]) if draft.get("on") else self._today(user)
            return screens.pick_type(book, on)

        if not draft.get("category"):
            try:
                draft["category"] = self.categories.name(text)
            except ValidationError:
                return screens.ask_category(
                    Flow(draft["direction"]), draft.get("recent") or [],
                    "نام دسته باید بین 1 تا 80 حرف باشد.",
                )
            await self.state.set(key, draft)
            return screens.ask_amount(draft["category"])

        # Refused here, with the reason and the same prompt, rather than let it
        # through to a ledger error that used to trap the person in this step.
        amount, problem = read_amount(text)
        if problem:
            return screens.ask_amount(draft["category"], problem=problem)

        draft["amount"] = str(amount)
        codes = await self.exchange.allowed(book.id)
        if len(codes) > 1:
            # Only asked where there is a choice. On a single-currency book the
            # question has one answer, and a tap that never varies is noise.
            draft["awaiting"] = "currency"
            await self.state.set(key, draft)
            balances = {
                b.code: b.amount
                for b in await self.exchange.balances(user.id, book.id)
            }
            return screens.pick_currency(codes, balances)

        draft["awaiting"] = "description"
        await self.state.set(key, draft)
        return screens.ask_description()

    async def _save_tx(self, draft, user, key, description=None, attachment=None):
        # Claimed before it is recorded, so a second tap in flight finds nothing
        # to record (webhook mode runs updates concurrently).
        draft = await self.state.pop(key)
        if draft.get("flow") != "tx" or draft.get("awaiting") != "description":
            if draft:
                # Somebody else's draft (another flow began in between) is not
                # ours to consume.
                await self.state.set(key, draft)
            return screens.stale(None, user.display_name)

        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        flow = Flow(draft["direction"])
        try:
            transaction = await self.ledger.record(
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
                receipt_provider=self.provider.value if attachment else None,
                receipt_kind=attachment.kind if attachment else None,
                receipt_file_name=attachment.file_name if attachment else None,
                receipt_mime_type=attachment.mime_type if attachment else None,
            )
        except Exception:
            # A refused record must not eat the draft: give it back.
            await self.state.set(key, draft)
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

