"""What every screen shares: right-to-left text, money and date formatting, the
home screen, errors, and the stale and cancelled answers.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from ...adapters.base import Button
from ...modules.books.models import Book, BookType
from ...modules.exchange.models import CURRENCY_NAMES


RLM = "‏"


BOOK_LABELS = {
    BookType.PERSONAL: "👤 مالی شخصی",
    BookType.BUSINESS: "💼 کسب‌وکار",
    BookType.TEAM: "👥 تیم",
    BookType.ORGANIZATION: "🏢 سازمان",
}


Screen = Tuple[str, List[List[Button]]]


def rtl(text: str) -> str:
    """Mark every line right-to-left so mixed Persian and digits stay readable."""
    return "\n".join(RLM + line for line in text.splitlines())


def _problem(problem: Optional[str]) -> str:
    """The cause line a prompt shows when the last answer was refused."""
    return f"⚠️ {problem}\n\n" if problem else ""


def with_notice(notice: str, screen: "Screen") -> "Screen":
    """A one-line message above a screen, separated from it by a blank line.

    `rtl()` splits on lines and a trailing newline is not a line, so gluing a
    notice to the next screen with a newline inside `rtl()` loses the blank line and
    welds "✅ ثبت شد" onto the first line of the screen.
    """
    text, buttons = screen
    return rtl(notice) + "\n\n" + text, buttons


def fmt(amount: Decimal, currency: str = "") -> str:
    grouped = f"{Decimal(amount):,.0f}"
    # A code like IRT means nothing to the reader; the word does.
    return f"{grouped} {CURRENCY_NAMES.get(currency, currency)}".strip()


# Currencies counted in whole units. Everything else is a token, where the
# fractional part is real money: 229.19 USDT shown as "229" loses 0.19 of it.
WHOLE_UNIT_CURRENCIES = ("IRT", "IRR")


def fmt_currency(amount: Decimal, code: str) -> str:
    """Format an amount in its own currency, keeping a token's decimals."""
    name = CURRENCY_NAMES.get(code, code)
    if code in WHOLE_UNIT_CURRENCIES:
        return f"{Decimal(amount):,.0f} {name}"
    text = f"{Decimal(amount):,.4f}".rstrip("0").rstrip(".")
    return f"{text or '0'} {name}"


# ------------------------------------------------------------------ welcome
def welcome(display_name: str, first_run: bool = False) -> Screen:
    """The home screen. A first run says what to do first: a book comes before anything."""
    start = (
        "اول یک دفتر بساز؛ مثلاً «خرج خانه» یا «کارگاه». بعد هر تراکنش را با یک خط ثبت می‌کنی."
        if first_run
        else "برای شروع بنویس: «فروش 250ک» — یا از منوی زیر استفاده کن."
    )
    text = rtl(
        f"سلام {display_name}\n\n"
        "KasbBook دفتر حساب کسب‌وکارت است.\n"
        "درآمد و هزینه را ثبت کن، و هر جا باشی — تلگرام، وب یا هر پیام‌رسان دیگر — "
        "همان دفتر را ببین.\n\n"
        + start
    )
    buttons = main_menu()
    if first_run:
        buttons = [[Button("➕ ساخت دفتر", data="book:new")]] + buttons
    return text, buttons


def main_menu() -> List[List[Button]]:
    return [
        [Button("📌 ثبت تراکنش", data="tx:new")],
        [Button("📊 گزارش‌ها", data="rep:menu")],
        [Button("📚 دفترهای من", data="book:list")],
        [Button("🔔 یادآورها", data="rm:panel")],
        [Button("👤 حساب کاربری", data="acc:panel")],
    ]


# -------------------------------------------------------------------- books
def _book_names(books: Sequence[Book]) -> dict:
    """A name per book that is unique on screen.

    Two books may share a name (nothing forbids it), and two identical buttons
    send money to whichever one is tapped. The second is numbered so the person
    can tell them apart; the books themselves are untouched.
    """
    seen: dict = {}
    names: dict = {}
    for book in books:
        seen[book.name] = seen.get(book.name, 0) + 1
        names[book.id] = book.name if seen[book.name] == 1 else f"{book.name} ({seen[book.name]})"
    return names


def _book_buttons(books: Sequence[Book], data) -> List[List[Button]]:
    """One button per book: its mark and name, not its type spelled out."""
    names = _book_names(books)
    return [[Button(f"{_book_mark(b)} {names[b.id]}", data=data(b))] for b in books]


def _book_mark(book: Book) -> str:
    return BOOK_LABELS.get(book.type, "").split(" ")[0]


def stale(current: Optional[Screen], display_name: str) -> Screen:
    """The answer to a button whose message is no longer the live one.

    If there is a draft waiting, it is shown right below, so the person can carry
    on with that one instead of wondering what the tap did.
    """
    if current is None:
        return with_notice("این دکمه قدیمی است یا کارش قبلاً انجام شده؛ ادامه از همین‌جا:",
                           welcome(display_name))
    return with_notice("این پیام قدیمی است؛ پیش‌نویس فعلی:", current)


def cancelled(display_name: str) -> Screen:
    """Said whenever انصراف clears a draft, so nobody wonders if it was kept."""
    return with_notice("انصراف دادی؛ چیزی ثبت نشد.", welcome(display_name))


# What each way a line can be unclear tells the person, with an example that works.
_UNCLEAR = {
    "several": "چند عدد دیدم ({numbers}) و نفهمیدم کدام مبلغ است.\nمبلغ را بلافاصله بعد از دسته بنویس و تعداد را بعدش؛ مثلاً: «خرید نان 20000 2 عدد»",
    "grouping": "«{numbers}» را نمی‌شود با اطمینان خواند: 1.5 است یا 15؟\nبرای اعشار از نقطه بنویس و برای هزارگان از ویرگول؛ مثلاً: 1.5م یا 1,500,000",
    "dots": "«{numbers}» 250 است یا 250,000؟\nبرای هزارگان از ویرگول بنویس؛ مثلاً: 250,000",
    "rial": "«{numbers}» ریال است؟ دفتر با تومان حساب می‌شود.\nمبلغ را به تومان بنویس؛ مثلاً: «فروش 25000»",
    "nocategory": "مبلغ {numbers} را دیدم ولی نفهمیدم برای چیست.\nاول دسته را بنویس؛ مثلاً: «فروش 250000»",
    "zero": "مبلغ باید بیشتر از صفر باشد.\nمثال: «فروش 250000»",
    "compound": "نفهمیدم «{numbers}» یک مبلغ است یا دو مبلغ.\nمبلغ را یک‌جا بنویس؛ مثلاً 2500000 یا «2 میلیون و 500 هزار».",
}


def unclear_reason(reason: str, numbers: Sequence[str]) -> str:
    """Why an amount could not be read, and how to write it so it can."""
    return _UNCLEAR.get(reason, _UNCLEAR["several"]).format(numbers=" و ".join(numbers))


def error(message: str, back: Optional[str] = None) -> Screen:
    """A refusal. With `back` the person returns to where they were, not home."""
    if back:
        return rtl(f"⚠️ {message}"), [[Button("⬅️ بازگشت", data=back)]]
    return rtl(f"⚠️ {message}"), [[Button("⬅️ منوی اصلی", data="nav:home")]]


# Domain errors reach the bot in whatever language the service wrote them. The
# services' own English messages are for logs and the API; a person reads
# Persian. Mapped here, at the boundary, so no rule moves and no message is lost.
_ENGLISH_ERRORS = {
    "an entry of zero moves nothing": "مبلغ باید بیشتر از صفر باشد.",
    "an amount is never negative; use the other flow": "مبلغ نمی‌تواند منفی باشد.",
    "a conversion rate must be positive": "نرخ تبدیل باید بیشتر از صفر باشد.",
    "a journal line is never negative": "مبلغ نمی‌تواند منفی باشد.",
    "the owner cannot be removed from their own book": "مالک دفتر را نمی‌شود از دفتر خودش حذف کرد.",
    "this person is already a member": "این شخص قبلاً عضو دفتر شده است.",
    "only the owner may delete a book": "فقط مالک دفتر می‌تواند آن را حذف کند.",
    "only the owner may hand a book over": "فقط مالک دفتر می‌تواند آن را واگذار کند.",
    "a period cannot end before it starts": "پایان دوره نمی‌تواند قبل از شروعش باشد.",
    "this period is locked; record a correction in a later one":
        "این دوره قفل است؛ اصلاح را در دورهٔ بعدی ثبت کن.",
}


def user_message(exc: Exception) -> str:
    """The sentence a person sees for a domain error: Persian, with a way forward."""
    from ...shared.errors import (
        BalanceError, NotFound, PermissionDenied, ValidationError,
    )

    message = str(exc).strip()
    if any("\u0600" <= ch <= "\u06ff" for ch in message):
        return message
    if message in _ENGLISH_ERRORS:
        return _ENGLISH_ERRORS[message]
    if isinstance(exc, NotFound):
        return "این مورد پیدا نشد؛ شاید حذف شده یا مال تو نیست."
    if isinstance(exc, PermissionDenied):
        return "اجازهٔ این کار را نداری."
    if isinstance(exc, BalanceError):
        return "ثبت انجام نشد؛ مبلغ را بررسی کن و دوباره امتحان کن."
    if isinstance(exc, ValidationError):
        return "ورودی درست نیست؛ بررسی کن و دوباره امتحان کن."
    return "کار انجام نشد؛ دوباره امتحان کن."


def confirm_delete(what: str, yes_data: str, no_data: str) -> Screen:
    return rtl(f"⚠️ حذف {what}\n\nمطمئنی؟"), [
        [Button("🗑 بله، حذف کن", data=yes_data)],
        [Button("↩️ انصراف", data=no_data)],
    ]


# ----------------------------------------------------------------- payroll
PERIOD_LABELS = {
    "open": "🟢 باز",
    "calculating": "🧮 در حال محاسبه",
    "awaiting_approval": "⏳ منتظر تأیید",
    "approved": "✅ تأییدشده",
    "paid": "💵 پرداخت‌شده",
    "locked": "🔒 بسته",
}
