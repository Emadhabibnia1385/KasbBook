"""One event in, one screen out.

This is the layer every messenger shares. It knows about books and transactions
because it calls the application services; it knows nothing about Telegram,
Bale or Rubika, because the adapter already turned their payload into an
`IncomingEvent` and will turn the reply back into their own format.
"""

from __future__ import annotations

import uuid
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.base import EventKind, IncomingEvent, OutgoingMessage
from ..modules.books.models import BookType
from ..modules.books.service import BookService
from ..modules.identity.models import Provider
from ..modules.identity.service import IdentityService
from ..modules.ledger.models import Flow, Scope
from ..modules.ledger.service import LedgerService
from ..shared.errors import KasbBookError
from ..shared.parsing import parse_amount
from . import screens
from .state import DEFAULT_TTL_SECONDS, StateStore, conversation_key

# Which book type a scope belongs to, so a team book never records personal money.
SCOPE_FOR_BOOK = {
    BookType.PERSONAL: Scope.PERSONAL,
    BookType.BUSINESS: Scope.WORK,
    BookType.TEAM: Scope.TEAM,
    BookType.ORGANIZATION: Scope.TEAM,
}


class Conversation:
    """Handles one update for one person."""

    def __init__(
        self,
        session: AsyncSession,
        state: StateStore,
        provider: Provider,
    ) -> None:
        self.session = session
        self.state = state
        self.provider = provider
        self.identity = IdentityService(session)
        self.books = BookService(session)
        self.ledger = LedgerService(session)

    # ------------------------------------------------------------- entry
    async def handle(self, event: IncomingEvent) -> OutgoingMessage:
        key = conversation_key(self.provider.value, event.identity.external_id)

        try:
            text, buttons = await self._route(event, key)
        except KasbBookError as exc:
            # Domain errors are answers, not crashes: the user sees why.
            text, buttons = screens.error(str(exc))

        return OutgoingMessage(
            chat_id=event.chat_id,
            text=text,
            buttons=buttons,
            # Editing the screen in place is what keeps the chat a panel rather
            # than a transcript; the adapter falls back to a new message if the
            # anchor is gone.
            edit_message_id=event.message_id if event.kind is EventKind.CALLBACK else None,
        )

    async def _route(self, event: IncomingEvent, key: str):
        user = await self.identity.user_for_identity(
            self.provider, event.identity.external_id
        )

        if user is None:
            return await self._unlinked(event, key)

        if event.kind is EventKind.COMMAND:
            return await self._command(event, user, key)
        if event.kind is EventKind.CALLBACK:
            return await self._callback(event, user, key)
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
            return screens.welcome(user.display_name)

        if event.kind is EventKind.CALLBACK and event.callback_data == "acc:create":
            user = await self.identity.create_user(
                event.identity.display_name or "کاربر تازه"
            )
            await self.identity._attach(
                user_id=user.id,
                provider=self.provider,
                external_id=event.identity.external_id,
                external_username=event.identity.username,
                display_name=event.identity.display_name,
            )
            return screens.welcome(user.display_name)

        issued = await self.identity.start_link_from_messenger(
            self.provider,
            event.identity.external_id,
            external_username=event.identity.username,
        )
        return screens.not_linked(issued.token)

    # ------------------------------------------------------------ commands
    async def _command(self, event: IncomingEvent, user, key: str):
        if event.command == "cancel":
            await self.state.clear(key)
            return screens.welcome(user.display_name)
        # /start on an already-linked account is just "go home".
        await self.state.clear(key)
        return screens.welcome(user.display_name)

    # ----------------------------------------------------------- callbacks
    async def _callback(self, event: IncomingEvent, user, key: str):
        parts = (event.callback_data or "").split(":")
        area = parts[0] if parts else ""
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""

        if area == "nav":
            await self.state.clear(key)
            return screens.welcome(user.display_name)

        if area == "book":
            return await self._book_callback(action, argument, user, key)

        if area == "tx":
            return await self._tx_callback(action, argument, user, key)

        if area == "rep":
            return await self._report_callback(action, argument, user)

        if area == "acc":
            if action == "newcode":
                issued = await self.identity.start_link_from_messenger(
                    self.provider, event.identity.external_id
                )
                return screens.not_linked(issued.token)
            identities = await self.identity.list_identities(user.id)
            return screens.identity_list(identities, self.provider)

        return screens.welcome(user.display_name)

    async def _book_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            return screens.book_list(await self.books.books_for_user(user.id))

        if action == "new":
            return screens.new_book_type()

        if action == "type":
            book_type = BookType(argument)
            await self.state.set(
                key, {"flow": "new_book", "type": book_type.value}, DEFAULT_TTL_SECONDS
            )
            return screens.ask_book_name(book_type)

        if action == "open":
            book = await self.books.get_book(uuid.UUID(argument))
            totals = await self.ledger.totals(book.id, user.id)
            return screens.book_report(book, totals)

        return screens.book_list(await self.books.books_for_user(user.id))

    async def _tx_callback(self, action: str, argument: str, user, key: str):
        if action == "new":
            await self.state.clear(key)
            return screens.pick_book(await self.books.books_for_user(user.id), "tx")

        if action == "book":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.set(key, {"flow": "tx", "book_id": str(book.id)})
            return screens.pick_flow(book)

        if action == "flow":
            draft = await self.state.get(key)
            if not draft.get("book_id"):
                return screens.pick_book(await self.books.books_for_user(user.id), "tx")

            draft["direction"] = argument
            await self.state.set(key, draft)
            return screens.ask_category(Flow(argument))

        return screens.pick_book(await self.books.books_for_user(user.id), "tx")

    async def _report_callback(self, action: str, argument: str, user):
        if action == "book":
            book = await self.books.get_book(uuid.UUID(argument))
            totals = await self.ledger.totals(book.id, user.id)
            return screens.book_report(book, totals)

        return screens.report_menu(await self.books.books_for_user(user.id))

    # ----------------------------------------------------- free text steps
    async def _text(self, event: IncomingEvent, user, key: str):
        draft = await self.state.get(key)
        text = (event.text or "").strip()

        if draft.get("flow") == "new_book":
            book = await self.books.create_book(
                user.id, text, BookType(draft["type"])
            )
            await self.state.clear(key)
            return screens.book_list(await self.books.books_for_user(user.id))

        if draft.get("flow") == "tx":
            return await self._tx_text(text, draft, user, key)

        # Nothing in flight: treat it as a menu request rather than guessing.
        return screens.welcome(user.display_name)

    async def _tx_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("direction"):
            book = await self.books.get_book(uuid.UUID(draft["book_id"]))
            return screens.pick_flow(book)

        if not draft.get("category"):
            draft["category"] = text[:80]
            await self.state.set(key, draft)
            return screens.ask_amount(draft["category"])

        amount = parse_amount(text)
        if amount is None:
            return screens.ask_amount(draft["category"])

        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        flow = Flow(draft["direction"])

        transaction = await self.ledger.record(
            book_id=book.id,
            actor_user_id=user.id,
            flow=flow,
            scope=SCOPE_FOR_BOOK.get(book.type, Scope.WORK),
            category=draft["category"],
            amount=amount,
        )
        await self.state.clear(key)
        return screens.transaction_saved(
            book, flow, transaction.category,
            transaction.converted_amount, book.base_currency,
        )
