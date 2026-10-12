"""What a feature of the bot is given, and what it promises in return.

The bot used to be one class of two and a half thousand lines: every flow could
reach every other flow's private helpers, and a callback prefix was owned by
whichever `if area ==` branch came first. A feature now declares what it owns —
its callback prefixes and the draft flows it reads typed text for — and gets a
`Context`, not the conversation. Dependencies run one way: the conversation
knows the features; a feature knows only the context and the services.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ...adapters.base import IncomingEvent, OutgoingFile, OutgoingMessage
from ...modules.books.invitations import InvitationService
from ...modules.books.service import BookService
from ...modules.budgets.service import BudgetService
from ...modules.debts.service import DebtService
from ...modules.exchange.service import ExchangeService
from ...modules.identity.login import AccountLoginService
from ...modules.identity.models import Provider, User
from ...modules.identity.service import IdentityService
from ...modules.ledger.categories import CategoryService
from ...modules.ledger.service import LedgerService
from ...modules.loans.service import LoanService
from ...modules.payroll.service import PayrollService
from ...modules.recurring.service import RecurringService
from ...modules.reports.service import ReportService
from ...modules.treasury.service import TreasuryService
from decimal import Decimal

from ...shared import jalali
from .. import quick, screens
from ..state import StateStore

Screen = Tuple[str, list]

# What a person types to back out of a half-finished flow. The button's label
# is included because some people type exactly what they see.
CANCEL_WORDS = ("انصراف", "لغو", "↩️ انصراف", "⬅️ انصراف")

# What fits on a button next to its emoji. Longer names stay readable in the
# list text but would be cut mid-word on the button that opens the book.
BOOK_NAME_LIMIT = 40

# What a person types when a due date does not apply.
NO_DUE_WORDS = ("ندارد", "ندارم", "بدون سررسید", "-")


def read_amount(text: str):
    """(amount, None) or (None, why): the answer to every "how much?" prompt.

    One reader for every prompt, so «۳۰ هزار و ۵۰۰» means the same thing in a
    quick line, a budget and a loan, and a refusal always says why: not a
    number, zero, or written in a way that could mean two different sums.
    """
    got = quick.read_amount(text)
    if isinstance(got, quick.Unclear):
        return None, screens.unclear_reason(got.reason, got.numbers)
    if got is None:
        typed = (text or "").strip()
        if typed[:1] in ("-", "−") and isinstance(quick.read_amount(typed[1:]), Decimal):
            return None, "مبلغ منفی نمی‌شود؛ بدون علامت منفی بنویس. برای برداشت، نوع «هزینه» را بزن."
        return None, f"«{typed[:30]}» مبلغ نیست. فقط عدد بنویس؛ مثلاً 250000 یا 250ک."
    if got <= 0:
        return None, "مبلغ باید بیشتر از صفر باشد."
    return got, None



class Context:
    """One update's services, its outbox, and the helpers every feature shares.

    The outbox is what a handler hands back besides a screen — a file, a
    forwarded receipt, a concealed secret, messages for other people — reset
    for every update by the conversation.
    """

    def __init__(
        self, session: AsyncSession, state: StateStore, provider: Provider, rates=None
    ) -> None:
        self.session = session
        self.state = state
        self.provider = provider
        self.rates = rates
        self.identity = IdentityService(session)
        self.books = BookService(session)
        self.ledger = LedgerService(session)
        self.reports = ReportService(session)
        self.budgets = BudgetService(session)
        self.debts = DebtService(session)
        self.loans = LoanService(session)
        self.recurring = RecurringService(session)
        self.payroll = PayrollService(session)
        self.treasury = TreasuryService(session)
        self.exchange = ExchangeService(session, rates=rates)
        self.categories = CategoryService(session)
        self.invitations = InvitationService(session)
        self.account_login = AccountLoginService(session)
        self.reset_outbox()

    def reset_outbox(self) -> None:
        self.notifications: List[OutgoingMessage] = []
        # Set by a handler that needs to hand the user a file alongside a screen.
        self.pending_file: Optional[OutgoingFile] = None
        # A receipt the provider already holds: forwarded by id, never downloaded.
        self.forward_file_id: Optional[str] = None
        self.forward_file_kind: Optional[str] = None
        # Text a screen wants concealed until the reader taps it.
        self.hidden: Optional[str] = None

    # ------------------------------------------------------------ helpers
    def today(self, user: User) -> date:
        """The person's day. See jalali.today_in for why not the server's."""
        return jalali.today_in(user.timezone)

    async def home(self, user: User) -> Screen:
        """The home screen; with no book yet it says a book comes first."""
        return screens.welcome(
            user.display_name, first_run=not await self.books.books_for_user(user.id)
        )

    async def member_names(self, book_id) -> Dict:
        """user_id → display name, for every screen that lists people."""
        names = {}
        for member in await self.books.members(book_id):
            person = await self.identity.get_user(member.user_id)
            names[member.user_id] = person.display_name
        return names


class Feature:
    """A slice of the bot: the prefixes it answers and the flows it reads text for.

    `prefixes` are callback-data areas (`pr` in `pr:open:<id>`); `flows` are the
    `flow` values of a draft for which typed text belongs to this feature. Both
    are checked for collisions when the conversation is assembled, so two
    features can never silently share one.
    """

    prefixes: Sequence[str] = ()
    flows: Sequence[str] = ()

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    async def callback(
        self, area: str, parts: List[str], user: User, key: str, event: IncomingEvent
    ) -> Screen:
        raise NotImplementedError

    async def text(
        self, text: str, draft: dict, user: User, key: str, event: IncomingEvent
    ) -> Screen:
        raise NotImplementedError


def index(features: Sequence[type]) -> Tuple[Dict[str, type], Dict[str, type]]:
    """prefix → feature and flow → feature, refusing any overlap.

    A prefix collision is silent at run time: `rc:` once meant both "report
    CSV" and "recurring", and every recurring button raised. Raised here
    instead, when the bot is assembled, before any update is handled.
    """
    by_prefix: Dict[str, type] = {}
    by_flow: Dict[str, type] = {}
    for feature in features:
        for prefix in feature.prefixes:
            if prefix in by_prefix:
                raise RuntimeError(
                    f"callback prefix {prefix!r} claimed by both "
                    f"{by_prefix[prefix].__name__} and {feature.__name__}"
                )
            by_prefix[prefix] = feature
        for flow in feature.flows:
            if flow in by_flow:
                raise RuntimeError(
                    f"draft flow {flow!r} claimed by both "
                    f"{by_flow[flow].__name__} and {feature.__name__}"
                )
            by_flow[flow] = feature
    return by_prefix, by_flow
