"""Planning in the bot: budgets, debts, loans, recurring rules and reminder settings.

Everything that looks ahead rather than records what happened. Each part is a
list of items per book, an add flow that asks one thing at a time, and a
confirmed delete; the rules themselves live in their services.

"One thing at a time" had become one thing per screen even where two answers
were the same answer: a category already knows whether it is income or
expense, a recurring rule is almost always monthly and starts today, and a
loan's instalment count is one of half a dozen numbers. Those are defaults and
taps now, not questions. Every screen in a flow is also told where the flow
began, so «انصراف» leaves the draft without leaving the place.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from ...modules.budgets.models import BudgetKind
from ...modules.debts.models import Direction
from ...modules.recurring.models import Period as RecurringPeriod
from ...modules.ledger.models import Flow
from ...shared.errors import ValidationError
from ...shared import jalali
from ...shared.parsing import parse_date, to_ascii_digits
from .. import screens
from .base import NO_DUE_WORDS, Feature, read_amount


class PlanningFeature(Feature):
    prefixes = ("bg", "dt", "ln", "rr", "rm")
    flows = ("budget", "debt", "loan", "recurring", "reminder")

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""
        extra = parts[3] if len(parts) > 3 else ""
        if area == "bg":
            return await self._budget_callback(action, argument, user, key)
        if area == "dt":
            return await self._debt_callback(action, argument, user, key, extra)
        if area == "ln":
            return await self._loan_callback(action, argument, user, key, extra)
        if area == "rr":
            return await self._recurring_callback(action, argument, user, key)
        if area == "rm":
            return await self._reminder_callback(action, user, key)
        raise AssertionError(area)

    async def text(self, text, draft, user, key, event):
        if draft.get("flow") == "budget":
            return await self._budget_text(text, draft, user, key)
        if draft.get("flow") == "debt":
            return await self._debt_text(text, draft, user, key)
        if draft.get("flow") == "loan":
            return await self._loan_text(text, draft, user, key)
        if draft.get("flow") == "recurring":
            return await self._recurring_text(text, draft, user, key)
        if draft.get("flow") == "reminder":
            return await self._reminder_text(text, draft, user, key)
        raise AssertionError(draft.get("flow"))

    # ------------------------------------------------------------- the way back
    @staticmethod
    def _parent(prefix: str, book_id) -> str:
        """The list a flow began on, for its «انصراف» button.

        Fifteen prompts here sent the person home when they backed out, because
        the later screens in a flow were never told which book they belonged
        to and so could not name their own parent. The book id is in the draft
        from the first step, and every `:list:` callback clears the draft on
        arrival, so handing the parent down is the whole fix.
        """
        return f"{prefix}:list:{book_id}"

    @staticmethod
    def _bad_date(typed: str) -> str:
        """Why a date was refused, in one place: the three prompts here that can
        refuse one each carried their own copy of this sentence."""
        return f"«{typed[:30]}» را به‌عنوان تاریخ نفهمیدم."

    # ------------------------------------------------- the book's own categories
    async def _stash_categories(self, draft: dict, user, key: str, flow=None):
        """The categories this book already uses, kept in the draft.

        A button names one by position, never by name: a category is free text
        up to eighty characters and a callback payload is sixty-four bytes, so
        a Persian name on a button would silently fail to send. Each one is
        stored with its own flow, which is what lets a single tap answer both
        «کدام دسته؟» and «درآمد یا هزینه؟». A legacy category carries no flow;
        it keeps an empty one and the flow is asked for separately.
        """
        rows = await self.ctx.categories.list(uuid.UUID(draft["book_id"]), user.id, flow)
        draft["offered"] = [[row.name, row.flow.value if row.flow else ""] for row in rows]
        await self.ctx.state.set(key, draft)
        return draft["offered"]

    @staticmethod
    def _offered_name(offered, index: str):
        """(name, flow) for a button's position, or None if the list moved on."""
        try:
            position = int(index)
            if position < 0:
                raise IndexError(index)
            name, flow = offered[position]
        except (ValueError, IndexError):
            return None
        return name, flow

    @staticmethod
    def _match_offered(typed: str, offered):
        """The book's own spelling of a typed name, where it has one.

        A budget's target and a recurring rule's category are both matched
        against a transaction's category by exact string equality, so «اجاره»
        typed with its half space one letter along is a different category that
        will never match anything. What the book already holds wins, letter for
        letter.
        """
        def flat(value: str) -> str:
            return value.replace("\u200c", "").replace(" ", "").casefold()

        for name, flow in offered:
            if flat(name) == flat(typed):
                return name, flow
        return None

    # ------------------------------------------------------------ recurring
    async def _recurring_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.clear(key)
            rules = await self.ctx.recurring.list_rules(book.id, user.id)
            return screens.recurring_list(book, rules)

        if action == "add":
            # Straight to the category: the flow question it used to open with
            # is answered by whichever category is picked.
            draft = {"flow": "recurring", "book_id": argument}
            offered = await self._stash_categories(draft, user, key)
            return screens.recurring_ask_category(
                categories=offered, cancel_data=self._parent("rr", argument)
            )

        if action == "cat":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "recurring":
                return screens.stale(None, user.display_name)
            parent = self._parent("rr", draft["book_id"])
            offered = draft.get("offered") or []
            picked = self._offered_name(offered, argument)
            if picked is None:
                return screens.recurring_ask_category(
                    categories=offered, cancel_data=parent
                )
            draft["category"], draft["direction"] = picked
            await self.ctx.state.set(key, draft)
            if not draft["direction"]:
                return screens.recurring_pick_flow(cancel_data=parent)
            return screens.recurring_ask_amount(draft["category"], cancel_data=parent)

        if action == "flow":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "recurring":
                return screens.stale(None, user.display_name)
            draft["direction"] = argument
            await self.ctx.state.set(key, draft)
            parent = self._parent("rr", draft["book_id"])
            if draft.get("category"):
                # The only way here now: a typed category the book did not know.
                return screens.recurring_ask_amount(draft["category"], cancel_data=parent)
            offered = await self._stash_categories(draft, user, key, argument)
            return screens.recurring_ask_category(categories=offered, cancel_data=parent)

        if action == "period":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "recurring":
                return screens.stale(None, user.display_name)
            draft["period"] = argument
            await self.ctx.state.set(key, draft)
            return screens.recurring_ask_start(
                cancel_data=self._parent("rr", draft["book_id"]), period=argument
            )

        if action == "today":
            return await self._save_recurring(user, key, self.ctx.today(user))

        target = uuid.UUID(argument)
        for book in await self.ctx.books.books_for_user(user.id):
            for rule in await self.ctx.recurring.list_rules(book.id, user.id):
                if rule.id != target:
                    continue
                if action == "del":
                    return screens.confirm_delete(
                        f"تراکنش تکرارشونده «{rule.category}»",
                        f"rr:delok:{target}", f"rr:list:{book.id}",
                    )
                notice = None
                if action == "tog":
                    await self.ctx.recurring.toggle(book.id, user.id, target)
                elif action == "delok":
                    await self.ctx.recurring.delete(book.id, user.id, target)
                    notice = "✅ حذف شد."
                rules = await self.ctx.recurring.list_rules(book.id, user.id)
                screen = screens.recurring_list(book, rules)
                return screens.with_notice(notice, screen) if notice else screen

        return screens.error("این مورد دیگر وجود ندارد؛ شاید حذف شده است.", back="book:list")

    async def _save_recurring(self, user, key: str, starts_on):
        draft = await self.ctx.state.get(key)
        if draft.get("flow") != "recurring" or not draft.get("period"):
            return screens.stale(None, user.display_name)

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        await self.ctx.recurring.create(
            book.id, user.id, Flow(draft["direction"]), draft["category"],
            Decimal(draft["amount"]), RecurringPeriod(draft["period"]), starts_on,
        )
        await self.ctx.state.clear(key)
        rules = await self.ctx.recurring.list_rules(book.id, user.id)
        return screens.recurring_list(book, rules)

    # ------------------------------------------------------------ reminders
    async def _reminder_callback(self, action: str, user, key: str):
        if action == "toggle":
            user.digest_enabled = not user.digest_enabled
            await self.ctx.session.flush()
            return screens.reminder_settings(user)

        if action == "hour":
            await self.ctx.state.set(key, {"flow": "reminder", "field": "hour"})
            return screens.ask_hour()

        if action == "days":
            await self.ctx.state.set(key, {"flow": "reminder", "field": "days"})
            return screens.ask_days()

        await self.ctx.state.clear(key)
        return screens.reminder_settings(user)

    # -------------------------------------------------------------- budgets
    async def _budget_screen(self, book, user):
        statuses = await self.ctx.budgets.status(book.id, user.id)
        year, month, _ = jalali.to_parts(self.ctx.today(user))
        label = f"{jalali.month_name(month)} {year}"
        return screens.budget_list(book, statuses, label)

    async def _budget_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.clear(key)
            return await self._budget_screen(book, user)

        if action == "add":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            draft = {"flow": "budget", "book_id": argument}
            offered = await self._stash_categories(draft, user, key)
            return screens.budget_pick_kind(book, [name for name, _ in offered])

        if action == "cat":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "budget":
                return screens.stale(None, user.display_name)
            offered = draft.get("offered") or []
            picked = self._offered_name(offered, argument)
            if picked is None:
                book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
                return screens.budget_pick_kind(book, [name for name, _ in offered])
            draft["kind"] = BudgetKind.CATEGORY.value
            draft["target"] = picked[0]
            await self.ctx.state.set(key, draft)
            return screens.budget_ask_amount(
                self._budget_label(draft), cancel_data=self._parent("bg", draft["book_id"])
            )

        if action == "kind":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "budget":
                return screens.stale(None, user.display_name)
            parent = self._parent("bg", draft["book_id"])

            if argument == "category":
                draft["kind"] = BudgetKind.CATEGORY.value
                await self.ctx.state.set(key, draft)
                return screens.budget_ask_target(cancel_data=parent)

            draft["kind"] = BudgetKind.FLOW.value
            draft["target"] = argument
            await self.ctx.state.set(key, draft)
            return screens.budget_ask_amount(self._budget_label(draft), cancel_data=parent)

        if action in ("del", "delok"):
            budget_id = uuid.UUID(argument)
            # The delete button lives on a list, so the book is whichever one
            # owns the budget; look it up rather than trusting stale state.
            for book in await self.ctx.books.books_for_user(user.id):
                for status in await self.ctx.budgets.status(book.id, user.id):
                    if status.budget.id == budget_id:
                        if action == "del":
                            return screens.confirm_delete(
                                f"بودجهٔ «{status.label}»",
                                f"bg:delok:{budget_id}", f"bg:list:{book.id}",
                            )
                        await self.ctx.budgets.delete(book.id, user.id, budget_id)
                        return screens.with_notice(
                            "✅ بودجه حذف شد.", await self._budget_screen(book, user)
                        )
            return screens.error("این بودجه دیگر وجود ندارد؛ شاید حذف شده است.", back="book:list")

        return screens.stale(None, user.display_name)

    # ---------------------------------------------------------------- debts
    async def _debt_screen(self, book, user):
        rows = await self.ctx.debts.list_debts(book.id, user.id)
        totals = await self.ctx.debts.totals(book.id, user.id)
        return screens.debt_list(book, rows, totals)

    @staticmethod
    def _direction_label(direction: str) -> str:
        """Which of the two entry buttons was pressed, said back on the next
        screen — otherwise the only record of the tap is the draft."""
        return "📥 طلب من" if direction == Direction.OWED_TO_ME.value else "📤 بدهی من"

    async def _debt_callback(self, action: str, argument: str, user, key: str, extra: str = ""):
        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.clear(key)
            return await self._debt_screen(book, user)

        if action == "add":
            draft = {"flow": "debt", "book_id": argument}
            parent = self._parent("dt", argument)
            if extra in (Direction.OWED_TO_ME.value, Direction.I_OWE.value):
                # The list has one entry button per direction, so the screen
                # that used to ask for it is no longer in the path.
                draft["direction"] = extra
                await self.ctx.state.set(key, draft)
                return screens.debt_ask_person(
                    cancel_data=parent, what=self._direction_label(extra)
                )
            await self.ctx.state.set(key, draft)
            return screens.debt_ask_person(cancel_data=parent)

        if action == "dir":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "debt":
                return screens.stale(None, user.display_name)
            draft["direction"] = argument
            await self.ctx.state.set(key, draft)
            return screens.debt_ask_amount(
                cancel_data=self._parent("dt", draft["book_id"]),
                person=draft.get("person") or "",
            )

        if action == "due":
            # The offsets the buttons carry, counted from the person's own
            # today rather than the server's.
            days = int(argument) if argument.isdigit() else 0
            return await self._save_debt(user, key, self.ctx.today(user) + timedelta(days=days))

        if action == "nodue":
            return await self._save_debt(user, key, None)

        if action in ("settle", "settleonly", "settletx", "del", "delok"):
            target = uuid.UUID(argument)
            for book in await self.ctx.books.books_for_user(user.id):
                for debt in await self.ctx.debts.list_debts(book.id, user.id, True):
                    if debt.id == target:
                        if action == "del":
                            return screens.confirm_delete(
                                f"مورد «{debt.person}»", f"dt:delok:{target}", f"dt:list:{book.id}",
                            )
                        if action == "settle":
                            return screens.debt_confirm_settle(book, debt)
                        if action in ("settleonly", "settletx"):
                            recorded = action == "settletx"
                            await self.ctx.debts.settle(book.id, user.id, target,
                                                    record_transaction=recorded)
                            notice = f"✅ «{debt.person}» تسویه شد." + (
                                " مبلغش در تراکنش‌ها هم ثبت شد." if recorded else ""
                            )
                        else:
                            await self.ctx.debts.delete(book.id, user.id, target)
                            notice = f"✅ «{debt.person}» حذف شد."
                        return screens.with_notice(notice, await self._debt_screen(book, user))
            return screens.error("این مورد دیگر وجود ندارد؛ شاید حذف شده است.", back="book:list")

        return screens.stale(None, user.display_name)

    async def _save_debt(self, user, key: str, due):
        draft = await self.ctx.state.get(key)
        if draft.get("flow") != "debt" or not draft.get("amount"):
            return screens.stale(None, user.display_name)

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        await self.ctx.debts.create(
            book.id, user.id, draft["person"], Direction(draft["direction"]),
            Decimal(draft["amount"]),
            # No note: nothing in the bot ever set one, and reading it off the
            # draft pretended otherwise. The web and the API do set it, which
            # is why debt_list still prints a note when there is one.
            None, due,
        )
        await self.ctx.state.clear(key)
        return await self._debt_screen(book, user)

    # ---------------------------------------------------------------- loans
    async def _loan_screen(self, book, user):
        loans = await self.ctx.loans.list_loans(book.id, user.id)
        progress = [await self.ctx.loans.progress(book.id, user.id, loan) for loan in loans]
        return screens.loan_list(book, progress)

    async def _loan_for(self, user, loan_id: uuid.UUID):
        for book in await self.ctx.books.books_for_user(user.id):
            for loan in await self.ctx.loans.list_loans(book.id, user.id):
                if loan.id == loan_id:
                    return book, loan
        return None, None

    async def _loan_callback(self, action: str, argument: str, user, key: str, extra: str = ""):
        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.clear(key)
            return await self._loan_screen(book, user)

        if action == "add":
            await self.ctx.state.set(key, {"flow": "loan", "book_id": argument})
            return screens.loan_ask_title(cancel_data=self._parent("ln", argument))

        if action == "count":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "loan" or not draft.get("amount"):
                return screens.stale(None, user.display_name)
            count, problem = self._read_count(argument)
            if problem:
                return screens.loan_ask_count(
                    draft.get("title") or "", problem,
                    cancel_data=self._parent("ln", draft["book_id"]),
                )
            draft["count"] = count
            await self.ctx.state.set(key, draft)
            # The screen says these buttons start the loan today, and the
            # detail screen it lands on prints that date straight back.
            return await self._save_loan(user, key, self.ctx.today(user), show_detail=True)

        if action == "today":
            return await self._save_loan(user, key, self.ctx.today(user))

        target = uuid.UUID(argument)
        book, loan = await self._loan_for(user, target)
        if loan is None:
            return screens.error("این وام دیگر وجود ندارد؛ شاید حذف شده است.")

        if action == "open":
            progress = await self.ctx.loans.progress(book.id, user.id, loan)
            return screens.loan_detail(book, progress)

        if action == "pay":
            # The button names the count it was shown with; a second press of
            # it is refused instead of paying a second instalment.
            await self.ctx.loans.record_payment(
                book.id, user.id, loan.id,
                expected_paid_count=int(extra) if extra.isdigit() else None,
            )
            progress = await self.ctx.loans.progress(book.id, user.id, loan)
            return screens.loan_detail(book, progress)

        if action == "del":
            return screens.confirm_delete(
                f"وام «{loan.title}»", f"ln:delok:{loan.id}", f"ln:open:{loan.id}"
            )

        if action == "delok":
            await self.ctx.loans.delete(book.id, user.id, loan.id)
            return await self._loan_screen(book, user)

        return screens.stale(None, user.display_name)

    async def _save_loan(self, user, key: str, starts_on, show_detail: bool = False):
        draft = await self.ctx.state.get(key)
        if draft.get("flow") != "loan" or not draft.get("count"):
            return screens.stale(None, user.display_name)

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        loan = await self.ctx.loans.create(
            book.id, user.id, draft["title"],
            Decimal(draft["amount"]), int(draft["count"]), starts_on,
        )
        await self.ctx.state.clear(key)
        if show_detail:
            # A pressed count commits a start date nobody typed, so it lands on
            # the one screen that prints that date back. The list does not, and
            # a default worth having is a default that can be seen.
            progress = await self.ctx.loans.progress(book.id, user.id, loan)
            return screens.loan_detail(book, progress)
        return await self._loan_screen(book, user)

    @staticmethod
    def _read_count(text: str):
        """(count, None) or (None, why). One reader for the buttons and the
        typed line, so both refuse the same things for the same reason."""
        digits = to_ascii_digits(text).strip()
        if not digits.isdigit() or int(digits) <= 0:
            return None, "تعداد اقساط باید یک عدد صحیح بیشتر از صفر باشد؛ مثلاً 24."
        return int(digits), None

    @staticmethod
    def _budget_label(draft: dict) -> str:
        """What the budget is for, in words. The raw target of a flow budget is
        the enum value «expense», which is not something to show a person."""
        if draft.get("kind") == BudgetKind.FLOW.value:
            return "درآمدها" if draft.get("target") == Flow.INCOME.value else "هزینه‌ها"
        return draft.get("target") or ""

    async def _budget_text(self, text: str, draft: dict, user, key: str):
        parent = self._parent("bg", draft["book_id"])
        if not draft.get("target"):
            try:
                target = self.ctx.categories.name(text)
            except ValidationError as exc:
                return screens.budget_ask_target(cancel_data=parent, problem=str(exc))
            # Snapped to the book's own spelling where it has one: status
            # compares the target with a transaction's category by exact
            # equality, so a stray half space is a budget stuck at 0%.
            matched = self._match_offered(target, draft.get("offered") or [])
            draft["target"] = matched[0] if matched else target
            await self.ctx.state.set(key, draft)
            return screens.budget_ask_amount(self._budget_label(draft), cancel_data=parent)

        amount, problem = read_amount(text)
        if problem:
            return screens.budget_ask_amount(
                self._budget_label(draft), problem, cancel_data=parent
            )

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        await self.ctx.budgets.set_budget(
            book.id, user.id, BudgetKind(draft["kind"]), draft["target"], amount
        )
        await self.ctx.state.clear(key)
        return await self._budget_screen(book, user)

    async def _debt_text(self, text: str, draft: dict, user, key: str):
        parent = self._parent("dt", draft["book_id"])
        if not draft.get("person"):
            draft["person"] = text[:80]
            await self.ctx.state.set(key, draft)
            if not draft.get("direction"):
                return screens.debt_pick_direction(draft["person"], cancel_data=parent)
            return screens.debt_ask_amount(cancel_data=parent, person=draft["person"])

        if not draft.get("direction"):
            return screens.debt_pick_direction(
                draft["person"], "برای ادامه یکی از دو دکمهٔ زیر را بزن.", cancel_data=parent
            )

        if not draft.get("amount"):
            amount, problem = read_amount(text)
            if problem:
                return screens.debt_ask_amount(
                    problem, cancel_data=parent, person=draft["person"]
                )
            draft["amount"] = str(amount)
            await self.ctx.state.set(key, draft)
            return screens.debt_ask_due(cancel_data=parent)

        # The prompt used to tell people to type «ندارد» and then refuse it.
        if text.strip() in NO_DUE_WORDS:
            return await self._save_debt(user, key, None)
        due = parse_date(text, self.ctx.today(user))
        if due is None:
            return screens.debt_ask_due(cancel_data=parent, problem=self._bad_date(text))
        return await self._save_debt(user, key, due)

    async def _loan_text(self, text: str, draft: dict, user, key: str):
        parent = self._parent("ln", draft["book_id"])
        if not draft.get("title"):
            draft["title"] = text[:80]
            await self.ctx.state.set(key, draft)
            return screens.loan_ask_amount(draft["title"], cancel_data=parent)

        if not draft.get("amount"):
            amount, problem = read_amount(text)
            if problem:
                return screens.loan_ask_amount(draft["title"], problem, cancel_data=parent)
            draft["amount"] = str(amount)
            await self.ctx.state.set(key, draft)
            return screens.loan_ask_count(draft["title"], cancel_data=parent)

        if not draft.get("count"):
            count, problem = self._read_count(text)
            if problem:
                return screens.loan_ask_count(draft["title"], problem, cancel_data=parent)
            draft["count"] = count
            await self.ctx.state.set(key, draft)
            # Typed rather than pressed, which is how one says the first
            # instalment is not today.
            return screens.loan_ask_start(cancel_data=parent)

        starts_on = parse_date(text, self.ctx.today(user))
        if starts_on is None:
            return screens.loan_ask_start(cancel_data=parent, problem=self._bad_date(text))
        return await self._save_loan(user, key, starts_on)

    async def _recurring_text(self, text: str, draft: dict, user, key: str):
        parent = self._parent("rr", draft["book_id"])
        if not draft.get("category"):
            try:
                draft["category"] = self.ctx.categories.name(text)
            except ValidationError as exc:
                return screens.recurring_ask_category(
                    str(exc), draft.get("offered") or [], cancel_data=parent
                )
            # A name the book already knows brings its own flow with it, so the
            # flow is only asked about a category that is genuinely new.
            matched = self._match_offered(draft["category"], draft.get("offered") or [])
            if matched and matched[1]:
                draft["category"], draft["direction"] = matched
            await self.ctx.state.set(key, draft)
            if not draft.get("direction"):
                return screens.recurring_pick_flow(cancel_data=parent)
            return screens.recurring_ask_amount(draft["category"], cancel_data=parent)

        if not draft.get("direction"):
            return screens.recurring_pick_flow(cancel_data=parent)

        if not draft.get("amount"):
            amount, problem = read_amount(text)
            if problem:
                return screens.recurring_ask_amount(
                    draft["category"], problem, cancel_data=parent
                )
            draft["amount"] = str(amount)
            # Monthly unless the next screen is told otherwise: rent, wages and
            # a subscription are all monthly, and that screen prints the period
            # it is about to use.
            draft.setdefault("period", RecurringPeriod.MONTHLY.value)
            await self.ctx.state.set(key, draft)
            return screens.recurring_ask_start(cancel_data=parent, period=draft["period"])

        if not draft.get("period"):
            return screens.recurring_pick_period(
                "برای ادامه یکی از دکمه‌های زیر را بزن.", cancel_data=parent
            )

        starts_on = parse_date(text, self.ctx.today(user))
        if starts_on is None:
            return screens.recurring_ask_start(
                cancel_data=parent, problem=self._bad_date(text), period=draft["period"]
            )
        return await self._save_recurring(user, key, starts_on)

    async def _reminder_text(self, text: str, draft: dict, user, key: str):
        digits = to_ascii_digits(text).strip()
        hour = draft["field"] == "hour"
        if not digits.isdigit():
            problem = f"«{text[:30]}» عدد نیست. فقط یک عدد بنویس."
            return screens.ask_hour(problem) if hour else screens.ask_days(problem)

        value = int(digits)
        if hour:
            if value > 23:
                return screens.ask_hour("ساعت باید بین 0 تا 23 باشد.")
            user.digest_hour = value
        else:
            user.reminder_days = min(value, 60)

        await self.ctx.session.flush()
        await self.ctx.state.clear(key)
        return screens.reminder_settings(user)
