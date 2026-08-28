"""One event in, one screen out.

This is the layer every messenger shares. It knows about books and transactions
because it calls the application services; it knows nothing about Telegram,
Bale or Rubika, because the adapter already turned their payload into an
`IncomingEvent` and will turn the reply back into their own format.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.base import EventKind, IncomingEvent, OutgoingFile, OutgoingMessage
from ..modules.books.models import BookType
from ..modules.books.service import BookService
from ..modules.budgets.models import BudgetKind
from ..modules.budgets.service import BudgetService
from ..modules.debts.models import Direction
from ..modules.debts.service import DebtService
from ..modules.loans.service import LoanService
from ..modules.payroll.models import (
    AdjustmentKind,
    AdjustmentMode,
    PeriodStatus,
    ShareBasis,
)
from ..modules.payroll.service import PayrollService
from ..modules.recurring.models import Period as RecurringPeriod
from ..modules.recurring.service import RecurringService
from ..modules.identity.models import Provider
from ..modules.identity.service import IdentityService
from ..modules.ledger.models import Flow, Scope
from ..modules.ledger.service import LedgerService
from ..modules.reports import service as reports_service
from ..modules.treasury.models import FundKind, RuleBasis
from ..modules.treasury.service import TreasuryService
from ..modules.reports.service import ReportService
from ..shared.errors import KasbBookError
from ..shared import jalali
from ..shared.parsing import parse_amount, parse_date, to_ascii_digits
from . import quick, screens
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
        self.reports = ReportService(session)
        self.budgets = BudgetService(session)
        self.debts = DebtService(session)
        self.loans = LoanService(session)
        self.recurring = RecurringService(session)
        self.payroll = PayrollService(session)
        self.treasury = TreasuryService(session)
        # Set by a handler that needs to hand the user a file alongside a screen.
        self._pending_file: Optional[OutgoingFile] = None
        # A receipt the provider already holds: forwarded by id, never downloaded.
        self._forward_file_id: Optional[str] = None
        self._forward_file_kind: Optional[str] = None

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
            document=self._pending_file,
            forward_file_id=self._forward_file_id,
            forward_file_kind=self._forward_file_kind,
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
            return screens.welcome(user.display_name)

        if event.kind is EventKind.CALLBACK and event.callback_data == "acc:create":
            user = await self.identity.create_account_from_messenger(
                self.provider,
                event.identity.external_id,
                display_name=event.identity.display_name,
                external_username=event.identity.username,
            )
            return screens.account_created(user.display_name)

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

        if area in ("rp", "rb", "rc"):
            return await self._period_screen(parts, user, area)

        if area == "qk":
            return await self._quick_callback(action, argument, user, key)

        if area == "bg":
            return await self._budget_callback(action, argument, user, key)

        if area == "dt":
            return await self._debt_callback(action, argument, user, key)

        if area == "ln":
            return await self._loan_callback(action, argument, user, key)

        if area == "td":
            return await self._tx_detail_callback(action, argument, user, key, event)

        if area == "sr":
            return await self._search_callback(action, argument, user, key)

        if area == "rr":
            return await self._recurring_callback(action, argument, user, key)

        if area == "rm":
            return await self._reminder_callback(action, user, key)

        if area == "pr":
            return await self._payroll_callback(action, argument, user, key)

        if area == "tf":
            return await self._treasury_callback(action, argument, user, key)

        if area == "sh":
            return await self._share_callback(action, argument, user, key)

        if area == "pf":
            return await self._performance_callback(action, argument, user, key)

        if area == "noop":
            # An inert label; the screen stays as it is.
            return screens.welcome(user.display_name)

        if area == "acc":
            return await self._account_callback(action, argument, user, key, event)

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
            return screens.book_menu(book)

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
            flow = Flow(argument)

            # Kept in the draft so a press can name one by position. The
            # callback payload has sixty-four bytes; a Persian category does
            # not reliably fit, and a button that overflows it fails silently.
            recent = list(await self.ledger.recent_categories(
                uuid.UUID(draft["book_id"]), user.id, flow
            ))
            draft["recent"] = recent
            await self.state.set(key, draft)
            return screens.ask_category(flow, recent)

        if action == "cat":
            draft = await self.state.get(key)
            recent = draft.get("recent") or []
            try:
                draft["category"] = recent[int(argument)]
            except (ValueError, IndexError):
                # The suggestions moved on since this screen was drawn.
                return screens.ask_category(Flow(draft.get("direction", "expense")), recent)

            await self.state.set(key, draft)
            return screens.ask_amount(draft["category"])

        return screens.pick_book(await self.books.books_for_user(user.id), "tx")

    async def _report_callback(self, action: str, argument: str, user):
        if action == "book":
            book = await self.books.get_book(uuid.UUID(argument))
            years = await self.reports.years_with_data(book.id, user.id)
            return screens.period_menu(book, years)

        return screens.report_menu(await self.books.books_for_user(user.id))

    async def _period_screen(self, parts, user, kind: str):
        """rp / rb / rc all name a book and a period the same way."""
        book = await self.books.get_book(uuid.UUID(parts[1]))
        spec = ":".join(parts[2:])
        period = reports_service.parse_spec(spec)
        if period is None:
            years = await self.reports.years_with_data(book.id, user.id)
            return screens.period_menu(book, years)

        if kind == "rb":
            buckets = await self.reports.by_category(book.id, user.id, period)
            return screens.category_breakdown(book, period.label, buckets, spec)

        if kind == "rc":
            payload = await self.reports.to_csv(book.id, user.id, period)
            self._pending_file = OutgoingFile(
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
        return screens.transaction_detail(book, tx)

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
        if action == "list":
            book = await self.books.get_book(uuid.UUID(argument))
            return await self._tx_list(book, user)

        if action == "page":
            parts = (event.callback_data or "").split(":")
            book = await self.books.get_book(uuid.UUID(parts[2]))
            return await self._tx_list(book, user, int(parts[3]))

        target = uuid.UUID(argument)
        book, tx = await self._tx_and_book(user, target)
        if tx is None:
            return screens.error("این تراکنش پیدا نشد")

        if action == "open":
            return screens.transaction_detail(book, tx)

        if action == "rcp":
            await self.state.set(key, {"flow": "receipt", "tx_id": str(tx.id),
                                       "book_id": str(book.id)})
            return screens.ask_receipt()

        if action == "rcpv":
            # The file lives on the provider; hand its id back so the adapter
            # can forward it without us ever holding the bytes.
            self._pending_file = None
            self._forward_file_id = tx.receipt_file_id
            self._forward_file_kind = tx.receipt_kind
            return screens.transaction_detail(book, tx)

        if action == "rcpd":
            await self.ledger.attach_receipt(book.id, user.id, tx.id, None, None)
            fresh = await self.ledger.get_transaction(book.id, user.id, tx.id)
            return screens.transaction_detail(book, fresh)

        if action == "del":
            return screens.confirm_delete(
                f"تراکنش «{tx.category}»", f"td:delok:{tx.id}", f"td:open:{tx.id}"
            )

        if action == "delok":
            await self.ledger.delete(book.id, user.id, tx.id)
            return await self._tx_list(book, user)

        return screens.transaction_detail(book, tx)

    # --------------------------------------------------------------- search
    async def _search_callback(self, action: str, argument: str, user, key: str):
        if action == "new":
            await self.state.set(key, {"flow": "search", "book_id": argument})
            return screens.ask_search()

        if action == "page":
            draft = await self.state.get(key)
            if draft.get("flow") != "search" or not draft.get("query"):
                return screens.welcome(user.display_name)
            return await self._search_screen(user, draft, int(argument))

        return screens.welcome(user.display_name)

    async def _search_screen(self, user, draft: dict, page: int):
        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        rows, total, amount = await self.reports.search(
            book.id, user.id, draft["query"], page
        )
        return screens.search_results(book, draft["query"], rows, total, amount, page)

    # ------------------------------------------------------------ recurring
    async def _recurring_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.clear(key)
            rules = await self.recurring.list_rules(book.id, user.id)
            return screens.recurring_list(book, rules)

        if action == "add":
            await self.state.set(key, {"flow": "recurring", "book_id": argument})
            return screens.recurring_pick_flow()

        if action == "flow":
            draft = await self.state.get(key)
            if draft.get("flow") != "recurring":
                return screens.welcome(user.display_name)
            draft["direction"] = argument
            await self.state.set(key, draft)
            return screens.recurring_ask_category()

        if action == "period":
            draft = await self.state.get(key)
            if draft.get("flow") != "recurring":
                return screens.welcome(user.display_name)
            draft["period"] = argument
            await self.state.set(key, draft)
            return screens.recurring_ask_start()

        if action == "today":
            return await self._save_recurring(user, key, date.today())

        target = uuid.UUID(argument)
        for book in await self.books.books_for_user(user.id):
            for rule in await self.recurring.list_rules(book.id, user.id):
                if rule.id != target:
                    continue
                if action == "tog":
                    await self.recurring.toggle(book.id, user.id, target)
                elif action == "del":
                    await self.recurring.delete(book.id, user.id, target)
                rules = await self.recurring.list_rules(book.id, user.id)
                return screens.recurring_list(book, rules)

        return screens.error("این قاعده پیدا نشد")

    async def _save_recurring(self, user, key: str, starts_on):
        draft = await self.state.get(key)
        if draft.get("flow") != "recurring" or not draft.get("period"):
            return screens.welcome(user.display_name)

        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        await self.recurring.create(
            book.id, user.id, Flow(draft["direction"]), draft["category"],
            Decimal(draft["amount"]), RecurringPeriod(draft["period"]), starts_on,
        )
        await self.state.clear(key)
        rules = await self.recurring.list_rules(book.id, user.id)
        return screens.recurring_list(book, rules)

    # ------------------------------------------------------------ reminders
    async def _reminder_callback(self, action: str, user, key: str):
        if action == "toggle":
            user.digest_enabled = not user.digest_enabled
            await self.session.flush()
            return screens.reminder_settings(user)

        if action == "hour":
            await self.state.set(key, {"flow": "reminder", "field": "hour"})
            return screens.ask_hour()

        if action == "days":
            await self.state.set(key, {"flow": "reminder", "field": "days"})
            return screens.ask_days()

        await self.state.clear(key)
        return screens.reminder_settings(user)

    # -------------------------------------------------------------- budgets
    async def _budget_screen(self, book, user):
        statuses = await self.budgets.status(book.id, user.id)
        year, month, _ = jalali.to_parts(date.today())
        label = f"{jalali.month_name(month)} {year}"
        return screens.budget_list(book, statuses, label)

    async def _budget_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.clear(key)
            return await self._budget_screen(book, user)

        if action == "add":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.set(key, {"flow": "budget", "book_id": argument})
            return screens.budget_pick_kind(book)

        if action == "kind":
            draft = await self.state.get(key)
            if draft.get("flow") != "budget":
                return screens.welcome(user.display_name)

            if argument == "category":
                draft["kind"] = BudgetKind.CATEGORY.value
                await self.state.set(key, draft)
                return screens.budget_ask_target()

            draft["kind"] = BudgetKind.FLOW.value
            draft["target"] = argument
            await self.state.set(key, draft)
            label = "درآمد" if argument == Flow.INCOME.value else "هزینه"
            return screens.budget_ask_amount(label)

        if action == "del":
            budget_id = uuid.UUID(argument)
            # The delete button lives on a list, so the book is whichever one
            # owns the budget; look it up rather than trusting stale state.
            for book in await self.books.books_for_user(user.id):
                for status in await self.budgets.status(book.id, user.id):
                    if status.budget.id == budget_id:
                        await self.budgets.delete(book.id, user.id, budget_id)
                        return await self._budget_screen(book, user)
            return screens.error("این بودجه پیدا نشد")

        return screens.welcome(user.display_name)

    # ---------------------------------------------------------------- debts
    async def _debt_screen(self, book, user):
        rows = await self.debts.list_debts(book.id, user.id)
        totals = await self.debts.totals(book.id, user.id)
        return screens.debt_list(book, rows, totals)

    async def _debt_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.clear(key)
            return await self._debt_screen(book, user)

        if action == "add":
            await self.state.set(key, {"flow": "debt", "book_id": argument})
            return screens.debt_ask_person()

        if action == "dir":
            draft = await self.state.get(key)
            if draft.get("flow") != "debt":
                return screens.welcome(user.display_name)
            draft["direction"] = argument
            await self.state.set(key, draft)
            return screens.debt_ask_amount()

        if action == "nodue":
            return await self._save_debt(user, key, None)

        if action in ("settle", "del"):
            target = uuid.UUID(argument)
            for book in await self.books.books_for_user(user.id):
                for debt in await self.debts.list_debts(book.id, user.id, True):
                    if debt.id == target:
                        if action == "settle":
                            await self.debts.settle(book.id, user.id, target)
                        else:
                            await self.debts.delete(book.id, user.id, target)
                        return await self._debt_screen(book, user)
            return screens.error("این مورد پیدا نشد")

        return screens.welcome(user.display_name)

    async def _save_debt(self, user, key: str, due):
        draft = await self.state.get(key)
        if draft.get("flow") != "debt" or not draft.get("amount"):
            return screens.welcome(user.display_name)

        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        await self.debts.create(
            book.id, user.id, draft["person"], Direction(draft["direction"]),
            Decimal(draft["amount"]), draft.get("note"), due,
        )
        await self.state.clear(key)
        return await self._debt_screen(book, user)

    # ---------------------------------------------------------------- loans
    async def _loan_screen(self, book, user):
        loans = await self.loans.list_loans(book.id, user.id)
        progress = [await self.loans.progress(book.id, user.id, loan) for loan in loans]
        return screens.loan_list(book, progress)

    async def _loan_for(self, user, loan_id: uuid.UUID):
        for book in await self.books.books_for_user(user.id):
            for loan in await self.loans.list_loans(book.id, user.id):
                if loan.id == loan_id:
                    return book, loan
        return None, None

    async def _loan_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.clear(key)
            return await self._loan_screen(book, user)

        if action == "add":
            await self.state.set(key, {"flow": "loan", "book_id": argument})
            return screens.loan_ask_title()

        if action == "today":
            return await self._save_loan(user, key, date.today())

        target = uuid.UUID(argument)
        book, loan = await self._loan_for(user, target)
        if loan is None:
            return screens.error("این وام پیدا نشد")

        if action == "open":
            progress = await self.loans.progress(book.id, user.id, loan)
            return screens.loan_detail(book, progress)

        if action == "pay":
            await self.loans.record_payment(book.id, user.id, loan.id)
            progress = await self.loans.progress(book.id, user.id, loan)
            return screens.loan_detail(book, progress)

        if action == "del":
            return screens.confirm_delete(
                f"وام «{loan.title}»", f"ln:delok:{loan.id}", f"ln:open:{loan.id}"
            )

        if action == "delok":
            await self.loans.delete(book.id, user.id, loan.id)
            return await self._loan_screen(book, user)

        return screens.welcome(user.display_name)

    async def _save_loan(self, user, key: str, starts_on):
        draft = await self.state.get(key)
        if draft.get("flow") != "loan" or not draft.get("count"):
            return screens.welcome(user.display_name)

        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        await self.loans.create(
            book.id, user.id, draft["title"],
            Decimal(draft["amount"]), int(draft["count"]), starts_on,
        )
        await self.state.clear(key)
        return await self._loan_screen(book, user)

    # ------------------------------------------------------------- account
    async def _account_panel(self, user):
        return screens.account_panel(
            user, await self.identity.list_identities(user.id), self.provider
        )

    async def _account_callback(self, action: str, argument: str, user, key: str, event):
        if action == "newcode":
            issued = await self.identity.start_link_from_messenger(
                self.provider, event.identity.external_id
            )
            return screens.not_linked(issued.token)

        if action == "list":
            await self.state.clear(key)
            return screens.identity_list(
                await self.identity.list_identities(user.id), self.provider
            )

        if action in ("panel", "contact"):
            await self.state.clear(key)
            return await self._account_panel(user)

        if action == "name":
            await self.state.set(key, {"flow": "account", "field": "name"})
            return screens.ask_display_name(user.display_name)

        if action == "email":
            await self.state.set(key, {"flow": "account", "field": "email"})
            return screens.ask_email()

        if action == "phone":
            await self.state.set(key, {"flow": "account", "field": "phone"})
            return screens.ask_phone()

        if action == "tz":
            return screens.ask_timezone(user.timezone)

        if action == "tzset":
            # The zone name contains a slash, which the splitter took for a
            # separator; rebuild it from what is left of the callback.
            zone = ":".join((event.callback_data or "").split(":")[2:])
            await self.identity.update_profile(user.id, timezone=zone)
            return await self._account_panel(user)

        if action == "pw":
            # Asking for the current one first only makes sense when there is
            # one; a new account is setting its first password.
            field = "password_current" if user.password_hash else "password_new"
            await self.state.set(key, {"flow": "account", "field": field})
            return (
                screens.ask_current_password() if user.password_hash
                else screens.ask_new_password(changing=False)
            )

        if action == "sessions":
            return screens.session_list(await self._auth().sessions(user.id))

        if action == "signout":
            await self._auth().revoke_all_for_user(user.id)
            return screens.session_list([])

        return await self._account_panel(user)

    def _auth(self):
        """Sessions live behind AuthService, which needs the signing key.

        The bot never mints a token, so any key satisfies the constructor —
        but passing a real one keeps this honest if that ever changes.
        """
        from ..modules.identity.auth import AuthService
        from ..shared.settings import Settings

        return AuthService(self.session, Settings.from_env().api_secret_key or "bot")

    async def _account_text(self, text: str, draft: dict, user, key: str):
        field = draft.get("field")

        try:
            if field == "name":
                await self.identity.update_profile(user.id, display_name=text)
            elif field == "email":
                await self.identity.set_contact(user.id, email=text)
            elif field == "phone":
                await self.identity.set_contact(user.id, phone=text)
            elif field == "password_current":
                # Held only long enough to prove the next one is allowed.
                draft["current"] = text
                draft["field"] = "password_new"
                await self.state.set(key, draft)
                return screens.ask_new_password(changing=True)
            elif field == "password_new":
                await self.identity.set_password(
                    user.id, text, current_password=draft.get("current")
                )
                # A password change signs every other session out. Someone who
                # changes it because they fear it leaked expects exactly that.
                await self._auth().revoke_all_for_user(user.id)
            else:
                await self.state.clear(key)
                return await self._account_panel(user)
        except KasbBookError as exc:
            # Stay in the flow so the answer can be corrected without starting
            # again, except for a wrong current password, which starts over.
            if field == "password_new" and draft.get("current"):
                await self.state.clear(key)
                return screens.error(str(exc))
            return screens.error(str(exc))

        await self.state.clear(key)
        return await self._account_panel(user)

    # ---------------------------------------------------------- treasury
    async def _fund_screen(self, book, user):
        """Every fund with what it has actually taken, not what it might."""
        funds = await self.treasury.funds(book.id, user.id)
        rows = [
            (fund, await self.treasury.balance(book.id, user.id, fund.id))
            for fund in funds
        ]
        return screens.fund_list(book, rows)

    async def _fund_detail(self, book, user, fund):
        rules = await self.treasury.rules(book.id, user.id, fund.id)
        balance = await self.treasury.balance(book.id, user.id, fund.id)
        return screens.fund_detail(book, fund, rules, balance)

    async def _treasury_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.clear(key)
            return await self._fund_screen(book, user)

        if action == "add":
            await self.state.set(key, {"flow": "fund", "book_id": argument})
            return screens.fund_ask_name()

        if action == "kind":
            draft = await self.state.get(key)
            if draft.get("flow") != "fund" or not draft.get("name"):
                return screens.welcome(user.display_name)

            book = await self.books.get_book(uuid.UUID(draft["book_id"]))
            await self.treasury.create_fund(
                book.id, user.id, draft["name"], FundKind(argument)
            )
            await self.state.clear(key)
            return await self._fund_screen(book, user)

        if action == "basis":
            draft = await self.state.get(key)
            if draft.get("flow") != "rule":
                return screens.welcome(user.display_name)

            draft["basis"] = argument
            await self.state.set(key, draft)
            return screens.rule_ask_value(argument)

        # Everything below acts on something already in the database, so the
        # book comes from that record rather than from the callback — a book id
        # in a button is a book id someone can edit.
        if action in ("rtog", "rdel"):
            from ..modules.treasury.models import TreasuryRule

            rule = await self.session.get(TreasuryRule, uuid.UUID(argument))
            if rule is None:
                return screens.error("این قاعده پیدا نشد")

            book = await self.books.get_book(rule.book_id)
            fund_id = rule.fund_id
            if action == "rtog":
                await self.treasury.toggle_rule(book.id, user.id, rule.id)
            else:
                await self.treasury.delete_rule(book.id, user.id, rule.id)

            fund = await self.treasury.get_fund(book.id, user.id, fund_id)
            return await self._fund_detail(book, user, fund)

        from ..modules.treasury.models import TreasuryFund

        fund = await self.session.get(TreasuryFund, uuid.UUID(argument))
        if fund is None:
            return screens.error("این صندوق پیدا نشد")
        book = await self.books.get_book(fund.book_id)

        if action == "open":
            return await self._fund_detail(book, user, fund)

        if action == "rule":
            await self.state.set(
                key, {"flow": "rule", "book_id": str(book.id), "fund_id": str(fund.id)}
            )
            return screens.rule_pick_basis(fund.name)

        if action == "tog":
            await self.treasury.toggle_fund(book.id, user.id, fund.id)
            return await self._fund_detail(book, user, fund)

        if action == "del":
            await self.treasury.delete_fund(book.id, user.id, fund.id)
            return await self._fund_screen(book, user)

        return screens.welcome(user.display_name)

    # ----------------------------------------------------------- payroll
    async def _member_names(self, book_id) -> dict:
        """user_id → display name, for every screen that lists people."""
        names = {}
        for member in await self.books.members(book_id):
            person = await self.identity.get_user(member.user_id)
            names[member.user_id] = person.display_name
        return names

    async def _period_list_screen(self, book, user):
        periods = await self.payroll.periods(book.id, user.id)
        year, month, _ = jalali.to_parts(date.today())
        return screens.period_list(book, periods, f"{jalali.month_name(month)} {year}")

    async def _period_detail(self, book, user, period):
        distribution = await self.payroll.compute_distribution(period.id)
        slips = await self.payroll.payslips(user.id, period.id)
        return screens.period_detail(book, period, distribution, len(slips))

    async def _payroll_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.clear(key)
            return await self._period_list_screen(book, user)

        if action == "new":
            book = await self.books.get_book(uuid.UUID(argument))
            today = date.today()
            year, month, _ = jalali.to_parts(today)
            start, end = jalali.month_range(year, month)
            period = await self.payroll.open_period(
                user.id, book.id, f"{jalali.month_name(month)} {year}", start, end
            )
            await self.state.clear(key)
            return await self._period_detail(book, user, period)

        if action in ("slip", "pay", "payall"):
            return await self._payslip_action(action, argument, user, key)

        if action in ("adjok", "adjwho", "adjadd", "adjnoreason"):
            return await self._adjustment_action(action, argument, user, key)

        period = await self.payroll.get_period(uuid.UUID(argument))
        book = await self.books.get_book(period.book_id)

        if action == "open":
            await self.state.clear(key)
            return await self._period_detail(book, user, period)

        if action == "calc":
            if not await self.payroll.shares(book.id, user.id, period.ends_on):
                # Zero payslips because nobody has a share is an unanswered
                # question, not an empty result.
                await self.state.set(key, {"flow": "share", "book_id": str(book.id)})
                return screens.no_shares_defined(book, period)

            await self.payroll.calculate(user.id, period.id)
            return await self._period_detail(book, user, period)

        if action == "slips":
            slips = await self.payroll.payslips(user.id, period.id)
            return screens.payslip_list(book, slips, await self._member_names(book.id))

        if action == "adj":
            adjustments = await self.payroll.adjustments(user.id, period.id)
            return screens.adjustment_list(
                book, period, adjustments, await self._member_names(book.id)
            )

        if action == "lock":
            await self.payroll.advance_period(user.id, period.id, PeriodStatus.LOCKED)
            period = await self.payroll.get_period(period.id)
            return await self._period_detail(book, user, period)

        return screens.welcome(user.display_name)

    async def _payslip_action(self, action: str, argument: str, user, key: str):
        from ..modules.payroll.models import Payslip

        slip = await self.session.get(Payslip, uuid.UUID(argument))
        if slip is None:
            return screens.error("این فیش پیدا نشد")

        book = await self.books.get_book(slip.book_id)
        names = await self._member_names(book.id)
        name = names.get(slip.user_id, "—")
        outstanding = slip.net_pay - sum(
            (p.amount for p in slip.payments), Decimal("0")
        )

        if action == "slip":
            await self.state.clear(key)
            return screens.payslip_detail(book, slip, name)

        if action == "payall":
            # The common case by a long way: someone was paid what they were
            # owed, and typing the number again is a chance to mistype it.
            await self.payroll.pay(user.id, slip.id, outstanding)
            await self.session.refresh(slip)
            return screens.payslip_detail(book, slip, name)

        if action == "pay":
            await self.state.set(key, {"flow": "payslip", "slip_id": argument})
            return screens.payslip_ask_amount(name, outstanding, book.base_currency)

        return screens.welcome(user.display_name)

    async def _adjustment_action(self, action: str, argument: str, user, key: str):
        from ..modules.payroll.models import Adjustment

        if action == "adjadd":
            period = await self.payroll.get_period(uuid.UUID(argument))
            book = await self.books.get_book(period.book_id)
            await self.state.set(
                key, {"flow": "adjustment", "period_id": argument}
            )
            return screens.adjustment_pick_member(
                period, await self.books.members(book.id), await self._member_names(book.id)
            )

        if action == "adjwho":
            draft = await self.state.get(key)
            if draft.get("flow") != "adjustment":
                return screens.welcome(user.display_name)

            draft["user_id"] = argument
            await self.state.set(key, draft)
            period = await self.payroll.get_period(uuid.UUID(draft["period_id"]))
            names = await self._member_names(period.book_id)
            return screens.adjustment_ask_value(names.get(uuid.UUID(argument), "—"))

        if action == "adjnoreason":
            return await self._save_adjustment(user, key, reason=None)

        if action == "adjok":
            adjustment = await self.session.get(Adjustment, uuid.UUID(argument))
            if adjustment is None:
                return screens.error("این مورد پیدا نشد")

            await self.payroll.approve_adjustment(user.id, adjustment.id)
            period = await self.payroll.get_period(adjustment.period_id)
            book = await self.books.get_book(period.book_id)
            return screens.adjustment_list(
                book, period,
                await self.payroll.adjustments(user.id, period.id),
                await self._member_names(book.id),
            )

        return screens.welcome(user.display_name)

    async def _save_adjustment(self, user, key: str, reason):
        draft = await self.state.get(key)
        if draft.get("flow") != "adjustment" or "value" not in draft:
            return screens.welcome(user.display_name)

        period = await self.payroll.get_period(uuid.UUID(draft["period_id"]))
        book = await self.books.get_book(period.book_id)

        value = Decimal(draft["value"])
        # The sign already says which it is, so asking the person to pick a
        # kind as well would be asking the same question twice.
        kind = AdjustmentKind.BONUS if value > 0 else AdjustmentKind.PENALTY

        await self.payroll.add_adjustment(
            user.id, period.id, uuid.UUID(draft["user_id"]),
            kind, AdjustmentMode.AMOUNT, value, reason=reason,
        )
        await self.state.clear(key)
        return screens.adjustment_list(
            book, period,
            await self.payroll.adjustments(user.id, period.id),
            await self._member_names(book.id),
        )

    async def _fund_text(self, text: str, draft: dict, user, key: str):
        draft["name"] = text[:80]
        await self.state.set(key, draft)
        return screens.fund_pick_kind(draft["name"])

    async def _rule_text(self, text: str, draft: dict, user, key: str):
        basis = draft.get("basis")
        if not basis:
            return screens.welcome(user.display_name)

        if basis == "fixed":
            value = parse_amount(text)
        else:
            # A percentage is a plain number, so the amount parser's "۵م means
            # five million" shortcut would read "10" as ten and "۱۰م" as ten
            # million percent. Only digits are accepted here.
            try:
                value = Decimal(to_ascii_digits(text).strip())
            except Exception:
                value = None

        if value is None or value <= 0:
            return screens.rule_ask_value(basis)

        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        fund = await self.treasury.get_fund(
            book.id, user.id, uuid.UUID(draft["fund_id"])
        )
        await self.treasury.add_rule(
            book.id, user.id, fund.id, RuleBasis(basis), value
        )
        await self.state.clear(key)
        return await self._fund_detail(book, user, fund)

    async def _payslip_text(self, text: str, draft: dict, user, key: str):
        from ..modules.payroll.models import Payslip

        amount = parse_amount(text)
        slip = await self.session.get(Payslip, uuid.UUID(draft["slip_id"]))
        if slip is None:
            await self.state.clear(key)
            return screens.error("این فیش پیدا نشد")

        book = await self.books.get_book(slip.book_id)
        names = await self._member_names(book.id)
        name = names.get(slip.user_id, "—")
        outstanding = slip.net_pay - sum((p.amount for p in slip.payments), Decimal("0"))

        if amount is None or amount <= 0:
            return screens.payslip_ask_amount(name, outstanding, book.base_currency)

        await self.payroll.pay(user.id, slip.id, amount)
        await self.session.refresh(slip)
        await self.state.clear(key)
        return screens.payslip_detail(book, slip, name)

    async def _adjustment_text(self, text: str, draft: dict, user, key: str):
        if "user_id" not in draft:
            return screens.welcome(user.display_name)

        # A deduction is a negative number, and the amount parser only reads
        # magnitudes — so the sign has to be taken off the front first.
        cleaned = to_ascii_digits(text).strip()
        negative = cleaned.startswith("-")
        amount = parse_amount(cleaned.lstrip("-+").strip())

        if amount is None or amount <= 0:
            period = await self.payroll.get_period(uuid.UUID(draft["period_id"]))
            names = await self._member_names(period.book_id)
            return screens.adjustment_ask_value(names.get(uuid.UUID(draft["user_id"]), "—"))

        draft["value"] = str(-amount if negative else amount)
        await self.state.set(key, draft)
        return screens.adjustment_ask_reason()

    # ------------------------------------------------------------- shares
    async def _share_screen(self, book, user):
        return screens.share_list(
            book,
            await self.books.members(book.id),
            await self._member_names(book.id),
            await self.payroll.shares(book.id, user.id),
        )

    async def _share_book(self, user, key: str):
        """Which book this flow is about. Held in state, never in the button."""
        draft = await self.state.get(key)
        if not draft.get("book_id"):
            return None, draft
        return await self.books.get_book(uuid.UUID(draft["book_id"])), draft

    async def _share_callback(self, action: str, argument: str, user, key: str):
        if action == "open":
            book = await self.books.get_book(uuid.UUID(argument))
            await self.state.set(key, {"flow": "share", "book_id": argument})
            return await self._share_screen(book, user)

        book, draft = await self._share_book(user, key)
        if book is None:
            return screens.welcome(user.display_name)

        if action == "list":
            await self.state.set(key, {"flow": "share", "book_id": str(book.id)})
            return await self._share_screen(book, user)

        if action == "set":
            draft["user_id"] = argument
            await self.state.set(key, draft)
            rules = await self.payroll.shares(book.id, user.id)
            names = await self._member_names(book.id)
            return screens.share_pick_basis(
                names.get(uuid.UUID(argument), "—"), rules.get(uuid.UUID(argument))
            )

        if action == "basis":
            if "user_id" not in draft:
                return await self._share_screen(book, user)
            draft["basis"] = argument
            await self.state.set(key, draft)
            names = await self._member_names(book.id)
            return screens.share_ask_value(
                names.get(uuid.UUID(draft["user_id"]), "—"), argument
            )

        if action == "clear":
            if "user_id" in draft:
                await self.payroll.clear_share(
                    book.id, user.id, uuid.UUID(draft["user_id"])
                )
            await self.state.set(key, {"flow": "share", "book_id": str(book.id)})
            return await self._share_screen(book, user)

        return await self._share_screen(book, user)

    async def _share_text(self, text: str, draft: dict, user, key: str):
        basis = draft.get("basis")
        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        if not basis or "user_id" not in draft:
            return await self._share_screen(book, user)

        names = await self._member_names(book.id)
        name = names.get(uuid.UUID(draft["user_id"]), "—")

        if basis == "fixed":
            value = parse_amount(text)
        else:
            # A percentage and a weight are plain numbers. The amount parser
            # reads "۵۰م" as fifty million, which would be fifty million
            # percent, or a weight nothing could outweigh.
            try:
                value = Decimal(to_ascii_digits(text).strip())
            except Exception:
                value = None

        if value is None or value <= 0:
            return screens.share_ask_value(name, basis)

        await self.payroll.set_share(
            book.id, user.id, uuid.UUID(draft["user_id"]), ShareBasis(basis), value
        )
        await self.state.set(key, {"flow": "share", "book_id": str(book.id)})
        return await self._share_screen(book, user)

    # --------------------------------------------------------- performance
    async def _performance_screen(self, book, user, period):
        return screens.performance_list(
            book, period,
            await self.books.members(book.id),
            await self._member_names(book.id),
            await self.payroll.performance(user.id, period.id),
            await self.payroll.shares(book.id, user.id, period.ends_on),
        )

    async def _performance_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            period = await self.payroll.get_period(uuid.UUID(argument))
            book = await self.books.get_book(period.book_id)
            await self.state.set(
                key, {"flow": "performance", "period_id": argument}
            )
            return await self._performance_screen(book, user, period)

        draft = await self.state.get(key)
        if not draft.get("period_id"):
            return screens.welcome(user.display_name)

        period = await self.payroll.get_period(uuid.UUID(draft["period_id"]))
        book = await self.books.get_book(period.book_id)

        if action == "set":
            draft["user_id"] = argument
            await self.state.set(key, draft)
            rules = await self.payroll.shares(book.id, user.id, period.ends_on)
            names = await self._member_names(book.id)
            rule = rules.get(uuid.UUID(argument))
            return screens.performance_ask_value(
                names.get(uuid.UUID(argument), "—"),
                rule.basis.value if rule else "hours",
            )

        return await self._performance_screen(book, user, period)

    async def _performance_text(self, text: str, draft: dict, user, key: str):
        period = await self.payroll.get_period(uuid.UUID(draft["period_id"]))
        book = await self.books.get_book(period.book_id)
        if "user_id" not in draft:
            return await self._performance_screen(book, user, period)

        member_id = uuid.UUID(draft["user_id"])
        rules = await self.payroll.shares(book.id, user.id, period.ends_on)
        rule = rules.get(member_id)
        basis = rule.basis.value if rule else "hours"

        try:
            value = Decimal(to_ascii_digits(text).strip())
        except Exception:
            value = None

        if value is None or value < 0:
            names = await self._member_names(book.id)
            return screens.performance_ask_value(names.get(member_id, "—"), basis)

        column = {"hours": "hours_worked", "days": "days_worked", "points": "points"}[basis]
        await self.payroll.record_performance(
            user.id, period.id, member_id, **{column: value}
        )
        draft.pop("user_id", None)
        await self.state.set(key, draft)
        return await self._performance_screen(book, user, period)

    # ----------------------------------------------------- free text steps
    async def _text(self, event: IncomingEvent, user, key: str):
        draft = await self.state.get(key)
        text = (event.text or "").strip()

        if draft.get("flow") == "new_book":
            await self.books.create_book(user.id, text, BookType(draft["type"]))
            await self.state.clear(key)
            return screens.book_list(await self.books.books_for_user(user.id))

        if draft.get("flow") == "tx":
            return await self._tx_text(text, draft, user, key)

        if draft.get("flow") == "budget":
            return await self._budget_text(text, draft, user, key)

        if draft.get("flow") == "debt":
            return await self._debt_text(text, draft, user, key)

        if draft.get("flow") == "loan":
            return await self._loan_text(text, draft, user, key)

        if draft.get("flow") == "search":
            if len(text) < 2:
                return screens.ask_search()
            draft["query"] = text[:60]
            await self.state.set(key, draft)
            return await self._search_screen(user, draft, 0)

        if draft.get("flow") == "recurring":
            return await self._recurring_text(text, draft, user, key)

        if draft.get("flow") == "reminder":
            return await self._reminder_text(text, draft, user, key)

        if draft.get("flow") == "account":
            return await self._account_text(text, draft, user, key)

        if draft.get("flow") == "fund":
            return await self._fund_text(text, draft, user, key)

        if draft.get("flow") == "rule":
            return await self._rule_text(text, draft, user, key)

        if draft.get("flow") == "payslip":
            return await self._payslip_text(text, draft, user, key)

        if draft.get("flow") == "share":
            return await self._share_text(text, draft, user, key)

        if draft.get("flow") == "performance":
            return await self._performance_text(text, draft, user, key)

        if draft.get("flow") == "adjustment":
            if "value" in draft:
                return await self._save_adjustment(user, key, reason=text[:120])
            return await self._adjustment_text(text, draft, user, key)

        # Nothing in flight, so try to read the line as a transaction.
        entry = quick.parse(text)
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
        }
        await self.state.set(key, pending)

        if len(books) == 1:
            pending["book_id"] = str(books[0].id)
            await self.state.set(key, pending)
            return screens.quick_pick_flow(entry)

        return screens.quick_pick_book(entry, books)

    async def _quick_callback(self, action: str, argument: str, user, key: str):
        draft = await self.state.get(key)
        if draft.get("flow") != "quick":
            return screens.welcome(user.display_name)

        if action == "book":
            draft["book_id"] = argument
            await self.state.set(key, draft)
            entry = quick.QuickEntry(draft["category"], Decimal(draft["amount"]))
            return screens.quick_pick_flow(entry)

        if action == "flow":
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
            await self.state.clear(key)
            return screens.transaction_saved(
                book, flow, transaction.category,
                transaction.converted_amount, book.base_currency,
            )

        return screens.welcome(user.display_name)

    async def _budget_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("target"):
            draft["target"] = text[:80]
            await self.state.set(key, draft)
            return screens.budget_ask_amount(draft["target"])

        amount = parse_amount(text)
        if amount is None:
            return screens.budget_ask_amount(draft["target"])

        book = await self.books.get_book(uuid.UUID(draft["book_id"]))
        await self.budgets.set_budget(
            book.id, user.id, BudgetKind(draft["kind"]), draft["target"], amount
        )
        await self.state.clear(key)
        return await self._budget_screen(book, user)

    async def _debt_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("person"):
            draft["person"] = text[:80]
            await self.state.set(key, draft)
            return screens.debt_pick_direction(draft["person"])

        if not draft.get("direction"):
            return screens.debt_pick_direction(draft["person"])

        if not draft.get("amount"):
            amount = parse_amount(text)
            if amount is None:
                return screens.debt_ask_amount()
            draft["amount"] = str(amount)
            await self.state.set(key, draft)
            return screens.debt_ask_due()

        due = parse_date(text)
        if due is None:
            return screens.debt_ask_due()
        return await self._save_debt(user, key, due)

    async def _loan_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("title"):
            draft["title"] = text[:80]
            await self.state.set(key, draft)
            return screens.loan_ask_amount(draft["title"])

        if not draft.get("amount"):
            amount = parse_amount(text)
            if amount is None or amount <= 0:
                return screens.loan_ask_amount(draft["title"])
            draft["amount"] = str(amount)
            await self.state.set(key, draft)
            return screens.loan_ask_count()

        if not draft.get("count"):
            digits = to_ascii_digits(text).strip()
            if not digits.isdigit() or int(digits) <= 0:
                return screens.loan_ask_count()
            draft["count"] = int(digits)
            await self.state.set(key, draft)
            return screens.loan_ask_start()

        starts_on = parse_date(text)
        if starts_on is None:
            return screens.loan_ask_start()
        return await self._save_loan(user, key, starts_on)

    async def _recurring_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("category"):
            draft["category"] = text[:80]
            await self.state.set(key, draft)
            return screens.recurring_ask_amount(draft["category"])

        if not draft.get("amount"):
            amount = parse_amount(text)
            if amount is None or amount <= 0:
                return screens.recurring_ask_amount(draft["category"])
            draft["amount"] = str(amount)
            await self.state.set(key, draft)
            return screens.recurring_pick_period()

        if not draft.get("period"):
            return screens.recurring_pick_period()

        starts_on = parse_date(text)
        if starts_on is None:
            return screens.recurring_ask_start()
        return await self._save_recurring(user, key, starts_on)

    async def _reminder_text(self, text: str, draft: dict, user, key: str):
        digits = to_ascii_digits(text).strip()
        if not digits.isdigit():
            return screens.ask_hour() if draft["field"] == "hour" else screens.ask_days()

        value = int(digits)
        if draft["field"] == "hour":
            if value > 23:
                return screens.ask_hour()
            user.digest_hour = value
        else:
            user.reminder_days = min(value, 60)

        await self.session.flush()
        await self.state.clear(key)
        return screens.reminder_settings(user)

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
