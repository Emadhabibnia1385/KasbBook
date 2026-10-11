"""Planning in the bot: budgets, debts, loans, recurring rules and reminder settings.

Everything that looks ahead rather than records what happened. Each part is a
list of items per book, an add flow that asks one thing at a time, and a
confirmed delete; the rules themselves live in their services.
"""

from __future__ import annotations

import uuid
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
        if area == "bg":
            return await self._budget_callback(action, argument, user, key)
        if area == "dt":
            return await self._debt_callback(action, argument, user, key)
        if area == "ln":
            extra = parts[3] if len(parts) > 3 else ""
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

    # ------------------------------------------------------------ recurring
    async def _recurring_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.clear(key)
            rules = await self.ctx.recurring.list_rules(book.id, user.id)
            return screens.recurring_list(book, rules)

        if action == "add":
            await self.ctx.state.set(key, {"flow": "recurring", "book_id": argument})
            return screens.recurring_pick_flow()

        if action == "flow":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "recurring":
                return screens.stale(None, user.display_name)
            draft["direction"] = argument
            await self.ctx.state.set(key, draft)
            return screens.recurring_ask_category()

        if action == "period":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "recurring":
                return screens.stale(None, user.display_name)
            draft["period"] = argument
            await self.ctx.state.set(key, draft)
            return screens.recurring_ask_start()

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
            await self.ctx.state.set(key, {"flow": "budget", "book_id": argument})
            return screens.budget_pick_kind(book)

        if action == "kind":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "budget":
                return screens.stale(None, user.display_name)

            if argument == "category":
                draft["kind"] = BudgetKind.CATEGORY.value
                await self.ctx.state.set(key, draft)
                return screens.budget_ask_target()

            draft["kind"] = BudgetKind.FLOW.value
            draft["target"] = argument
            await self.ctx.state.set(key, draft)
            return screens.budget_ask_amount(self._budget_label(draft))

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

    async def _debt_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.clear(key)
            return await self._debt_screen(book, user)

        if action == "add":
            await self.ctx.state.set(key, {"flow": "debt", "book_id": argument})
            return screens.debt_ask_person()

        if action == "dir":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "debt":
                return screens.stale(None, user.display_name)
            draft["direction"] = argument
            await self.ctx.state.set(key, draft)
            return screens.debt_ask_amount()

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
            Decimal(draft["amount"]), draft.get("note"), due,
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
            return screens.loan_ask_title()

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

    async def _save_loan(self, user, key: str, starts_on):
        draft = await self.ctx.state.get(key)
        if draft.get("flow") != "loan" or not draft.get("count"):
            return screens.stale(None, user.display_name)

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        await self.ctx.loans.create(
            book.id, user.id, draft["title"],
            Decimal(draft["amount"]), int(draft["count"]), starts_on,
        )
        await self.ctx.state.clear(key)
        return await self._loan_screen(book, user)

    @staticmethod
    def _budget_label(draft: dict) -> str:
        """What the budget is for, in words. The raw target of a flow budget is
        the enum value «expense», which is not something to show a person."""
        if draft.get("kind") == BudgetKind.FLOW.value:
            return "درآمدها" if draft.get("target") == Flow.INCOME.value else "هزینه‌ها"
        return draft.get("target") or ""

    async def _budget_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("target"):
            draft["target"] = text[:80]
            await self.ctx.state.set(key, draft)
            return screens.budget_ask_amount(self._budget_label(draft))

        amount, problem = read_amount(text)
        if problem:
            return screens.budget_ask_amount(self._budget_label(draft), problem)

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        await self.ctx.budgets.set_budget(
            book.id, user.id, BudgetKind(draft["kind"]), draft["target"], amount
        )
        await self.ctx.state.clear(key)
        return await self._budget_screen(book, user)

    async def _debt_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("person"):
            draft["person"] = text[:80]
            await self.ctx.state.set(key, draft)
            return screens.debt_pick_direction(draft["person"])

        if not draft.get("direction"):
            return screens.debt_pick_direction(
                draft["person"], "برای ادامه یکی از دو دکمهٔ زیر را بزن."
            )

        if not draft.get("amount"):
            amount, problem = read_amount(text)
            if problem:
                return screens.debt_ask_amount(problem)
            draft["amount"] = str(amount)
            await self.ctx.state.set(key, draft)
            return screens.debt_ask_due()

        # The prompt used to tell people to type «ندارد» and then refuse it.
        if text.strip() in NO_DUE_WORDS:
            return await self._save_debt(user, key, None)
        due = parse_date(text, self.ctx.today(user))
        if due is None:
            return screens.debt_ask_due(text[:30])
        return await self._save_debt(user, key, due)

    async def _loan_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("title"):
            draft["title"] = text[:80]
            await self.ctx.state.set(key, draft)
            return screens.loan_ask_amount(draft["title"])

        if not draft.get("amount"):
            amount, problem = read_amount(text)
            if problem:
                return screens.loan_ask_amount(draft["title"], problem)
            draft["amount"] = str(amount)
            await self.ctx.state.set(key, draft)
            return screens.loan_ask_count()

        if not draft.get("count"):
            digits = to_ascii_digits(text).strip()
            if not digits.isdigit() or int(digits) <= 0:
                return screens.loan_ask_count("تعداد اقساط باید یک عدد صحیح بیشتر از صفر باشد؛ مثلاً 24.")
            draft["count"] = int(digits)
            await self.ctx.state.set(key, draft)
            return screens.loan_ask_start()

        starts_on = parse_date(text, self.ctx.today(user))
        if starts_on is None:
            return screens.loan_ask_start(text[:30])
        return await self._save_loan(user, key, starts_on)

    async def _recurring_text(self, text: str, draft: dict, user, key: str):
        if not draft.get("category"):
            try:
                draft["category"] = self.ctx.categories.name(text)
            except ValidationError:
                return screens.recurring_ask_category("نام دسته باید بین 1 تا 80 حرف باشد.")
            await self.ctx.state.set(key, draft)
            return screens.recurring_ask_amount(draft["category"])

        if not draft.get("amount"):
            amount, problem = read_amount(text)
            if problem:
                return screens.recurring_ask_amount(draft["category"], problem)
            draft["amount"] = str(amount)
            await self.ctx.state.set(key, draft)
            return screens.recurring_pick_period()

        if not draft.get("period"):
            return screens.recurring_pick_period("برای ادامه یکی از دکمه‌های زیر را بزن.")

        starts_on = parse_date(text, self.ctx.today(user))
        if starts_on is None:
            return screens.recurring_ask_start(text[:30])
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
