"""Planning screens: budgets, debts, loans, recurring rules, reminders."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ...adapters.base import Button
from ...modules.books.models import Book
from ...modules.ledger.models import Flow
from ...shared import jalali
from .common import (
    Screen,
    _problem,
    fmt,
    rtl,
)


# ------------------------------------------------------------------ budgets
def _bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, round(percent * width / 100)))
    return "█" * filled + "░" * (width - filled)


def budget_list(book: Book, statuses, month_label: str) -> Screen:
    if not statuses:
        text = rtl(
            f"🎯 بودجه‌های {book.name}\n\n"
            "هنوز بودجه‌ای نساخته‌ای.\n"
            "برای یک دسته یا کل هزینه‌ها سقف ماهانه بگذار تا ربات خبر بدهد."
        )
    else:
        lines = [f"🎯 بودجه‌های {month_label}", ""]
        for status in statuses:
            flag = "⛔" if status.over else ("⚠️" if status.percent >= 80 else "✅")
            lines.append(
                f"{flag} {status.label}\n"
                f"  {_bar(status.percent)} {status.percent}%\n"
                f"  {fmt(status.spent, book.base_currency)} از {fmt(status.limit)}"
            )
            if status.over:
                lines.append(f"  بیش از سقف: {fmt(-status.remaining)}")
        text = rtl("\n".join(lines))

    rows = [[Button("➕ ساخت بودجه", data=f"bg:add:{book.id}")]]
    for status in statuses:
        # The name rides on the delete button itself: a separate label button
        # had nothing to do and sent the person home when pressed.
        rows.append([Button(f"🗑 حذف بودجهٔ {status.label[:22]}", data=f"bg:del:{status.budget.id}")])
    rows.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return text, rows


def budget_pick_kind(book: Book) -> Screen:
    return rtl("بودجه برای چه چیزی؟"), [
        [Button("🏷 یک دستهٔ مشخص", data="bg:kind:category")],
        [Button("🧾 کل هزینه‌ها", data="bg:kind:expense")],
        [Button("💰 کل درآمدها", data="bg:kind:income")],
        [Button("↩️ انصراف", data=f"bg:list:{book.id}")],
    ]


def budget_ask_target(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "نام دسته را همان‌طور که ثبت کرده‌ای بنویس.\nمثال: اجاره"), [
        [Button("↩️ انصراف", data="nav:cancel")]
    ]


def budget_ask_amount(label: str, problem: Optional[str] = None) -> Screen:
    return rtl(
        _problem(problem)
        + f"سقف ماهانهٔ «{label}» چقدر باشد؟\nمثال: 500ک یا 2 میلیون"
    ), [
        [Button("↩️ انصراف", data="nav:cancel")]
    ]


# ------------------------------------------------------------------- debts
def debt_list(book: Book, debts, totals) -> Screen:
    lines = [
        f"🤝 طلب و بدهی — {book.name}",
        "",
        f"📥 طلب من: {fmt(totals.owed_to_me, book.base_currency)}",
        f"📤 بدهی من: {fmt(totals.i_owe, book.base_currency)}",
        f"⚖️ خالص: {fmt(totals.net, book.base_currency)}",
    ]

    if not debts:
        lines += ["", "مورد بازی نیست.", "نسیه‌ها و قرض‌ها اینجا می‌مانند و روی درآمد اثر نمی‌گذارند."]
    else:
        lines.append("")
        for debt in debts:
            arrow = "📥" if debt.direction.value == "owed_to_me" else "📤"
            line = f"{arrow} {debt.person}: {fmt(debt.amount, book.base_currency)}"
            if debt.due_on:
                line += f"\n  سررسید: {jalali.to_text(debt.due_on)}"
            if debt.note:
                line += f"\n  {debt.note[:40]}"
            lines.append(line)

    rows = [[Button("➕ ثبت طلب یا بدهی", data=f"dt:add:{book.id}")]]
    for debt in debts[:10]:
        rows.append([
            Button(f"✅ تسویه {debt.person[:14]}", data=f"dt:settle:{debt.id}"),
            Button("🗑 حذف", data=f"dt:del:{debt.id}"),
        ])
    rows.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl("\n".join(lines)), rows


def debt_ask_person() -> Screen:
    return rtl("نام طرف حساب را بنویس.\nمثال: آقای رضایی"), [[Button("↩️ انصراف", data="nav:cancel")]]


def debt_pick_direction(person: str, problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + f"{person}\n\nکدام است؟"), [
        [Button("📥 طلب من (او بدهکار است)", data="dt:dir:owed_to_me")],
        [Button("📤 بدهی من (من بدهکارم)", data="dt:dir:i_owe")],
        [Button("↩️ انصراف", data="nav:cancel")],
    ]


def debt_ask_amount(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "مبلغ را بنویس؛ مثلاً 2000000 یا 2م"), [[Button("↩️ انصراف", data="nav:cancel")]]


def debt_ask_due(typed: Optional[str] = None) -> Screen:
    return rtl(
        (f"⚠️ «{typed}» را به‌عنوان تاریخ نفهمیدم.\n\n" if typed else "")
        + "سررسید کِی است؟\n\n"
        "تاریخ بنویس (مثلاً 1405/08/15) یا دکمهٔ «بدون سررسید» را بزن."
    ), [
        [Button("بدون سررسید", data="dt:nodue")],
        [Button("↩️ انصراف", data="nav:cancel")],
    ]


# ------------------------------------------------------------------- loans
def loan_list(book: Book, rows_with_progress) -> Screen:
    if not rows_with_progress:
        text = rtl(
            f"📄 وام‌های {book.name}\n\n"
            "هنوز وامی ثبت نشده.\n"
            "وام را یک بار تعریف کن تا ربات بگوید چند قسط مانده."
        )
        buttons = [
            [Button("➕ افزودن وام", data=f"ln:add:{book.id}")],
            [Button("⬅️ بازگشت", data=f"book:open:{book.id}")],
        ]
        return text, buttons

    lines = [f"📄 وام‌های {book.name}", ""]
    remaining_total = Decimal("0")
    for progress in rows_with_progress:
        remaining_total += progress.remaining_amount
        lines.append(
            f"• {progress.loan.title}\n"
            f"  {progress.paid_count} از {progress.total_count} پرداخت شده ({progress.percent}%)\n"
            f"  باقی‌مانده: {fmt(progress.remaining_amount, book.base_currency)}"
        )
    lines += ["", f"مجموع باقی‌مانده: {fmt(remaining_total, book.base_currency)}"]

    buttons = [[Button("➕ افزودن وام", data=f"ln:add:{book.id}")]]
    for progress in rows_with_progress[:10]:
        buttons.append([
            Button(
                f"{progress.loan.title[:16]} — {progress.remaining_count} قسط",
                data=f"ln:open:{progress.loan.id}",
            )
        ])
    buttons.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl("\n".join(lines)), buttons


def loan_detail(book: Book, progress) -> Screen:

    loan = progress.loan
    lines = [
        f"📄 {loan.title}",
        "",
        f"💵 هر قسط: {fmt(loan.installment_amount, book.base_currency)}",
        f"🔢 تعداد: {progress.total_count}",
        f"💰 کل: {fmt(progress.total_amount, book.base_currency)}",
        "",
        f"✅ پرداخت‌شده: {progress.paid_count} قسط ({fmt(progress.paid_amount)})",
        f"⏳ باقی‌مانده: {progress.remaining_count} قسط ({fmt(progress.remaining_amount)})",
        f"📊 {_bar(progress.percent)} {progress.percent}%",
        "",
        f"🗓 شروع: {jalali.to_text(loan.starts_on)}",
    ]
    if progress.next_due:
        lines.append(f"⏰ قسط بعدی: {jalali.to_text(progress.next_due)}")
    else:
        lines.append("🏁 تمام شد.")

    buttons = []
    if progress.remaining_count:
        buttons.append([Button("✅ ثبت پرداخت قسط",
                               data=f"ln:pay:{loan.id}:{progress.paid_count}")])
    buttons.append([Button("🗑 حذف وام", data=f"ln:del:{loan.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"ln:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def loan_ask_title(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "نام وام چیست؟\n\nمثال: وام مسکن"), [
        [Button("↩️ انصراف", data="nav:cancel")]
    ]


def loan_ask_amount(title: str, problem: Optional[str] = None) -> Screen:
    return rtl(
        _problem(problem) + f"{title}\n\nمبلغ هر قسط چقدر است؟ مثال: 5م یا 5000000"
    ), [
        [Button("↩️ انصراف", data="nav:cancel")]
    ]


def loan_ask_count(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "تعداد کل اقساط چند تاست؟ مثال: 24"), [[Button("↩️ انصراف", data="nav:cancel")]]


def loan_ask_start(typed: Optional[str] = None) -> Screen:
    return rtl(
        (f"⚠️ «{typed}» را به‌عنوان تاریخ نفهمیدم.\n\n" if typed else "")
        + "تاریخ اولین قسط؟\n\nمثال: 1405/08/01 یا «فردا»؛ یا دکمهٔ «امروز» را بزن."
    ), [
        [Button("امروز", data="ln:today")],
        [Button("↩️ انصراف", data="nav:cancel")],
    ]


def debt_confirm_settle(book: Book, debt) -> Screen:
    """Settling asks whether the money itself should be recorded (owner decision D-2).

    "Only close it" comes first and is the safe answer: if the sale on credit or
    the purchase was recorded when it happened, recording the payment too
    counts the same money twice.
    """
    received = debt.direction.value == "owed_to_me"
    as_what = "درآمد" if received else "هزینه"
    return rtl(
        f"✅ تسویهٔ «{debt.person}» — {fmt(debt.amount, book.base_currency)}\n\n"
        f"اگر فروش یا خرید اصلی را قبلاً ثبت کرده‌ای، فقط ببند تا دوبار شمرده نشود. "
        f"اگر نه، این مبلغ به‌عنوان {as_what} هم ثبت شود."
    ), [
        [Button("فقط ببند", data=f"dt:settleonly:{debt.id}")],
        [Button(f"ببند و {as_what} ثبت کن", data=f"dt:settletx:{debt.id}")],
        [Button("↩️ انصراف", data=f"dt:list:{book.id}")],
    ]


# =============================================================== recurring
# Not PERIOD_LABELS: payroll defines that name further down for its period
# statuses, and the later definition silently replaced this one, so every
# recurring rule was listed with an empty frequency.
RECURRING_PERIOD_LABELS = {"daily": "روزانه", "weekly": "هفتگی", "monthly": "ماهانه"}


def recurring_list(book: Book, rules) -> Screen:

    if not rules:
        text = rtl(
            f"🔁 تراکنش‌های تکرارشونده — {book.name}\n\n"
            "هنوز چیزی تعریف نشده.\n"
            "اجاره یا حقوق را یک بار تعریف کن تا خودکار ثبت شوند."
        )
    else:
        lines = [f"🔁 تراکنش‌های تکرارشونده — {book.name}", ""]
        for rule in rules:
            state = "فعال ✅" if rule.is_active else "متوقف ⏸"
            word = "درآمد" if rule.flow is Flow.INCOME else "هزینه"
            lines.append(
                f"• {rule.category} — {fmt(rule.amount, book.base_currency)}\n"
                f"  {word} | {RECURRING_PERIOD_LABELS.get(rule.period.value, '')} | {state}\n"
                f"  بعدی: {jalali.to_text(rule.next_run_on)}"
            )
        text = rtl("\n".join(lines))

    buttons = [[Button("➕ افزودن تراکنش تکرارشونده", data=f"rr:add:{book.id}")]]
    for rule in rules[:10]:
        toggle = f"⏸ توقف {rule.category[:12]}" if rule.is_active else f"▶️ ادامهٔ {rule.category[:12]}"
        buttons.append([
            Button(toggle, data=f"rr:tog:{rule.id}"),
            Button("🗑 حذف", data=f"rr:del:{rule.id}"),
        ])
    buttons.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return text, buttons


def recurring_pick_flow() -> Screen:
    return rtl("این تراکنش تکرارشونده درآمد است یا هزینه؟"), [
        [Button("💰 درآمد", data="rr:flow:income"), Button("🧾 هزینه", data="rr:flow:expense")],
        [Button("↩️ انصراف", data="nav:cancel")],
    ]


def recurring_ask_category(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "دسته چیست؟\n\nمثال: اجاره، حقوق، اشتراک"), [
        [Button("↩️ انصراف", data="nav:cancel")]
    ]


def recurring_ask_amount(category: str, problem: Optional[str] = None) -> Screen:
    return rtl(
        _problem(problem) + f"{category}\n\nمبلغ چقدر است؟ مثال: 5000000 یا 5م"
    ), [[Button("↩️ انصراف", data="nav:cancel")]]


def recurring_pick_period(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "هر چند وقت تکرار شود؟"), [
        [Button("ماهانه", data="rr:period:monthly")],
        [Button("هفتگی", data="rr:period:weekly")],
        [Button("روزانه", data="rr:period:daily")],
        [Button("↩️ انصراف", data="nav:cancel")],
    ]


def recurring_ask_start(typed: Optional[str] = None) -> Screen:
    return rtl(
        (f"⚠️ «{typed}» را به‌عنوان تاریخ نفهمیدم.\n\n" if typed else "")
        + "از چه تاریخی شروع شود؟\n\nمثال: 1405/08/01 یا «فردا»؛ یا دکمهٔ «امروز» را بزن."
    ), [
        [Button("امروز", data="rr:today")],
        [Button("↩️ انصراف", data="nav:cancel")],
    ]


# =============================================================== reminders
def reminder_settings(user) -> Screen:
    digest = "روشن ✅" if user.digest_enabled else "خاموش ❌"
    text = rtl(
        "🔔 یادآورها\n\n"
        "خلاصهٔ روزانه، آخر هر روزی که چیزی ثبت شده باشد، فرستاده می‌شود.\n"
        "یادآور قسط و سررسید، قبل از موعد خبر می‌دهد."
    )
    return text, [
        [Button(f"📊 خلاصهٔ روزانه: {digest}", data="rm:toggle")],
        [Button(f"🕘 ساعت ارسال: {user.digest_hour}", data="rm:hour")],
        [Button(f"⏳ چند روز قبل: {user.reminder_days}", data="rm:days")],
        [Button("⬅️ بازگشت", data="nav:home")],
    ]


def ask_hour(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "ساعت ارسال خلاصه را بنویس (0 تا 23)؛ مثلاً: 21"), [
        [Button("↩️ انصراف", data="rm:panel")]
    ]


def ask_days(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "چند روز قبل از سررسید خبر بدهم؟ مثال: 3"), [
        [Button("↩️ انصراف", data="rm:panel")]
    ]
