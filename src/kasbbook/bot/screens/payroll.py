"""Payroll and treasury screens: periods, shares, performance, adjustments, payslips, funds."""

from __future__ import annotations

from decimal import Decimal

from ...adapters.base import Button
from ...modules.books.models import Book, CostPolicy
from ...modules.exchange.models import CURRENCY_NAMES
from ...shared import jalali
from .common import (
    PERIOD_LABELS,
    Screen,
    fmt,
    fmt_currency,
    rtl,
)


# ---------------------------------------------------------------- treasury
COST_POLICY_LABELS = {
    "before_split": "از کل درآمد، پیش از تقسیم",
    "from_treasury": "از سهم خزانه",
}


def cost_policy_pick(book: Book) -> Screen:
    """Ask who carries the costs, in the words of what it does to people's pay."""
    return rtl(
        f"⚖️ هزینه‌های «{book.name}» از سهم چه کسی کم شود؟\n\n"
        f"قاعدهٔ فعلی: {COST_POLICY_LABELS[book.cost_policy.value]}\n\n"
        "• پیش از تقسیم: هزینه اول از درآمد کم می‌شود و باقی‌مانده بین خزانه "
        "و اعضا تقسیم می‌شود؛ یک ماه بد را همه حس می‌کنند.\n"
        "• از سهم خزانه: اعضا سهمشان را از کل درآمد می‌گیرند و هزینه‌ها همه "
        "از سهم خزانه برداشته می‌شود.\n\n"
        "دوره‌هایی که قبلاً محاسبه شده‌اند دست نمی‌خورند."
    ), [
        [Button("📉 پیش از تقسیم", data="tf:cpset:before_split")],
        [Button("🏦 از سهم خزانه", data="tf:cpset:from_treasury")],
        [Button("⬅️ انصراف", data=f"tf:list:{book.id}")],
    ]


FUND_LABELS = {
    "main": "🏦 خزانهٔ اصلی",
    "emergency": "🚨 ذخیرهٔ اضطراری",
    "tax": "🧾 مالیات",
    "development": "🌱 توسعه",
    "equipment": "🛠 تجهیزات",
    "bonus": "🎁 پاداش",
}


BASIS_LABELS = {
    "gross_percent": "٪ از درآمد ناخالص",
    "net_percent": "٪ از سود خالص",
    "fixed": "مبلغ ثابت",
}


def fund_list(book: Book, funds_with_balance) -> Screen:
    """Funds are what the team keeps before anyone is paid."""
    if not funds_with_balance:
        return rtl(
            f"🏦 خزانهٔ {book.name}\n\n"
            "هنوز صندوقی ساخته نشده.\n"
            "صندوق جایی است که پیش از تقسیم سود، سهمی کنار گذاشته می‌شود — "
            "مثل ذخیرهٔ اضطراری یا کنارگذاشتن مالیات.\n\n"
            f"قاعدهٔ هزینه: {COST_POLICY_LABELS[book.cost_policy.value]}"
        ), [
            [Button("➕ صندوق تازه", data=f"tf:add:{book.id}")],
            [Button("⚖️ تغییر قاعدهٔ هزینه", data=f"tf:cp:{book.id}")],
            [Button("⬅️ بازگشت", data=f"pr:list:{book.id}")],
        ]

    lines = [f"🏦 خزانهٔ {book.name}", ""]
    total = Decimal("0")
    for fund, balance in funds_with_balance:
        total += balance
        mark = "" if fund.is_active else " (خاموش)"
        label = FUND_LABELS.get(fund.kind.value, "🏦")
        lines.append(f"• {label} — {fund.name}{mark}\n  تاکنون: {fmt(balance, book.base_currency)}")
    lines += ["", f"مجموع کنارگذاشته‌شده: {fmt(total, book.base_currency)}"]

    lines += ["", f"قاعدهٔ هزینه: {COST_POLICY_LABELS[book.cost_policy.value]}"]

    buttons = [[Button("➕ صندوق تازه", data=f"tf:add:{book.id}")],
               [Button("⚖️ تغییر قاعدهٔ هزینه", data=f"tf:cp:{book.id}")]]
    for fund, _ in funds_with_balance[:10]:
        buttons.append([Button(f"{fund.name[:20]}", data=f"tf:open:{fund.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"pr:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def fund_ask_name() -> Screen:
    return rtl(
        "🏦 نام صندوق چیست؟\n\nمثلاً: ذخیرهٔ اضطراری، مالیات، توسعه"
    ), [[Button("⬅️ انصراف", data="nav:cancel")]]


def fund_pick_kind(name: str) -> Screen:
    return rtl(f"«{name}» از چه نوعی است؟"), [
        [Button("🏦 اصلی", data="tf:kind:main"),
         Button("🚨 اضطراری", data="tf:kind:emergency")],
        [Button("🧾 مالیات", data="tf:kind:tax"),
         Button("🌱 توسعه", data="tf:kind:development")],
        [Button("🛠 تجهیزات", data="tf:kind:equipment"),
         Button("🎁 پاداش", data="tf:kind:bonus")],
        [Button("⬅️ انصراف", data="nav:cancel")],
    ]


def fund_detail(book: Book, fund, rules, balance) -> Screen:
    label = FUND_LABELS.get(fund.kind.value, "🏦")
    lines = [
        f"{label} {fund.name}",
        "",
        f"وضعیت: {'روشن' if fund.is_active else 'خاموش'}",
        f"تاکنون کنار گذاشته: {fmt(balance, book.base_currency)}",
        "",
    ]

    if not rules:
        lines.append("هنوز قاعده‌ای ندارد، پس چیزی برنمی‌دارد.")
    else:
        lines.append("قاعده‌ها:")
        for rule in rules:
            mark = "•" if rule.is_active else "◦"
            basis = BASIS_LABELS.get(rule.basis.value, rule.basis.value)
            amount = (
                fmt(rule.value, book.base_currency)
                if rule.basis.value == "fixed" else f"{rule.value:,.0f}٪"
            )
            lines.append(f"  {mark} {amount} — {basis}")

    buttons = [[Button("➕ قاعدهٔ تازه", data=f"tf:rule:{fund.id}")]]
    for rule in rules[:6]:
        state = "خاموش کن" if rule.is_active else "روشن کن"
        buttons.append([
            Button(f"{state}: {BASIS_LABELS.get(rule.basis.value, '')[:16]}",
                   data=f"tf:rtog:{rule.id}"),
            Button("🗑", data=f"tf:rdel:{rule.id}"),
        ])
    buttons.append([
        Button("🔴 خاموش" if fund.is_active else "🟢 روشن", data=f"tf:tog:{fund.id}"),
        Button("🗑 حذف صندوق", data=f"tf:del:{fund.id}"),
    ])
    buttons.append([Button("⬅️ بازگشت", data=f"tf:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def rule_pick_basis(fund_name: str) -> Screen:
    return rtl(
        f"قاعدهٔ «{fund_name}» بر چه پایه‌ای باشد؟\n\n"
        "درصد از درآمد ناخالص: پیش از کسر هزینه‌ها.\n"
        "درصد از سود خالص: بعد از کسر هزینه‌ها.\n"
        "مبلغ ثابت: هر دوره همان عدد."
    ), [
        [Button("٪ درآمد ناخالص", data="tf:basis:gross_percent")],
        [Button("٪ سود خالص", data="tf:basis:net_percent")],
        [Button("مبلغ ثابت", data="tf:basis:fixed")],
        [Button("⬅️ انصراف", data="nav:cancel")],
    ]


def rule_ask_value(basis: str) -> Screen:
    if basis == "fixed":
        return rtl("چه مبلغی هر دوره کنار گذاشته شود؟\n\nمثلاً: 5م"), [
            [Button("⬅️ انصراف", data="nav:cancel")]
        ]
    return rtl("چند درصد؟\n\nفقط عدد بنویس. مثلاً: 10"), [
        [Button("⬅️ انصراف", data="nav:cancel")]
    ]


def period_dates(book: Book, period, month_end) -> Screen:
    """Where a period starts and ends, and the ways to move either end."""

    lines = [
        f"📅 تاریخ‌های «{period.label}»",
        "",
        f"شروع: {jalali.to_text(period.starts_on)}",
        f"پایان: {jalali.to_text(period.ends_on)}",
        "",
        "بازهٔ دوره تعیین می‌کند کدام تراکنش‌ها در آن تقسیم می‌شوند. "
        "با تغییرش فیش‌های صادرشده دوباره حساب می‌شوند.",
    ]
    buttons = [[Button("✏️ تاریخ شروع", data=f"pr:dstart:{period.id}"),
                Button("✏️ تاریخ پایان", data=f"pr:dend:{period.id}")]]
    if month_end is not None and month_end != period.ends_on:
        buttons.append([Button(
            f"📆 پایان = {jalali.to_text(month_end)} (آخر ماه شروع)",
            data=f"pr:dmonth:{period.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"pr:open:{period.id}")])
    return rtl("\n".join(lines)), buttons


def period_ask_date(period, which: str) -> Screen:
    """Ask for one end of the window, in Jalali."""

    what = "شروع" if which == "start" else "پایان"
    other = period.ends_on if which == "start" else period.starts_on
    edge = "قبل از" if which == "start" else "بعد از"
    return rtl(
        f"📅 تاریخ {what} «{period.label}» را بفرست.\n\n"
        f"مثل 1405/06/31 — باید {edge} {jalali.to_text(other)} نباشد."
    ), [[Button("⬅️ انصراف", data=f"pr:dates:{period.id}")]]


def period_list(book: Book, periods, month_label: str) -> Screen:
    """Payroll starts here: a period is the window everything is measured over."""
    if book.type.value in ("personal", "business"):
        return rtl(
            f"👥 حقوق و سهم — {book.name}\n\n"
            "این بخش برای دفترهای تیمی و سازمانی است، جایی که سود میان چند نفر "
            "تقسیم می‌شود.\n"
            "این دفتر شخصی/کسب‌وکار است و صاحبش یک نفر است."
        ), [[Button("⬅️ بازگشت", data=f"book:open:{book.id}")]]

    if not periods:
        return rtl(
            f"👥 حقوق و سهم — {book.name}\n\n"
            "هنوز دوره‌ای باز نشده.\n"
            "دوره یعنی بازه‌ای که درآمد و هزینه‌اش با هم حساب می‌شود و "
            "ته‌اش میان اعضا تقسیم می‌شود."
        ), [
            [Button(f"➕ دورهٔ {month_label}", data=f"pr:new:{book.id}")],
            [Button("🧾 سهم اعضا", data=f"sh:open:{book.id}"),
             Button("🏦 خزانه", data=f"tf:list:{book.id}")],
            [Button("⬅️ بازگشت", data=f"book:open:{book.id}")],
        ]

    lines = [f"👥 حقوق و سهم — {book.name}", ""]
    for period in periods[:12]:
        state = PERIOD_LABELS.get(period.status.value, period.status.value)
        lines.append(f"• {period.label} — {state}")

    buttons = [[Button(f"➕ دورهٔ {month_label}", data=f"pr:new:{book.id}")]]
    for period in periods[:8]:
        buttons.append([
            Button(f"{period.label} — {PERIOD_LABELS.get(period.status.value, '')}",
                   data=f"pr:open:{period.id}")
        ])
    buttons.append([
        Button("🧾 سهم اعضا", data=f"sh:open:{book.id}"),
        Button("🏦 خزانه", data=f"tf:list:{book.id}"),
    ])
    buttons.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl("\n".join(lines)), buttons


def period_detail(book: Book, period, distribution, slips=(),
                  stale: bool = False) -> Screen:
    """The whole arithmetic, shown rather than asserted.

    Every line of it is here on purpose: someone about to be paid a share of a
    number should be able to see how that number was reached.
    """
    currency = book.base_currency
    state = PERIOD_LABELS.get(period.status.value, period.status.value)
    slip_count = len(slips)
    has_payments = any(slip.payments for slip in slips)


    lines = [
        f"📅 {period.label}",
        f"بازه: {jalali.to_text(period.starts_on)} تا {jalali.to_text(period.ends_on)}",
        f"وضعیت: {state}",
        "",
        f"درآمد دوره:     {fmt(distribution.gross_income, currency)}",
        f"هزینهٔ دوره:    {fmt(distribution.direct_costs, currency)}",
        f"سود خالص:      {fmt(distribution.net_profit, currency)}",
    ]
    if distribution.treasury_total:
        lines.append(f"سهم خزانه:     {fmt(distribution.treasury_total, currency)}")
    if distribution.cost_policy is CostPolicy.FROM_TREASURY:
        # On this policy the members are paid off gross, so "سود خالص" above is
        # not what anyone divides. Saying where the cost went, and what the
        # treasury is left with, is the difference between a number someone can
        # check and a number they have to trust.
        lines.append(
            f"خالص خزانه:    {fmt(distribution.treasury_net, currency)}"
            "  (هزینه از سهم خزانه)"
        )
    lines += [
        "",
        f"قابل تقسیم:    {fmt(distribution.distributable, currency)}",
    ]
    if distribution.shortfall:
        # A losing month pays nobody. Said out loud, so a row of zero payslips
        # reads as the loss it is rather than as nothing having happened.
        lines.append(
            f"⚠️ این دوره {fmt(distribution.shortfall, currency)} زیان داده؛ "
            "چیزی برای تقسیم نمانده و سهم‌ها صفر است."
        )

    if slip_count:
        lines += ["", f"{slip_count} فیش صادر شده."]
        if has_payments:
            # What the members are still owed, and what went to them beyond
            # their share, straight from the payslips. A period keeps taking
            # entries after it pays out, so both can move after payment.
            owed = sum((slip.remaining for slip in slips if slip.remaining > 0),
                       Decimal("0"))
            over = sum((slip.overpaid for slip in slips), Decimal("0"))
            lines.append(f"مانده پرداخت: {fmt(owed, currency)}" if owed
                         else "همه پرداخت شده ✅")
            if over:
                lines.append(f"⚠️ بیش از سهم پرداخت شده: {fmt(over, currency)}")
        if stale:
            lines.append(
                "⚠️ بعد از صدور فیش‌ها چیزی در این دوره ثبت یا عوض شده؛ "
                "اعداد بالا با فیش‌ها نمی‌خوانند. دوباره حساب کن."
            )
            if has_payments:
                lines.append("پرداخت‌ها سر جایشان می‌مانند و فقط مانده عوض می‌شود.")

    buttons = []
    if period.status.value not in ("locked", "paid"):
        # Offered whether or not anyone has been paid: recalculating updates
        # each payslip in place and keeps the payments made against it.
        buttons.append([Button(
            "🧮 محاسبهٔ دوبارهٔ فیش‌ها" if slip_count else "🧮 محاسبهٔ فیش‌ها",
            data=f"pr:calc:{period.id}",
        )])
    if slip_count and not has_payments and period.status.value not in ("locked", "paid"):
        # Discarding deletes the payslips, and payments cascade with them, so
        # it is only offered while nobody has been paid.
        buttons.append([Button("♻️ باطل‌کردن محاسبه", data=f"pr:uncalc:{period.id}")])
    if period.status.value not in ("locked", "paid"):
        buttons.append([Button("📅 تاریخ‌های دوره", data=f"pr:dates:{period.id}")])
    if period.status.value not in ("locked", "paid") and not slip_count:
        # Only while it has paid nobody. Two periods covering the same day
        # divide that day's income twice, so a period made by mistake needs a
        # way out.
        buttons.append([Button("🗑 حذف دوره", data=f"pr:del:{period.id}")])
    if slip_count:
        buttons.append([Button("💵 فیش‌ها", data=f"pr:slips:{period.id}")])
    buttons.append([
        Button("➕ کسر/اضافه", data=f"pr:adj:{period.id}"),
        Button("⏱ کارکرد", data=f"pf:list:{period.id}"),
    ])
    buttons.append([
        Button("🧾 سهم اعضا", data=f"sh:open:{book.id}"),
        Button("🏦 خزانه", data=f"tf:list:{book.id}"),
    ])
    if slip_count and period.status.value != "locked":
        buttons.append([Button("🔒 بستن دوره", data=f"pr:lock:{period.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"pr:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def confirm_close_period(period) -> Screen:
    return rtl(
        f"🔒 بستن دورهٔ «{period.label}»\n\n"
        "بعد از بستن، در این بازه نه تراکنشی ثبت یا ویرایش می‌شود و نه پرداختی. "
        "این کار برگشت ندارد. مطمئنی؟"
    ), [
        [Button("🔒 بله، ببند", data=f"pr:lockok:{period.id}")],
        [Button("↩️ انصراف", data=f"pr:open:{period.id}")],
    ]


def payslip_list(book: Book, slips, names) -> Screen:
    if not slips:
        return rtl(
            "💵 هنوز فیشی صادر نشده.\n\n"
            "«محاسبهٔ فیش‌ها» را بزن تا سهم هر نفر حساب شود."
        ), [[Button("⬅️ بازگشت", data="nav:home")]]

    currency = book.base_currency
    lines = ["💵 فیش‌های این دوره", ""]
    total = owed = Decimal("0")
    for slip in slips:
        total += slip.net_pay
        if slip.overpaid:
            mark, note = "🔴", f" — بیش‌پرداخت {fmt(slip.overpaid, currency)}"
        elif slip.is_settled:
            mark, note = "✅", ""
        elif slip.payments:
            mark, note = "🟡", f" — مانده {fmt(slip.remaining, currency)}"
        else:
            mark, note = "⚪️", ""
        if slip.remaining > 0:
            owed += slip.remaining
        lines.append(
            f"{mark} {names.get(slip.user_id, '—')}: {fmt(slip.net_pay, currency)}{note}"
        )
    lines += ["", f"مجموع: {fmt(total, currency)}"]
    if owed and any(slip.payments for slip in slips):
        lines.append(f"مانده پرداخت: {fmt(owed, currency)}")

    buttons = [
        [Button(f"{names.get(slip.user_id, '—')[:18]}", data=f"pr:slip:{slip.id}")]
        for slip in slips[:10]
    ]
    buttons.append([Button("⬅️ بازگشت", data=f"pr:open:{slips[0].period_id}")])
    return rtl("\n".join(lines)), buttons


def _payment_amount(payment, base: str) -> str:
    """A payment in the currency it was made in.

    The payslip's own currency is written the way the rest of the payslip
    writes it; a token keeps its name and its decimals, because 11.35 tether
    shown as "11" loses real money.
    """
    if payment.currency == base:
        return fmt(payment.amount, base)
    return fmt_currency(payment.amount, payment.currency)


def payslip_detail(book: Book, slip, name: str) -> Screen:
    """One person's slip, with every input that produced it."""
    currency = book.base_currency
    outstanding = slip.remaining

    basis = {
        "percent": "درصدی",
        "shares": "سهمی",
        "fixed": "ثابت",
    }.get(slip.share_basis_snapshot.value, slip.share_basis_snapshot.value)

    lines = [
        f"💵 فیش {name}",
        "",
        f"قابل تقسیم دوره: {fmt(slip.distributable_snapshot, currency)}",
        f"پایهٔ سهم:       {basis} ({slip.share_value_snapshot:,.0f})",
        f"سهم پایه:        {fmt(slip.base_share, currency)}",
    ]
    if slip.adjustments_total:
        sign = "+" if slip.adjustments_total > 0 else ""
        lines.append(f"کسر و اضافه:     {sign}{fmt(slip.adjustments_total, currency)}")
    lines += [
        "",
        f"خالص پرداختی:   {fmt(slip.net_pay, currency)}",
    ]

    if slip.payments:

        lines += ["", "پرداخت‌ها:"]
        for payment in slip.payments:
            # In the currency it was paid in. Written in the payslip's own,
            # forty tethers read as "40 IRT" — and the list no longer added up
            # to what the payslip said had been paid.
            paid = _payment_amount(payment, currency)
            if payment.currency != currency:
                worth = payment.amount * payment.conversion_rate
                paid += f" (≈ {fmt(worth, currency)})"
            lines.append(f"  • {paid} — {jalali.to_text(payment.paid_on)}")
        lines += ["", f"پرداخت‌شده: {fmt(slip.paid_total, currency)}"]
        if slip.overpaid:
            lines.append(f"⚠️ بیش از سهم پرداخت شده: {fmt(slip.overpaid, currency)}")
            lines.append(
                "سهم بعد از پرداخت کم شد. اگر قرار است برگردد، "
                "در دورهٔ بعد به‌صورت کسر ثبتش کن."
            )
        elif outstanding > 0:
            lines.append(f"مانده: {fmt(outstanding, currency)}")
        else:
            lines.append("کامل پرداخت شده ✅")

    buttons = []
    if outstanding > 0:
        buttons.append([
            Button(f"💵 پرداخت کامل ({fmt(outstanding, currency)})",
                   data=f"pr:payall:{slip.id}")
        ])
        buttons.append([Button("✏️ پرداخت جزئی", data=f"pr:pay:{slip.id}")])
    if slip.payments:
        # A figure typed wrongly, or against the wrong person, was permanent.
        last = slip.payments[-1]
        buttons.append([Button(
            f"↩️ برگرداندن آخرین پرداخت ({_payment_amount(last, currency)})",
            data=f"pr:unpay:{last.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"pr:slips:{slip.period_id}")])
    return rtl("\n".join(lines)), buttons


def payslip_ask_amount(name: str, outstanding: Decimal, currency: str) -> Screen:
    return rtl(
        f"چقدر به {name} پرداخت شد؟\n\n"
        f"مانده: {fmt(outstanding, currency)}\n"
        "مثلاً: 5م"
    ), [[Button("⬅️ انصراف", data="nav:cancel")]]


def adjustment_list(book: Book, period, adjustments, names) -> Screen:
    """Bonuses and deductions, before the slips are calculated."""
    lines = [f"➕ کسر و اضافهٔ {period.label}", ""]

    if not adjustments:
        lines.append(
            "چیزی ثبت نشده.\n"
            "پاداش، جریمه یا هر تعدیل دیگری را این‌جا اضافه کن؛ "
            "در محاسبهٔ بعدی روی فیش‌ها می‌نشیند."
        )
    else:
        for adjustment in adjustments:
            sign = "+" if adjustment.value > 0 else ""
            mark = "✅" if adjustment.approved_at else "⏳"
            unit = "٪" if adjustment.mode.value == "percent" else ""
            lines.append(
                f"{mark} {names.get(adjustment.user_id, '—')}: "
                f"{sign}{adjustment.value:,.0f}{unit} — {adjustment.reason or '—'}"
            )

    buttons = [[Button("➕ افزودن", data=f"pr:adjadd:{period.id}")]]
    for adjustment in adjustments[:8]:
        if not adjustment.approved_at:
            buttons.append([
                Button(f"✅ تأیید: {names.get(adjustment.user_id, '—')[:14]}",
                       data=f"pr:adjok:{adjustment.id}")
            ])
    buttons.append([Button("⬅️ بازگشت", data=f"pr:open:{period.id}")])
    return rtl("\n".join(lines)), buttons


def adjustment_pick_member(period, members, names) -> Screen:
    return rtl("کسر یا اضافه برای چه کسی؟"), [
        *[[Button(names.get(m.user_id, "—")[:20], data=f"pr:adjwho:{m.user_id}")]
          for m in members[:10]],
        [Button("⬅️ انصراف", data=f"pr:adj:{period.id}")],
    ]


def adjustment_ask_value(name: str) -> Screen:
    return rtl(
        f"چه مبلغی برای {name}؟\n\n"
        "برای پاداش عدد مثبت، برای کسر عدد منفی بنویس.\n"
        "مثلاً: 2م یا ‎-500ک"
    ), [[Button("⬅️ انصراف", data="nav:cancel")]]


def adjustment_ask_reason() -> Screen:
    return rtl("بابت چه چیزی؟\n\nمثلاً: پاداش پروژه، جریمهٔ تأخیر"), [
        [Button("بدون توضیح", data="pr:adjnoreason")],
        [Button("⬅️ انصراف", data="nav:cancel")],
    ]


# ------------------------------------------------------------------ shares
SHARE_BASIS_LABELS = {
    "percent": "درصدی",
    "fixed": "مبلغ ثابت",
    "hours": "ساعتی",
    "days": "روزانه",
    "points": "امتیازی",
    "project": "پروژه‌ای",
}


MEASURED_BASES = ("hours", "days", "points")


def share_list(book: Book, members, names, rules) -> Screen:
    """Who takes what. Without this, a payroll run produces nothing at all."""
    lines = [f"🧾 سهم اعضای {book.name}", ""]

    unset = [m for m in members if m.user_id not in rules]
    for member in members:
        name = names.get(member.user_id, "—")
        rule = rules.get(member.user_id)
        if rule is None:
            lines.append(f"⚪️ {name} — سهمی تعریف نشده")
            continue

        basis = SHARE_BASIS_LABELS.get(rule.basis.value, rule.basis.value)
        amount = (
            f"{rule.value:,.0f}٪" if rule.basis.value == "percent"
            else fmt(rule.value, book.base_currency) if rule.basis.value == "fixed"
            else f"ضریب {rule.value:,.0f}"
        )
        lines.append(f"• {name} — {amount} ({basis})")

    percent_total = sum(
        (r.value for r in rules.values() if r.basis.value == "percent"), Decimal("0")
    )
    if percent_total:
        lines += ["", f"مجموع درصدها: {percent_total:,.0f}٪"]
        if percent_total > 100:
            lines.append("⚠️ بیشتر از 100٪ است — بیش از قابل‌تقسیم پرداخت می‌شود.")
        elif percent_total < 100:
            lines.append(f"باقی‌مانده: {100 - percent_total:,.0f}٪ تقسیم نمی‌شود.")

    if unset:
        lines += ["", "کسی که سهمی ندارد در محاسبه فیشی نمی‌گیرد."]

    buttons = [
        [Button(f"{names.get(m.user_id, '—')[:18]}", data=f"sh:set:{m.user_id}")]
        for m in members[:10]
    ]
    buttons.append([Button("⬅️ بازگشت", data=f"pr:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def share_pick_basis(name: str, current) -> Screen:
    lines = [f"سهم {name} چطور حساب شود؟", ""]
    if current is not None:
        basis = SHARE_BASIS_LABELS.get(current.basis.value, current.basis.value)
        lines += [f"الان: {basis} ({current.value:,.0f})", ""]
    lines.append(
        "درصدی: سهمی از قابل‌تقسیم.\n"
        "مبلغ ثابت: همان عدد، هر دوره.\n"
        "ساعتی/روزانه/امتیازی: به نسبت کاری که در آن دوره ثبت شده."
    )

    buttons = [
        [Button("٪ درصدی", data="sh:basis:percent"),
         Button("مبلغ ثابت", data="sh:basis:fixed")],
        [Button("ساعتی", data="sh:basis:hours"),
         Button("روزانه", data="sh:basis:days"),
         Button("امتیازی", data="sh:basis:points")],
    ]
    if current is not None:
        buttons.append([Button("🗑 حذف سهم", data="sh:clear")])
    buttons.append([Button("⬅️ انصراف", data="sh:list")])
    return rtl("\n".join(lines)), buttons


def share_ask_value(name: str, basis: str) -> Screen:
    if basis == "percent":
        return rtl(f"{name} چند درصد بگیرد؟\n\nفقط عدد. مثلاً: 50"), [
            [Button("⬅️ انصراف", data="sh:list")]
        ]
    if basis == "fixed":
        return rtl(f"{name} هر دوره چه مبلغی بگیرد؟\n\nمثلاً: 15م"), [
            [Button("⬅️ انصراف", data="sh:list")]
        ]

    unit = {"hours": "ساعت", "days": "روز", "points": "امتیاز"}.get(basis, "واحد")
    return rtl(
        f"ضریب {name} چند باشد؟\n\n"
        f"سهمش به نسبت {unit}هایی که در هر دوره ثبت می‌شود حساب می‌شود، "
        f"ضربدر این عدد.\nبرای وزن برابر 1 بنویس."
    ), [[Button("⬅️ انصراف", data="sh:list")]]


def performance_list(book: Book, period, members, names, records, rules) -> Screen:
    """Only shown when somebody is actually paid by measure."""
    lines = [f"⏱ کارکرد {period.label}", ""]

    measured = [
        m for m in members
        if m.user_id in rules and rules[m.user_id].basis.value in MEASURED_BASES
    ]
    if not measured:
        return rtl(
            "⏱ کارکرد\n\n"
            "کسی در این دفتر ساعتی، روزانه یا امتیازی حساب نمی‌شود، "
            "پس چیزی برای ثبت نیست."
        ), [[Button("⬅️ بازگشت", data=f"pr:open:{period.id}")]]

    for member in measured:
        name = names.get(member.user_id, "—")
        basis = rules[member.user_id].basis.value
        record = records.get(member.user_id)
        value = {
            "hours": record.hours_worked if record else Decimal("0"),
            "days": record.days_worked if record else Decimal("0"),
            "points": record.points if record else Decimal("0"),
        }[basis]
        unit = {"hours": "ساعت", "days": "روز", "points": "امتیاز"}[basis]
        mark = "•" if record else "⚪️"
        lines.append(f"{mark} {name}: {value:,.0f} {unit}")

    buttons = [
        [Button(f"{names.get(m.user_id, '—')[:18]}", data=f"pf:set:{m.user_id}")]
        for m in measured[:10]
    ]
    buttons.append([Button("⬅️ بازگشت", data=f"pr:open:{period.id}")])
    return rtl("\n".join(lines)), buttons


def performance_ask_value(name: str, basis: str) -> Screen:
    unit = {"hours": "ساعت", "days": "روز", "points": "امتیاز"}.get(basis, "واحد")
    return rtl(f"{name} در این دوره چند {unit} داشت؟\n\nفقط عدد."), [
        [Button("⬅️ انصراف", data="nav:cancel")]
    ]


def no_shares_defined(book: Book, period) -> Screen:
    """What used to happen silently: calculate, and get nothing.

    A run that produces no payslips because nobody has a share is not an empty
    result, it is an unanswered question.
    """
    return rtl(
        "🧾 هنوز سهم کسی تعریف نشده\n\n"
        "محاسبه چیزی تولید نمی‌کند تا وقتی مشخص شود هر نفر چه سهمی می‌برد.\n"
        "از «سهم اعضا» شروع کن."
    ), [
        [Button("🧾 سهم اعضا", data="sh:list")],
        [Button("⬅️ بازگشت", data=f"pr:open:{period.id}")],
    ]


def payslip_pick_currency(name: str, amount: Decimal, base_code: str, codes) -> Screen:
    """Which currency is this person being paid in?"""
    base = CURRENCY_NAMES.get(base_code, base_code)
    buttons = [[Button(CURRENCY_NAMES.get(code, code), data=f"pr:pcur:{code}")]
               for code in codes]
    buttons.append([Button("↩️ انصراف", data="nav:cancel")])
    return rtl(
        f"💵 پرداخت به {name}\n\n"
        f"مبلغ: {fmt(amount, base)}\n\n"
        "به چه ارزی پرداخت شد؟ اگر ارز دیگری باشد، معادلش به نرخ امروز حساب می‌شود."
    ), buttons


def payslip_ask_rate(code: str, base_code: str) -> Screen:
    name = CURRENCY_NAMES.get(code, code)
    base = CURRENCY_NAMES.get(base_code, base_code)
    return rtl(
        f"💱 نرخ هر {name} به {base} چند بود؟\n\n"
        "نرخ لحظه‌ای در دسترس نیست، و دفتر برای پولی که جابه‌جا شده نرخ نمی‌سازد."
    ), [[Button("↩️ انصراف", data="nav:cancel")]]
