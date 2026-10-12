"""Payroll and treasury in the bot: periods, shares, performance, adjustments, payslips, funds.

The heaviest part of the bot and the one teams use least often, which is why it
lives on its own: nothing here is reachable from a personal book's flows.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from ...modules.books.models import CostPolicy, Permission
from ...modules.payroll.models import (
    AdjustmentKind,
    AdjustmentMode,
    ShareBasis,
)
from ...modules.treasury.models import FundKind, RuleBasis
from ...shared import jalali
from ...shared.errors import NotFound
from ...shared.parsing import parse_amount, parse_date, to_ascii_digits
from .. import screens
from .base import Feature


class PayrollFeature(Feature):
    prefixes = ("pr", "tf", "sh", "pf")
    flows = ("period_date", "fund", "rule", "payslip", "share", "performance", "adjustment")

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""
        if area == "pr":
            return await self._payroll_callback(action, argument, user, key)
        if area == "tf":
            return await self._treasury_callback(action, argument, user, key)
        if area == "sh":
            return await self._share_callback(action, argument, user, key)
        if area == "pf":
            return await self._performance_callback(action, argument, user, key)
        raise AssertionError(area)

    async def text(self, text, draft, user, key, event):
        if draft.get("flow") == "period_date":
            return await self._period_date_text(text, draft, user, key)
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
        raise AssertionError(draft.get("flow"))

    # ---------------------------------------------------------- treasury
    async def _fund_screen(self, book, user):
        """Every fund with what it has actually taken, not what it might."""
        funds = await self.ctx.treasury.funds(book.id, user.id)
        rows = [
            (fund, await self.ctx.treasury.balance(book.id, user.id, fund.id))
            for fund in funds
        ]
        return screens.fund_list(book, rows)

    async def _fund_detail(self, book, user, fund):
        rules = await self.ctx.treasury.rules(book.id, user.id, fund.id)
        balance = await self.ctx.treasury.balance(book.id, user.id, fund.id)
        return screens.fund_detail(book, fund, rules, balance)

    async def _treasury_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.clear(key)
            return await self._fund_screen(book, user)

        if action == "add":
            await self.ctx.state.set(key, {"flow": "fund", "book_id": argument})
            return screens.fund_ask_name()

        if action == "cp":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.books.require(book.id, user.id, Permission.MANAGE_TREASURY)
            await self.ctx.state.set(key, {"flow": "costpolicy", "book_id": argument})
            return screens.cost_policy_pick(book)

        if action == "cpset":
            # The book comes from state, not from the button: the permission
            # was checked against that book when the picker was opened.
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "costpolicy":
                return screens.stale(None, user.display_name)

            book = await self.ctx.books.set_cost_policy(
                user.id, uuid.UUID(draft["book_id"]), CostPolicy(argument)
            )
            await self.ctx.state.clear(key)
            return await self._fund_screen(book, user)

        if action == "kind":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "fund" or not draft.get("name"):
                return screens.stale(None, user.display_name)

            book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
            await self.ctx.treasury.create_fund(
                book.id, user.id, draft["name"], FundKind(argument)
            )
            await self.ctx.state.clear(key)
            return await self._fund_screen(book, user)

        if action == "basis":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "rule":
                return screens.stale(None, user.display_name)

            draft["basis"] = argument
            await self.ctx.state.set(key, draft)
            return screens.rule_ask_value(argument)

        # Everything below acts on something already in the database, so the
        # book comes from that record rather than from the callback — a book id
        # in a button is a book id someone can edit.
        if action in ("rtog", "rdel"):
            from ...modules.treasury.models import TreasuryRule

            rule = await self.ctx.session.get(TreasuryRule, uuid.UUID(argument))
            if rule is None:
                return screens.error("این قاعده دیگر وجود ندارد؛ شاید حذف شده است.")

            book = await self.ctx.books.get_book(rule.book_id)
            fund_id = rule.fund_id
            if action == "rtog":
                await self.ctx.treasury.toggle_rule(book.id, user.id, rule.id)
            else:
                await self.ctx.treasury.delete_rule(book.id, user.id, rule.id)

            fund = await self.ctx.treasury.get_fund(book.id, user.id, fund_id)
            return await self._fund_detail(book, user, fund)

        from ...modules.treasury.models import TreasuryFund

        fund = await self.ctx.session.get(TreasuryFund, uuid.UUID(argument))
        if fund is None:
            return screens.error("این صندوق دیگر وجود ندارد؛ شاید حذف شده است.")
        book = await self.ctx.books.get_book(fund.book_id)

        if action == "open":
            return await self._fund_detail(book, user, fund)

        if action == "rule":
            await self.ctx.state.set(
                key, {"flow": "rule", "book_id": str(book.id), "fund_id": str(fund.id)}
            )
            return screens.rule_pick_basis(fund.name)

        if action == "tog":
            await self.ctx.treasury.toggle_fund(book.id, user.id, fund.id)
            return await self._fund_detail(book, user, fund)

        if action == "del":
            await self.ctx.treasury.delete_fund(book.id, user.id, fund.id)
            return await self._fund_screen(book, user)

        return screens.stale(None, user.display_name)

    async def _period_list_screen(self, book, user):
        periods = await self.ctx.payroll.periods(book.id, user.id)
        year, month, _ = jalali.to_parts(self.ctx.today(user))
        return screens.period_list(book, periods, f"{jalali.month_name(month)} {year}")

    @staticmethod
    def _month_end(day: date) -> date:
        """The last day of the Jalali month the given day falls in."""
        year, month, _ = jalali.to_parts(day)
        return jalali.month_range(year, month)[1]

    async def _period_date_text(self, text: str, draft: dict, user, key: str):
        period = await self.ctx.payroll.get_period(uuid.UUID(draft["period_id"]))
        book = await self.ctx.books.get_book(period.book_id)
        which = draft["which"]

        on = parse_date(text, self.ctx.today(user))
        if on is None:
            return screens.period_ask_date(period, which)

        await self.ctx.payroll.reschedule_period(
            user.id, period.id,
            starts_on=on if which == "start" else None,
            ends_on=on if which == "end" else None,
        )
        await self.ctx.state.clear(key)
        return await self._period_detail(book, user, period)

    async def _period_detail(self, book, user, period):
        distribution = await self.ctx.payroll.compute_distribution(period.id)
        slips = await self.ctx.payroll.payslips(user.id, period.id)
        # A payslip froze the numbers it was built from. If the period has
        # moved since, saying so beats leaving somebody to read a stale figure
        # as a current one.
        stale = any(
            slip.distributable_snapshot != distribution.distributable for slip in slips
        )
        return screens.period_detail(book, period, distribution, slips, stale)

    async def _payroll_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.clear(key)
            return await self._period_list_screen(book, user)

        if action == "new":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            today = self.ctx.today(user)
            year, month, _ = jalali.to_parts(today)
            start, end = jalali.month_range(year, month)
            period = await self.ctx.payroll.open_period(
                user.id, book.id, f"{jalali.month_name(month)} {year}", start, end
            )
            await self.ctx.state.clear(key)
            return await self._period_detail(book, user, period)

        if action == "uncalc":
            period = await self.ctx.payroll.get_period(uuid.UUID(argument))
            book = await self.ctx.books.get_book(period.book_id)
            await self.ctx.payroll.discard_calculation(user.id, period.id)
            await self.ctx.state.clear(key)
            return await self._period_detail(book, user, period)

        if action in ("dates", "dstart", "dend", "dmonth"):
            period = await self.ctx.payroll.get_period(uuid.UUID(argument))
            book = await self.ctx.books.get_book(period.book_id)
            await self.ctx.books.require(book.id, user.id, Permission.MANAGE_PAYROLL)

            if action == "dates":
                await self.ctx.state.clear(key)
                return screens.period_dates(book, period, self._month_end(period.starts_on))

            if action == "dmonth":
                await self.ctx.payroll.reschedule_period(
                    user.id, period.id, ends_on=self._month_end(period.starts_on)
                )
                return await self._period_detail(book, user, period)

            await self.ctx.state.set(key, {
                "flow": "period_date", "period_id": argument,
                "which": "start" if action == "dstart" else "end",
            })
            return screens.period_ask_date(period, "start" if action == "dstart" else "end")

        if action == "del":
            period = await self.ctx.payroll.get_period(uuid.UUID(argument))
            book = await self.ctx.books.get_book(period.book_id)
            await self.ctx.payroll.delete_period(user.id, period.id)
            await self.ctx.state.clear(key)
            return await self._period_list_screen(book, user)

        if action == "unpay":
            slip = await self.ctx.payroll.void_payment(user.id, uuid.UUID(argument))
            book = await self.ctx.books.get_book(slip.book_id)
            person = await self.ctx.identity.get_user(slip.user_id)
            await self.ctx.state.clear(key)
            return screens.payslip_detail(book, slip, person.display_name)

        if action == "pcur":
            # Carries a currency code rather than a payslip id, so it is
            # answered before anything tries to read one.
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "payslip":
                return screens.stale(None, user.display_name)
            return await self._pay_in(draft, argument, user, key)

        if action in ("slip", "pay", "payall"):
            return await self._payslip_action(action, argument, user, key)

        if action in ("adjok", "adjwho", "adjadd", "adjnoreason"):
            return await self._adjustment_action(action, argument, user, key)

        period = await self.ctx.payroll.get_period(uuid.UUID(argument))
        book = await self.ctx.books.get_book(period.book_id)

        if action == "open":
            await self.ctx.state.clear(key)
            return await self._period_detail(book, user, period)

        if action == "calc":
            if not await self.ctx.payroll.shares(book.id, user.id, period.ends_on):
                # Zero payslips because nobody has a share is an unanswered
                # question, not an empty result.
                await self.ctx.state.set(key, {"flow": "share", "book_id": str(book.id)})
                return screens.no_shares_defined(book, period)

            await self.ctx.payroll.calculate(user.id, period.id)
            return await self._period_detail(book, user, period)

        if action == "slips":
            slips = await self.ctx.payroll.payslips(user.id, period.id)
            return screens.payslip_list(book, slips, await self.ctx.member_names(book.id))

        if action == "adj":
            adjustments = await self.ctx.payroll.adjustments(user.id, period.id)
            return screens.adjustment_list(
                book, period, adjustments, await self.ctx.member_names(book.id)
            )

        if action == "lock":
            return screens.confirm_close_period(period)

        if action == "lockok":
            period = await self.ctx.payroll.close_period(user.id, period.id)
            return screens.with_notice(
                "🔒 دوره بسته شد.", await self._period_detail(book, user, period)
            )

        return screens.stale(None, user.display_name)

    async def _payslip_action(self, action: str, argument: str, user, key: str):
        try:
            slip = await self.ctx.payroll.get_payslip(user.id, uuid.UUID(argument))
        except NotFound:
            return screens.error("این فیش دیگر وجود ندارد؛ شاید حذف شده است.")

        book = await self.ctx.books.get_book(slip.book_id)
        names = await self.ctx.member_names(book.id)
        name = names.get(slip.user_id, "—")
        # The payslip owns this sum: a payment made in another currency is
        # worth its amount times its rate, not its amount.
        outstanding = slip.remaining

        if action == "slip":
            await self.ctx.state.clear(key)
            return screens.payslip_detail(book, slip, name)

        if action in ("payall", "pay") and outstanding <= 0:
            # A button from an older screen. Since it was drawn the slip was
            # settled, or recalculated below what had been paid; show it as
            # it is now rather than try to pay a negative amount.
            await self.ctx.state.clear(key)
            return screens.payslip_detail(book, slip, name)

        if action in ("payall", "pay"):
            # "Pay all" is the common case by a long way: someone was paid what
            # they were owed, and typing the number again is a chance to
            # mistype it.
            draft = {"flow": "payslip", "slip_id": argument,
                     "owed": str(outstanding), "whole": action == "payall"}
            codes = await self.ctx.exchange.allowed(book.id)
            if action == "pay":
                await self.ctx.state.set(key, draft)
                return screens.payslip_ask_amount(name, outstanding, book.base_currency)
            if len(codes) > 1:
                await self.ctx.state.set(key, draft)
                return screens.payslip_pick_currency(name, outstanding,
                                                     book.base_currency, codes)
            await self.ctx.payroll.pay_towards(user.id, slip.id)
            await self.ctx.session.refresh(slip)
            return screens.payslip_detail(book, slip, name)

        return screens.stale(None, user.display_name)

    async def _adjustment_action(self, action: str, argument: str, user, key: str):
        from ...modules.payroll.models import Adjustment

        if action == "adjadd":
            period = await self.ctx.payroll.get_period(uuid.UUID(argument))
            book = await self.ctx.books.get_book(period.book_id)
            await self.ctx.state.set(
                key, {"flow": "adjustment", "period_id": argument}
            )
            return screens.adjustment_pick_member(
                period, await self.ctx.books.members(book.id), await self.ctx.member_names(book.id)
            )

        if action == "adjwho":
            draft = await self.ctx.state.get(key)
            if draft.get("flow") != "adjustment":
                return screens.stale(None, user.display_name)

            draft["user_id"] = argument
            await self.ctx.state.set(key, draft)
            period = await self.ctx.payroll.get_period(uuid.UUID(draft["period_id"]))
            names = await self.ctx.member_names(period.book_id)
            return screens.adjustment_ask_value(names.get(uuid.UUID(argument), "—"))

        if action == "adjnoreason":
            return await self._save_adjustment(user, key, reason=None)

        if action == "adjok":
            adjustment = await self.ctx.session.get(Adjustment, uuid.UUID(argument))
            if adjustment is None:
                return screens.error("این مورد دیگر وجود ندارد؛ شاید حذف شده است.")

            await self.ctx.payroll.approve_adjustment(user.id, adjustment.id)
            period = await self.ctx.payroll.get_period(adjustment.period_id)
            book = await self.ctx.books.get_book(period.book_id)
            return screens.adjustment_list(
                book, period,
                await self.ctx.payroll.adjustments(user.id, period.id),
                await self.ctx.member_names(book.id),
            )

        return screens.stale(None, user.display_name)

    async def _save_adjustment(self, user, key: str, reason):
        draft = await self.ctx.state.get(key)
        if draft.get("flow") != "adjustment" or "value" not in draft:
            return screens.stale(None, user.display_name)

        period = await self.ctx.payroll.get_period(uuid.UUID(draft["period_id"]))
        book = await self.ctx.books.get_book(period.book_id)

        value = Decimal(draft["value"])
        # The sign already says which it is, so asking the person to pick a
        # kind as well would be asking the same question twice.
        kind = AdjustmentKind.BONUS if value > 0 else AdjustmentKind.PENALTY

        await self.ctx.payroll.add_adjustment(
            user.id, period.id, uuid.UUID(draft["user_id"]),
            kind, AdjustmentMode.AMOUNT, value, reason=reason,
        )
        await self.ctx.state.clear(key)
        return screens.adjustment_list(
            book, period,
            await self.ctx.payroll.adjustments(user.id, period.id),
            await self.ctx.member_names(book.id),
        )

    async def _fund_text(self, text: str, draft: dict, user, key: str):
        draft["name"] = text[:80]
        await self.ctx.state.set(key, draft)
        return screens.fund_pick_kind(draft["name"])

    async def _rule_text(self, text: str, draft: dict, user, key: str):
        basis = draft.get("basis")
        if not basis:
            return screens.stale(None, user.display_name)

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

        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        fund = await self.ctx.treasury.get_fund(
            book.id, user.id, uuid.UUID(draft["fund_id"])
        )
        await self.ctx.treasury.add_rule(
            book.id, user.id, fund.id, RuleBasis(basis), value
        )
        await self.ctx.state.clear(key)
        return await self._fund_detail(book, user, fund)

    async def _pay_in(self, draft: dict, code: str, user, key: str, rate=None):
        """Settle a payslip in one of the book's currencies."""
        slip = await self.ctx.payroll.get_payslip(user.id, uuid.UUID(draft["slip_id"]))
        book = await self.ctx.books.get_book(slip.book_id)
        names = await self.ctx.member_names(book.id)
        name = names.get(slip.user_id, "—")

        if code == book.base_currency:
            rate = Decimal("1")
        elif rate is None:
            rate = await self.ctx.exchange.quote(code, book.base_currency)
            if rate is None:
                # No live price, so the person supplies one rather than the
                # book inventing a rate for money that changed hands.
                draft["currency"] = code
                draft["awaiting"] = "rate"
                await self.ctx.state.set(key, draft)
                return screens.payslip_ask_rate(code, book.base_currency)

        # How much of which currency that is, the service decides: the API
        # pays the same payslip through the same arithmetic.
        worth = None if draft.get("whole") else Decimal(draft["amount"])
        await self.ctx.payroll.pay_towards(user.id, slip.id, worth, currency=code,
                                           conversion_rate=rate)
        await self.ctx.state.clear(key)
        await self.ctx.session.refresh(slip, attribute_names=["payments"])
        return screens.payslip_detail(book, slip, name)

    async def _payslip_text(self, text: str, draft: dict, user, key: str):
        amount = parse_amount(text)
        try:
            slip = await self.ctx.payroll.get_payslip(user.id, uuid.UUID(draft["slip_id"]))
        except NotFound:
            await self.ctx.state.clear(key)
            return screens.error("این فیش دیگر وجود ندارد؛ شاید حذف شده است.")

        book = await self.ctx.books.get_book(slip.book_id)
        names = await self.ctx.member_names(book.id)
        name = names.get(slip.user_id, "—")
        outstanding = slip.remaining

        if draft.get("awaiting") == "rate":
            rate = parse_amount(text)
            if rate is None or rate <= 0:
                return screens.payslip_ask_rate(draft["currency"], book.base_currency)
            return await self._pay_in(draft, draft["currency"], user, key, rate)

        if amount is None or amount <= 0:
            return screens.payslip_ask_amount(name, outstanding, book.base_currency)

        codes = await self.ctx.exchange.allowed(book.id)
        if len(codes) > 1:
            draft["amount"] = str(amount)
            draft["whole"] = False
            await self.ctx.state.set(key, draft)
            return screens.payslip_pick_currency(name, amount, book.base_currency, codes)

        await self.ctx.payroll.pay(user.id, slip.id, amount)
        await self.ctx.session.refresh(slip)
        await self.ctx.state.clear(key)
        return screens.payslip_detail(book, slip, name)

    async def _adjustment_text(self, text: str, draft: dict, user, key: str):
        if "user_id" not in draft:
            return screens.stale(None, user.display_name)

        # A deduction is a negative number, and the amount parser only reads
        # magnitudes — so the sign has to be taken off the front first.
        cleaned = to_ascii_digits(text).strip()
        negative = cleaned.startswith("-")
        amount = parse_amount(cleaned.lstrip("-+").strip())

        if amount is None or amount <= 0:
            period = await self.ctx.payroll.get_period(uuid.UUID(draft["period_id"]))
            names = await self.ctx.member_names(period.book_id)
            return screens.adjustment_ask_value(names.get(uuid.UUID(draft["user_id"]), "—"))

        draft["value"] = str(-amount if negative else amount)
        await self.ctx.state.set(key, draft)
        return screens.adjustment_ask_reason()

    # ------------------------------------------------------------- shares
    async def _share_screen(self, book, user):
        return screens.share_list(
            book,
            await self.ctx.books.members(book.id),
            await self.ctx.member_names(book.id),
            await self.ctx.payroll.shares(book.id, user.id),
        )

    async def _share_book(self, user, key: str):
        """Which book this flow is about. Held in state, never in the button."""
        draft = await self.ctx.state.get(key)
        if not draft.get("book_id"):
            return None, draft
        return await self.ctx.books.get_book(uuid.UUID(draft["book_id"])), draft

    async def _share_callback(self, action: str, argument: str, user, key: str):
        if action == "open":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            await self.ctx.state.set(key, {"flow": "share", "book_id": argument})
            return await self._share_screen(book, user)

        book, draft = await self._share_book(user, key)
        if book is None:
            return screens.stale(None, user.display_name)

        if action == "list":
            await self.ctx.state.set(key, {"flow": "share", "book_id": str(book.id)})
            return await self._share_screen(book, user)

        if action == "set":
            draft["user_id"] = argument
            await self.ctx.state.set(key, draft)
            rules = await self.ctx.payroll.shares(book.id, user.id)
            names = await self.ctx.member_names(book.id)
            return screens.share_pick_basis(
                names.get(uuid.UUID(argument), "—"), rules.get(uuid.UUID(argument))
            )

        if action == "basis":
            if "user_id" not in draft:
                return await self._share_screen(book, user)
            draft["basis"] = argument
            await self.ctx.state.set(key, draft)
            names = await self.ctx.member_names(book.id)
            return screens.share_ask_value(
                names.get(uuid.UUID(draft["user_id"]), "—"), argument
            )

        if action == "clear":
            if "user_id" in draft:
                await self.ctx.payroll.clear_share(
                    book.id, user.id, uuid.UUID(draft["user_id"])
                )
            await self.ctx.state.set(key, {"flow": "share", "book_id": str(book.id)})
            return await self._share_screen(book, user)

        return await self._share_screen(book, user)

    async def _share_text(self, text: str, draft: dict, user, key: str):
        basis = draft.get("basis")
        book = await self.ctx.books.get_book(uuid.UUID(draft["book_id"]))
        if not basis or "user_id" not in draft:
            return await self._share_screen(book, user)

        names = await self.ctx.member_names(book.id)
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

        await self.ctx.payroll.set_share(
            book.id, user.id, uuid.UUID(draft["user_id"]), ShareBasis(basis), value
        )
        await self.ctx.state.set(key, {"flow": "share", "book_id": str(book.id)})
        return await self._share_screen(book, user)

    # --------------------------------------------------------- performance
    async def _performance_screen(self, book, user, period):
        return screens.performance_list(
            book, period,
            await self.ctx.books.members(book.id),
            await self.ctx.member_names(book.id),
            await self.ctx.payroll.performance(user.id, period.id),
            await self.ctx.payroll.shares(book.id, user.id, period.ends_on),
        )

    async def _performance_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            period = await self.ctx.payroll.get_period(uuid.UUID(argument))
            book = await self.ctx.books.get_book(period.book_id)
            await self.ctx.state.set(
                key, {"flow": "performance", "period_id": argument}
            )
            return await self._performance_screen(book, user, period)

        draft = await self.ctx.state.get(key)
        if not draft.get("period_id"):
            return screens.stale(None, user.display_name)

        period = await self.ctx.payroll.get_period(uuid.UUID(draft["period_id"]))
        book = await self.ctx.books.get_book(period.book_id)

        if action == "set":
            draft["user_id"] = argument
            await self.ctx.state.set(key, draft)
            rules = await self.ctx.payroll.shares(book.id, user.id, period.ends_on)
            names = await self.ctx.member_names(book.id)
            rule = rules.get(uuid.UUID(argument))
            return screens.performance_ask_value(
                names.get(uuid.UUID(argument), "—"),
                rule.basis.value if rule else "hours",
            )

        return await self._performance_screen(book, user, period)

    async def _performance_text(self, text: str, draft: dict, user, key: str):
        period = await self.ctx.payroll.get_period(uuid.UUID(draft["period_id"]))
        book = await self.ctx.books.get_book(period.book_id)
        if "user_id" not in draft:
            return await self._performance_screen(book, user, period)

        member_id = uuid.UUID(draft["user_id"])
        rules = await self.ctx.payroll.shares(book.id, user.id, period.ends_on)
        rule = rules.get(member_id)
        basis = rule.basis.value if rule else "hours"

        try:
            value = Decimal(to_ascii_digits(text).strip())
        except Exception:
            value = None

        if value is None or value < 0:
            names = await self.ctx.member_names(book.id)
            return screens.performance_ask_value(names.get(member_id, "—"), basis)

        column = {"hours": "hours_worked", "days": "days_worked", "points": "points"}[basis]
        await self.ctx.payroll.record_performance(
            user.id, period.id, member_id, **{column: value}
        )
        draft.pop("user_id", None)
        await self.ctx.state.set(key, draft)
        return await self._performance_screen(book, user, period)
