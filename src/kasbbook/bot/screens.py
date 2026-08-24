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


def error(message: str) -> Screen:
    return rtl(f"⚠️ {message}"), [[Button("⬅️ منوی اصلی", data="nav:home")]]
