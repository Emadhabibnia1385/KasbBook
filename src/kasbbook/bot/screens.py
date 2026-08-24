"""What each screen says and which buttons it offers.

Pure functions: data in, text and buttons out. No database, no network, no
provider. That is what lets the same screens serve Telegram, Bale and Rubika,
and what lets every one of them be tested without a bot token.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple

from ..adapters.base import Button
from ..modules.books.models import Book, BookType
from ..modules.identity.models import Identity, Provider
from ..modules.ledger.models import Flow

RLM = "‏"

BOOK_LABELS = {
    BookType.PERSONAL: "👤 مالی شخصی",
    BookType.BUSINESS: "💼 کسب‌وکار",
    BookType.TEAM: "👥 تیم",
    BookType.ORGANIZATION: "🏢 سازمان",
}

PROVIDER_LABELS = {
    Provider.TELEGRAM: "تلگرام",
    Provider.BALE: "بله",
    Provider.RUBIKA: "روبیکا",
    Provider.EITAA: "ایتا",
    Provider.WEB: "وب",
}

Screen = Tuple[str, List[List[Button]]]


def rtl(text: str) -> str:
    """Mark every line right-to-left so mixed Persian and digits stay readable."""
    return "\n".join(RLM + line for line in text.splitlines())


def fmt(amount: Decimal, currency: str = "") -> str:
    grouped = f"{Decimal(amount):,.0f}"
    return f"{grouped} {currency}".strip()


# ------------------------------------------------------------------ welcome
def welcome(display_name: str) -> Screen:
    text = rtl(
        f"سلام {display_name} 👋\n\n"
        "KasbBook دفتر حساب کسب‌وکارت است.\n"
        "درآمد و هزینه را ثبت کن، و هر جا باشی — تلگرام، وب یا هر پیام‌رسان دیگر — "
        "همان دفتر را ببین.\n\n"
        "از منوی زیر شروع کن 👇"
    )
    return text, main_menu()


def not_linked(code: str) -> Screen:
    """Shown when this messenger account is not attached to any KasbBook account."""
    text = rtl(
        "این حساب هنوز به KasbBook وصل نیست.\n\n"
        "دو راه داری:\n\n"
        "۱. اگر حساب داری، در پنل وب وارد شو و این کد را وارد کن:\n"
        f"    {code}\n\n"
        "۲. اگر نداری، همین‌جا یک حساب تازه بساز.\n\n"
        "کد تا ۱۵ دقیقه معتبر است."
    )
    return text, [
        [Button("🆕 ساخت حساب تازه", data="acc:create")],
        [Button("🔄 کد جدید", data="acc:newcode")],
    ]


def main_menu() -> List[List[Button]]:
    return [
        [Button("📌 ثبت تراکنش", data="tx:new")],
        [Button("📊 گزارش‌ها", data="rep:menu")],
        [Button("📚 دفترهای من", data="book:list")],
        [Button("🔔 یادآورها", data="rm:panel")],
        [Button("🔗 حساب‌های متصل", data="acc:list")],
    ]


# -------------------------------------------------------------------- books
def book_list(books: Sequence[Book]) -> Screen:
    if not books:
        return (
            rtl("هنوز دفتری نداری.\n\nبا دکمهٔ زیر اولین دفترت را بساز."),
            [[Button("➕ ساخت دفتر", data="book:new")], [Button("⬅️ بازگشت", data="nav:home")]],
        )

    lines = ["📚 دفترهای تو:", ""]
    buttons: List[List[Button]] = []
    for book in books:
        label = BOOK_LABELS.get(book.type, book.type.value)
        lines.append(f"• {label} — {book.name}")
        buttons.append([Button(f"{label} {book.name}", data=f"book:open:{book.id}")])

    buttons.append([Button("➕ ساخت دفتر", data="book:new")])
    buttons.append([Button("⬅️ بازگشت", data="nav:home")])
    return rtl("\n".join(lines)), buttons


def pick_book(books: Sequence[Book], purpose: str = "tx") -> Screen:
    """The question every recording flow starts with: whose money is this?"""
    if not books:
        return (
            rtl("برای ثبت تراکنش اول باید یک دفتر بسازی."),
            [[Button("➕ ساخت دفتر", data="book:new")], [Button("⬅️ بازگشت", data="nav:home")]],
        )

    buttons = [
        [Button(f"{BOOK_LABELS.get(b.type, '')} {b.name}", data=f"{purpose}:book:{b.id}")]
        for b in books
    ]
    buttons.append([Button("⬅️ بازگشت", data="nav:home")])
    return rtl("این تراکنش مربوط به کدام دفتر است؟"), buttons


def new_book_type() -> Screen:
    return rtl("چه نوع دفتری می‌خواهی؟"), [
        [Button("👤 مالی شخصی", data="book:type:personal")],
        [Button("💼 کسب‌وکار شخصی", data="book:type:business")],
        [Button("👥 تیم", data="book:type:team")],
        [Button("⬅️ بازگشت", data="book:list")],
    ]


def ask_book_name(book_type: BookType) -> Screen:
    label = BOOK_LABELS.get(book_type, "")
    return rtl(f"اسم این دفتر چه باشد؟\n\nنوع: {label}"), [
        [Button("↩️ انصراف", data="book:list")]
    ]


# ------------------------------------------------------------- transactions
def pick_flow(book: Book) -> Screen:
    label = BOOK_LABELS.get(book.type, "")
    return rtl(f"{label} — {book.name}\n\nدرآمد یا هزینه؟"), [
        [Button("💰 درآمد", data="tx:flow:income")],
        [Button("🧾 هزینه", data="tx:flow:expense")],
        [Button("⬅️ بازگشت", data="tx:new")],
    ]


def ask_category(flow: Flow) -> Screen:
    word = "درآمد" if flow is Flow.INCOME else "هزینه"
    return rtl(f"دستهٔ این {word} چیست؟\n\nمثلاً: فروش، اجاره، حقوق"), [
        [Button("↩️ انصراف", data="nav:home")]
    ]


def ask_amount(category: str) -> Screen:
    return (
        rtl(
            f"دسته: {category}\n\n"
            "مبلغ را بنویس.\n"
            "می‌توانی این‌طور هم بنویسی: ۲۵۰ک، 1.2م، 250,000"
        ),
        [[Button("↩️ انصراف", data="nav:home")]],
    )


def transaction_saved(
    book: Book, flow: Flow, category: str, amount: Decimal, currency: str
) -> Screen:
    word = "درآمد" if flow is Flow.INCOME else "هزینه"
    text = rtl(
        "✅ ثبت شد.\n\n"
        f"📚 {book.name}\n"
        f"🔖 {word}\n"
        f"🏷 {category}\n"
        f"💵 {fmt(amount, currency)}"
    )
    return text, [
        [Button("➕ ثبت بعدی", data="tx:new")],
        [Button("📊 گزارش این دفتر", data=f"rep:book:{book.id}")],
        [Button("⬅️ منوی اصلی", data="nav:home")],
    ]


# ------------------------------------------------------------------ reports
def report_menu(books: Sequence[Book]) -> Screen:
    if not books:
        return rtl("هنوز دفتری نداری."), [[Button("⬅️ بازگشت", data="nav:home")]]

    buttons = [
        [Button(f"{BOOK_LABELS.get(b.type, '')} {b.name}", data=f"rep:book:{b.id}")]
        for b in books
    ]
    buttons.append([Button("⬅️ بازگشت", data="nav:home")])
    return rtl("گزارش کدام دفتر؟"), buttons


def book_report(book: Book, totals: dict) -> Screen:
    text = rtl(
        f"📊 {book.name}\n\n"
        f"💰 درآمد: {fmt(totals['income'], book.base_currency)}\n"
        f"🧾 هزینه: {fmt(totals['expense'], book.base_currency)}\n"
        f"➖ خالص: {fmt(totals['net'], book.base_currency)}"
    )
    return text, [
        [Button("➕ ثبت تراکنش", data="tx:new")],
        [Button("⬅️ بازگشت", data="rep:menu")],
    ]


# -------------------------------------------------------- linked identities
def identity_list(identities: Iterable[Identity], current: Provider) -> Screen:
    rows = list(identities)
    lines = ["🔗 حساب‌های متصل:", ""]

    for identity in rows:
        label = PROVIDER_LABELS.get(identity.provider, identity.provider.value)
        who = identity.external_username or identity.external_id
        here = " ← همین‌جا" if identity.provider is current else ""
        lines.append(f"• {label}: {who}{here}")

    missing = [p for p in PROVIDER_LABELS if p is not Provider.WEB and
               p not in {i.provider for i in rows}]
    if missing:
        lines += ["", "وصل‌نشده: " + "، ".join(PROVIDER_LABELS[p] for p in missing)]

    lines += ["", "برای وصل‌کردن یک پیام‌رسان دیگر، از پنل وب اقدام کن."]
    return rtl("\n".join(lines)), [[Button("⬅️ بازگشت", data="nav:home")]]


# ------------------------------------------------------------ jalali reports
def period_menu(book: Book, years: Sequence[int]) -> Screen:
    """Which stretch of time to look at."""
    rows: List[List[Button]] = [
        [
            Button("این هفته", data=f"rp:{book.id}:w:0"),
            Button("هفتهٔ گذشته", data=f"rp:{book.id}:w:1"),
        ]
    ]

    from ..shared import jalali

    this_year, this_month, _ = jalali.to_parts(__import__("datetime").date.today())
    rows.append([Button(f"{jalali.month_name(this_month)} {this_year}",
                        data=f"rp:{book.id}:m:{this_year}:{this_month:02d}")])

    buffer: List[Button] = []
    for year in years[:6]:
        buffer.append(Button(f"سال {year}", data=f"rp:{book.id}:y:{year}"))
        if len(buffer) == 2:
            rows.append(buffer)
            buffer = []
    if buffer:
        rows.append(buffer)

    rows.append([Button("⬅️ بازگشت", data="rep:menu")])
    return rtl(f"📊 {book.name}\n\nکدام بازه؟"), rows


def period_report(
    book: Book, period_label: str, summary, spec: str, comparison: Optional[str] = None
) -> Screen:
    body = (
        f"📊 {book.name} — {period_label}\n\n"
        f"💰 درآمد: {fmt(summary.income, book.base_currency)}\n"
        f"🧾 هزینه: {fmt(summary.expense, book.base_currency)}\n"
        f"➖ خالص: {fmt(summary.net, book.base_currency)}"
    )
    if comparison:
        body += f"\n\n{comparison}"

    return rtl(body), [
        [Button("🏷 تفکیک دسته‌ها", data=f"rb:{book.id}:{spec}")],
        [Button("📥 خروجی CSV", data=f"rc:{book.id}:{spec}")],
        [Button("📆 بازهٔ دیگر", data=f"rep:book:{book.id}")],
        [Button("⬅️ منوی اصلی", data="nav:home")],
    ]


def category_breakdown(book: Book, period_label: str, buckets, spec: str) -> Screen:
    from ..modules.ledger.models import Flow

    lines = [f"🏷 تفکیک — {period_label}"]
    for flow, title in ((Flow.INCOME, "💰 درآمد"), (Flow.EXPENSE, "🧾 هزینه")):
        rows = buckets.get(flow, [])
        lines += ["", title]
        if not rows:
            lines.append("— خالی —")
            continue

        grand = sum((total for _, total, _ in rows), Decimal("0"))
        for name, total, count in rows[:8]:
            share = round(total * 100 / grand) if grand else 0
            lines.append(f"• {name}: {fmt(total, book.base_currency)} ({share}%، {count} مورد)")

    return rtl("\n".join(lines)), [
        [Button("⬅️ بازگشت", data=f"rp:{book.id}:{spec}")],
    ]


def comparison_line(previous_label: str, before, after) -> str:
    def delta(name: str, old: Decimal, new: Decimal) -> str:
        difference = new - old
        arrow = "▲" if difference > 0 else ("▼" if difference < 0 else "▬")
        percent = f"{round(difference * 100 / abs(old)):+d}%" if old else "—"
        return f"{arrow} {name}: {percent}"

    return "\n".join([
        f"📈 نسبت به {previous_label}:",
        delta("درآمد", before.income, after.income),
        delta("هزینه", before.expense, after.expense),
        delta("خالص", before.net, after.net),
    ])


# --------------------------------------------------------------- quick entry
def quick_pick_book(entry, books: Sequence[Book]) -> Screen:
    """A one-line entry still has to say which book it belongs to."""
    text = rtl(
        f"🏷 {entry.category}\n"
        f"💵 {fmt(entry.amount)}\n\n"
        "در کدام دفتر ثبت شود؟"
    )
    rows = [
        [Button(f"{BOOK_LABELS.get(b.type, '')} {b.name}", data=f"qk:book:{b.id}")]
        for b in books
    ]
    rows.append([Button("↩️ انصراف", data="nav:home")])
    return text, rows


def quick_pick_flow(entry) -> Screen:
    return (
        rtl(f"🏷 {entry.category}\n💵 {fmt(entry.amount)}\n\nدرآمد است یا هزینه؟"),
        [
            [Button("💰 درآمد", data="qk:flow:income"), Button("🧾 هزینه", data="qk:flow:expense")],
            [Button("↩️ انصراف", data="nav:home")],
        ],
    )


def unreadable_line() -> Screen:
    return (
        rtl(
            "❓ متوجه نشدم.\n\n"
            "برای ثبت سریع بنویس: «دسته مبلغ»\n"
            "مثال‌ها:\n"
            "• فروش 250000\n"
            "• اجاره ۱٫۲م بابت مرداد\n\n"
            "یا از منو استفاده کن:"
        ),
        main_menu(),
    )


def error(message: str) -> Screen:
    return rtl(f"⚠️ {message}"), [[Button("⬅️ منوی اصلی", data="nav:home")]]


# =========================================================== book workspace
def book_menu(book: Book) -> Screen:
    """Everything that belongs to one book, one press away."""
    label = BOOK_LABELS.get(book.type, "")
    return rtl(f"{label} — {book.name}"), [
        [Button("📌 ثبت تراکنش", data=f"tx:book:{book.id}")],
        [Button("📄 تراکنش‌ها", data=f"td:list:{book.id}"),
         Button("🔎 جست‌وجو", data=f"sr:new:{book.id}")],
        [Button("📊 گزارش", data=f"rep:book:{book.id}")],
        [Button("🎯 بودجه‌ها", data=f"bg:list:{book.id}"),
         Button("🤝 طلب و بدهی", data=f"dt:list:{book.id}")],
        [Button("📄 وام و اقساط", data=f"ln:list:{book.id}"),
         Button("🔁 تکرارشونده", data=f"rr:list:{book.id}")],
        [Button("⬅️ دفترها", data="book:list")],
    ]


# ------------------------------------------------------------------ budgets
def _bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, round(percent * width / 100)))
    return "█" * filled + "░" * (width - filled)


def budget_list(book: Book, statuses, month_label: str) -> Screen:
    if not statuses:
        text = rtl(
            f"🎯 بودجه‌های {book.name}\n\n"
            "هنوز سقفی تعیین نشده.\n"
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

    rows = [[Button("➕ تعیین بودجه", data=f"bg:add:{book.id}")]]
    for status in statuses:
        rows.append([
            Button(status.label[:22], data="noop:x"),
            Button("🗑", data=f"bg:del:{status.budget.id}"),
        ])
    rows.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return text, rows


def budget_pick_kind(book: Book) -> Screen:
    return rtl("بودجه برای چه چیزی؟"), [
        [Button("🏷 یک دستهٔ مشخص", data="bg:kind:category")],
        [Button("🧾 کل هزینه‌ها", data="bg:kind:expense")],
        [Button("💰 کل درآمدها", data="bg:kind:income")],
        [Button("↩️ انصراف", data=f"bg:list:{book.id}")],
    ]


def budget_ask_target() -> Screen:
    return rtl("نام دقیق دسته را بنویس:"), [[Button("↩️ انصراف", data="nav:home")]]


def budget_ask_amount(label: str) -> Screen:
    return rtl(f"سقف ماهانه برای «{label}» چقدر باشد؟"), [
        [Button("↩️ انصراف", data="nav:home")]
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
        lines += ["", "چیزی ثبت نشده.", "نسیه‌ها و قرض‌ها اینجا می‌مانند و روی درآمد اثر نمی‌گذارند."]
    else:
        lines.append("")
        for debt in debts:
            arrow = "📥" if debt.direction.value == "owed_to_me" else "📤"
            line = f"{arrow} {debt.person}: {fmt(debt.amount, book.base_currency)}"
            if debt.due_on:
                from ..shared import jalali
                line += f"\n  سررسید: {jalali.to_text(debt.due_on)}"
            if debt.note:
                line += f"\n  {debt.note[:40]}"
            lines.append(line)

    rows = [[Button("➕ ثبت طلب/بدهی", data=f"dt:add:{book.id}")]]
    for debt in debts[:10]:
        rows.append([
            Button(debt.person[:18], data="noop:x"),
            Button("✅ تسویه", data=f"dt:settle:{debt.id}"),
            Button("🗑", data=f"dt:del:{debt.id}"),
        ])
    rows.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl("\n".join(lines)), rows


def debt_ask_person() -> Screen:
    return rtl("نام طرف حساب را بنویس:"), [[Button("↩️ انصراف", data="nav:home")]]


def debt_pick_direction(person: str) -> Screen:
    return rtl(f"{person}\n\nجهت را انتخاب کن:"), [
        [Button("📥 به من بدهکار است", data="dt:dir:owed_to_me")],
        [Button("📤 من بدهکارم", data="dt:dir:i_owe")],
        [Button("↩️ انصراف", data="nav:home")],
    ]


def debt_ask_amount() -> Screen:
    return rtl("مبلغ را بنویس:"), [[Button("↩️ انصراف", data="nav:home")]]


def debt_ask_due() -> Screen:
    return rtl("سررسید کِی است؟\n\nتاریخ بنویس، یا «ندارد» بزن."), [
        [Button("بدون سررسید", data="dt:nodue")],
        [Button("↩️ انصراف", data="nav:home")],
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
    from ..shared import jalali

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
        buttons.append([Button("✅ ثبت پرداخت قسط", data=f"ln:pay:{loan.id}")])
    buttons.append([Button("🗑 حذف وام", data=f"ln:del:{loan.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"ln:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def loan_ask_title() -> Screen:
    return rtl("نام وام چیست؟\n\nمثلاً: وام مسکن"), [
        [Button("↩️ انصراف", data="nav:home")]
    ]


def loan_ask_amount(title: str) -> Screen:
    return rtl(f"{title}\n\nمبلغ هر قسط چقدر است؟"), [
        [Button("↩️ انصراف", data="nav:home")]
    ]


def loan_ask_count() -> Screen:
    return rtl("تعداد کل اقساط چند تاست؟"), [[Button("↩️ انصراف", data="nav:home")]]


def loan_ask_start() -> Screen:
    return rtl("تاریخ اولین قسط؟\n\nشمسی یا میلادی، یا «امروز»."), [
        [Button("امروز", data="ln:today")],
        [Button("↩️ انصراف", data="nav:home")],
    ]


def confirm_delete(what: str, yes_data: str, no_data: str) -> Screen:
    return rtl(f"⚠️ حذف {what}\n\nمطمئنی؟"), [
        [Button("🗑 بله، حذف کن", data=yes_data)],
        [Button("↩️ انصراف", data=no_data)],
    ]


# ======================================================= transaction detail
def transaction_list(book: Book, rows, page: int, total: int, per_page: int = 8) -> Screen:
    from ..shared import jalali

    if not rows:
        return rtl(f"📄 {book.name}\n\nهنوز تراکنشی ثبت نشده."), [
            [Button("➕ ثبت تراکنش", data=f"tx:book:{book.id}")],
            [Button("⬅️ بازگشت", data=f"book:open:{book.id}")],
        ]

    lines = [f"📄 تراکنش‌های {book.name} — {total} مورد", ""]
    buttons: List[List[Button]] = []
    for tx in rows:
        mark = "💰" if tx.flow is Flow.INCOME else "🧾"
        clip = "🧾" if tx.receipt_file_id else ""
        lines.append(
            f"{mark} {jalali.to_text(tx.occurred_on)} | {tx.category}: "
            f"{fmt(tx.converted_amount, book.base_currency)} {clip}"
        )
        buttons.append([
            Button(f"{tx.category[:16]} — {fmt(tx.converted_amount)}", data=f"td:open:{tx.id}")
        ])

    last = max(0, (total - 1) // per_page)
    if last:
        nav: List[Button] = []
        if page > 0:
            nav.append(Button("◀️ قبلی", data=f"td:page:{book.id}:{page - 1}"))
        nav.append(Button(f"{page + 1}/{last + 1}", data="noop:x"))
        if page < last:
            nav.append(Button("بعدی ▶️", data=f"td:page:{book.id}:{page + 1}"))
        buttons.append(nav)

    buttons.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl("\n".join(lines)), buttons


def transaction_detail(book: Book, tx) -> Screen:
    from ..shared import jalali

    word = "درآمد" if tx.flow is Flow.INCOME else "هزینه"
    lines = [
        "🧾 جزئیات تراکنش",
        "",
        f"📅 {jalali.to_text(tx.occurred_on)}  ({tx.occurred_on.isoformat()})",
        f"🔖 {word}",
        f"🏷 {tx.category}",
        f"💵 {fmt(tx.converted_amount, book.base_currency)}",
    ]
    if tx.original_currency != book.base_currency:
        lines.append(f"💱 اصل: {fmt(tx.original_amount, tx.original_currency)}"
                     f" (نرخ {tx.conversion_rate})")
    if tx.description:
        lines.append(f"📝 {tx.description}")
    lines.append("🧾 رسید: " + ("دارد" if tx.receipt_file_id else "ندارد"))

    buttons: List[List[Button]] = []
    if tx.receipt_file_id:
        buttons.append([
            Button("🧾 دیدن رسید", data=f"td:rcpv:{tx.id}"),
            Button("❌ حذف رسید", data=f"td:rcpd:{tx.id}"),
        ])
    else:
        buttons.append([Button("🧾 افزودن رسید", data=f"td:rcp:{tx.id}")])

    buttons.append([Button("🗑 حذف تراکنش", data=f"td:del:{tx.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"td:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def ask_receipt() -> Screen:
    return rtl("🧾 عکس یا فایل رسید را بفرست.\n\nبرای انصراف /cancel بزن."), []


# ================================================================== search
def ask_search() -> Screen:
    return rtl("🔎 جست‌وجو\n\nبخشی از نام دسته یا توضیح را بنویس."), [
        [Button("↩️ انصراف", data="nav:home")]
    ]


def search_results(book: Book, query: str, rows, total: int, amount, page: int,
                   per_page: int = 10) -> Screen:
    from ..shared import jalali

    if not total:
        return rtl(f"🔎 «{query}»\n\nچیزی پیدا نشد."), [
            [Button("🔎 جست‌وجوی دیگر", data=f"sr:new:{book.id}")],
            [Button("⬅️ بازگشت", data=f"book:open:{book.id}")],
        ]

    lines = [f"🔎 «{query}» — {total} نتیجه", f"جمع کل: {fmt(amount, book.base_currency)}", ""]
    for tx in rows:
        mark = "💰" if tx.flow is Flow.INCOME else "🧾"
        note = f" — {tx.description[:24]}" if tx.description else ""
        lines.append(
            f"{mark} {jalali.to_text(tx.occurred_on)} | {tx.category}: "
            f"{fmt(tx.converted_amount)}{note}"
        )

    buttons: List[List[Button]] = []
    last = max(0, (total - 1) // per_page)
    if last:
        nav: List[Button] = []
        if page > 0:
            nav.append(Button("◀️ قبلی", data=f"sr:page:{page - 1}"))
        nav.append(Button(f"{page + 1}/{last + 1}", data="noop:x"))
        if page < last:
            nav.append(Button("بعدی ▶️", data=f"sr:page:{page + 1}"))
        buttons.append(nav)

    buttons.append([Button("🔎 جست‌وجوی دیگر", data=f"sr:new:{book.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl("\n".join(lines)), buttons


# =============================================================== recurring
PERIOD_LABELS = {"daily": "روزانه", "weekly": "هفتگی", "monthly": "ماهانه"}


def recurring_list(book: Book, rules) -> Screen:
    from ..shared import jalali

    if not rules:
        text = rtl(
            f"🔁 تکرارشونده‌های {book.name}\n\n"
            "چیزی تعریف نشده.\n"
            "اجاره یا حقوق را یک بار تعریف کن تا خودکار ثبت شوند."
        )
    else:
        lines = [f"🔁 تکرارشونده‌های {book.name}", ""]
        for rule in rules:
            state = "فعال ✅" if rule.is_active else "متوقف ⏸"
            word = "درآمد" if rule.flow is Flow.INCOME else "هزینه"
            lines.append(
                f"• {rule.category} — {fmt(rule.amount, book.base_currency)}\n"
                f"  {word} | {PERIOD_LABELS.get(rule.period.value, '')} | {state}\n"
                f"  بعدی: {jalali.to_text(rule.next_run_on)}"
            )
        text = rtl("\n".join(lines))

    buttons = [[Button("➕ افزودن قاعده", data=f"rr:add:{book.id}")]]
    for rule in rules[:10]:
        toggle = "⏸" if rule.is_active else "▶️"
        buttons.append([
            Button(rule.category[:18], data="noop:x"),
            Button(toggle, data=f"rr:tog:{rule.id}"),
            Button("🗑", data=f"rr:del:{rule.id}"),
        ])
    buttons.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return text, buttons


def recurring_pick_flow() -> Screen:
    return rtl("درآمد است یا هزینه؟"), [
        [Button("💰 درآمد", data="rr:flow:income"), Button("🧾 هزینه", data="rr:flow:expense")],
        [Button("↩️ انصراف", data="nav:home")],
    ]


def recurring_ask_category() -> Screen:
    return rtl("دسته چیست؟\n\nمثلاً: اجاره، حقوق، اشتراک"), [
        [Button("↩️ انصراف", data="nav:home")]
    ]


def recurring_ask_amount(category: str) -> Screen:
    return rtl(f"{category}\n\nمبلغ چقدر است؟"), [[Button("↩️ انصراف", data="nav:home")]]


def recurring_pick_period() -> Screen:
    return rtl("هر چند وقت تکرار شود؟"), [
        [Button("ماهانه", data="rr:period:monthly")],
        [Button("هفتگی", data="rr:period:weekly")],
        [Button("روزانه", data="rr:period:daily")],
        [Button("↩️ انصراف", data="nav:home")],
    ]


def recurring_ask_start() -> Screen:
    return rtl("از چه تاریخی شروع شود؟"), [
        [Button("امروز", data="rr:today")],
        [Button("↩️ انصراف", data="nav:home")],
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


def ask_hour() -> Screen:
    return rtl("ساعت ارسال خلاصه را بنویس (۰ تا ۲۳):"), [
        [Button("↩️ انصراف", data="rm:panel")]
    ]


def ask_days() -> Screen:
    return rtl("چند روز قبل از سررسید خبر بدهم؟"), [
        [Button("↩️ انصراف", data="rm:panel")]
    ]
