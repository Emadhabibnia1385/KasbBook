"""One event in, one screen out.

This is the layer every messenger shares. It knows about books and transactions
because it calls the application services; it knows nothing about Telegram,
Bale or Rubika, because the adapter already turned their payload into an
`IncomingEvent` and will turn the reply back into their own format.

What a person can do lives in `bot/features/`, one module per area: a feature
declares the callback prefixes and draft flows it owns and is handed a `Context`
rather than this class. This module is what is left once those are taken out -
the savepoint around each update, the people who are not linked yet, the
commands, and the two dispatchers that hand a button or a typed line to the
feature that owns it.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.base import EventKind, IncomingEvent, OutgoingMessage
from ..modules.identity.models import Provider
from ..shared.errors import KasbBookError
from . import screens
from .features.base import CANCEL_WORDS, Context, index
from .features.account import AccountFeature
from .features.books import BooksFeature
from .features.payroll import PayrollFeature
from .features.planning import PlanningFeature
from .features.reports import ReportsFeature
from .features.transactions import TransactionsFeature
from .features.wallet import WalletFeature
from .state import StateStore, conversation_key

# Every feature of the bot, in one list. `index` refuses two that
# claim the same callback prefix or draft flow — at import, not at the first
# unlucky button press.
FEATURES: tuple = (
    AccountFeature,
    BooksFeature,
    PayrollFeature,
    PlanningFeature,
    ReportsFeature,
    TransactionsFeature,
    WalletFeature,
)
FEATURE_BY_PREFIX, FEATURE_BY_FLOW = index(FEATURES)


# Where a refusal offers to go back to, by the area of the button that failed.
# An area missing here keeps `screens.error`'s own fallback, the main menu.
#
# Two rules decide what may be listed, and both are about a refusal not making
# things worse:
#
# - The target names no book, category or entry. An id in the way back could
#   only come from the callback that just failed, and what failed is usually
#   that very id - a book this account may not see, an entry already gone - so
#   "back" would refuse a second time. It would leak, too: `books.require`
#   answers NotFound rather than PermissionDenied exactly so a stranger's book
#   cannot be told apart from one that never existed, and a button offered for
#   the one and not the other hands that difference straight back. Built from
#   the area alone, the screen is identical either way, which is the point.
# - The target is one of the main menu's own destinations. Home offers those to
#   every linked account unconditionally, which is the only evidence worth
#   having that the target renders for whoever just hit the refusal - and none
#   of them needs the work the savepoint has already rolled back.
#
# What is left is the areas rooted in the main menu. Everything that exists
# only inside a book - its categories, budgets, debts, loans, recurring rules,
# wallet and payroll, and the entry flow's own steps - has no parent that does
# not name the book, so it keeps the main menu. That is the narrow half of the
# bot on purpose: a second refusal, or a probe, costs more than a tap.
_PARENT_SCREEN = {
    "book": "book:list",
    # One area under four prefixes: rp, rb and rc all hang off the book picker
    # that `rep:menu` draws.
    "rep": "rep:menu",
    "rp": "rep:menu",
    "rb": "rep:menu",
    "rc": "rep:menu",
    "dl": "dl:v",
    "acc": "acc:panel",
    "rm": "rm:panel",
}

# The main menu's callbacks, as home itself offers them, so the second rule is
# checked rather than remembered. A target that falls out of the menu is
# dropped back to home instead of being trusted: the test suite pins the map,
# so the mistake is loud there and harmless here.
_HOME_DESTINATIONS = frozenset(
    button.data for row in screens.main_menu() for button in row if button.data
)


def _back_target(event: IncomingEvent) -> Optional[str]:
    """The screen a refusal offers to return to, or None for the main menu.

    A pure function of the callback's area: no draft is read and no id is
    carried, so the same area refuses the same way whatever was asked about.
    A typed line, a command or an attachment names no area and gets home.
    """
    if event.kind is not EventKind.CALLBACK:
        return None
    area = (event.callback_data or "").split(":")[0]
    back = _PARENT_SCREEN.get(area)
    return back if back in _HOME_DESTINATIONS else None


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
        self._features = [feature(self.ctx) for feature in FEATURES]
        # Held by name because the conversation hands it what no feature owns:
        # an attachment, and a typed line while no draft is waiting.
        self._transactions = next(
            f for f in self._features if isinstance(f, TransactionsFeature)
        )
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
            # Domain errors are answers, not crashes: the user sees why - and,
            # where the area they were in has a parent that cannot refuse in
            # turn, the way back to it rather than being dropped home with
            # whatever they were doing lost. See `_PARENT_SCREEN`.
            text, buttons = screens.error(
                screens.user_message(exc), _back_target(event)
            )

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
        await self.ctx.identity.observe_username(self.provider, event.identity.external_id, event.identity.username)
        user = await self.ctx.identity.user_for_identity(
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
            handled = await self._transactions.attachment(event, user, key)
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
            identity = await self.ctx.identity.complete_link_from_messenger(
                payload,
                self.provider,
                event.identity.external_id,
                external_username=event.identity.username,
                display_name=event.identity.display_name,
            )
            user = await self.ctx.identity.get_user(identity.user_id)
            return await self._home(user)

        user = await self.ctx.identity.create_account_from_messenger(
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

        feature = self._by_prefix.get(area)
        if feature is not None:
            return await feature.callback(area, parts, user, key, event)

        if area == "nav":
            await self.state.clear(key)
            if action == "cancel":
                return screens.cancelled(user.display_name)
            return await self._home(user)

        if area == "noop":
            # No screen emits this any more: a label that cannot act is a dead
            # end, so lists put the name on the button that does something. An
            # old message may still carry one, and it is told so rather than
            # silently sent home.
            return screens.stale(None, user.display_name)

        # An unknown area, deliberately the same answer as a retired one. The
        # two cannot be told apart from here, and from where the person sits
        # they are one event: a button that no longer does anything. Nearly
        # every one of these is a message older than the refactor that renamed
        # the prefix - which is what «قدیمی» already says - and the only other
        # source is hand-written data, which needs no explanation.
        return screens.stale(None, user.display_name)

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

        # Nothing in flight, so try to read the line as a transaction.
        return await self._transactions.quick_line(text, user, key)
