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
        [Button("👤 حساب من", data="acc:panel")],
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


def ask_category(flow: Flow, recent: Sequence[str] = ()) -> Screen:
    """Ask, but offer what this book already uses.

    A category is typed on every single entry, so the recent ones are the
    highest-value buttons in the whole bot. They are offered by *index* rather
    than by name: a category is free text up to eighty characters, and Telegram
    gives a callback payload sixty-four bytes — a Persian category would
    overflow it and the button would silently fail to send.
    """
    word = "درآمد" if flow is Flow.INCOME else "هزینه"
    text = rtl(f"دستهٔ این {word} چیست؟\n\nمثلاً: فروش، اجاره، حقوق")

    buttons: List[List[Button]] = []
    row: List[Button] = []
    for index, category in enumerate(recent[:6]):
        row.append(Button(category[:18], data=f"tx:cat:{index}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([Button("↩️ انصراف", data="nav:home")])
    return text, buttons


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
def account_created(display_name: str) -> Screen:
    """A brand-new account is reachable from this messenger and nowhere else.

    Saying so now is much cheaper than explaining it to someone who has lost
    their Telegram account and their books with it.
    """
    return rtl(
        f"✅ حسابت ساخته شد، {display_name}.\n\n"
        "فعلاً فقط از همین پیام‌رسان به آن می‌رسی. اگر این حساب را از دست بدهی، "
        "دفترهایت هم می‌روند.\n\n"
        "یک ایمیل یا شماره اضافه کن تا حسابت راه برگشت داشته باشد."
    ), [
        [Button("📧 افزودن ایمیل یا شماره", data="acc:contact")],
        [Button("بعداً", data="nav:home")],
    ]


def account_panel(user, identities: Iterable[Identity], current: Provider) -> Screen:
    """Everything about the account itself, rather than about its books."""
    rows = list(identities)
    lines = [f"👤 {user.display_name}", ""]

    lines.append(f"📧 ایمیل: {user.email or 'ندارد'}")
    lines.append(f"📱 شماره: {user.phone or 'ندارد'}")
    lines.append(f"🔑 رمز: {'دارد' if user.password_hash else 'ندارد'}")
    lines.append(f"🕐 منطقهٔ زمانی: {user.timezone}")

    lines += ["", "🔗 پیام‌رسان‌های متصل:"]
    for identity in rows:
        label = PROVIDER_LABELS.get(identity.provider, identity.provider.value)
        who = identity.external_username or identity.external_id
        here = " ← همین‌جا" if identity.provider is current else ""
        lines.append(f"  • {label}: {who}{here}")

    if not user.email and not user.phone:
        lines += [
            "",
            "⚠️ این حساب راه برگشت ندارد. اگر پیام‌رسانت را از دست بدهی، "
            "دفترهایت هم می‌روند.",
        ]
    elif not user.password_hash:
        lines += ["", "برای ورود از وب یا API، یک رمز تعیین کن."]

    return rtl("\n".join(lines)), [
        [Button("✏️ نام", data="acc:name"),
         Button("🕐 منطقهٔ زمانی", data="acc:tz")],
        [Button("📧 ایمیل", data="acc:email"),
         Button("📱 شماره", data="acc:phone")],
        [Button("🔑 " + ("تغییر رمز" if user.password_hash else "تعیین رمز"),
                data="acc:pw")],
        [Button("🖥 نشست‌های فعال", data="acc:sessions")],
        [Button("🗑 حذف حساب", data="acc:close")],
        [Button("⬅️ بازگشت", data="nav:home")],
    ]


def ask_email() -> Screen:
    return rtl(
        "📧 ایمیلت را بنویس.\n\n"
        "با همین می‌توانی از وب وارد شوی، و اگر پیام‌رسانت را از دست دادی "
        "حسابت را برگردانی."
    ), [[Button("⬅️ انصراف", data="acc:panel")]]


def ask_phone() -> Screen:
    return rtl(
        "📱 شماره‌ات را بنویس.\n\nمثلاً: ۰۹۱۲۱۲۳۴۵۶۷"
    ), [[Button("⬅️ انصراف", data="acc:panel")]]


def ask_current_password() -> Screen:
    return rtl(
        "🔑 اول رمز فعلی را بنویس.\n\n"
        "پیامت بلافاصله پاک می‌شود."
    ), [[Button("⬅️ انصراف", data="acc:panel")]]


def ask_new_password(changing: bool) -> Screen:
    what = "رمز تازه" if changing else "رمزی که می‌خواهی"
    return rtl(
        f"🔑 {what} را بنویس.\n\n"
        "دست‌کم ۸ نویسه.\n"
        "پیامت بلافاصله پاک می‌شود، ولی جای امنی نگهش دار."
    ), [[Button("⬅️ انصراف", data="acc:panel")]]


def ask_display_name(current: str) -> Screen:
    return rtl(f"✏️ نام تازه چه باشد؟\n\nالان: {current}"), [
        [Button("⬅️ انصراف", data="acc:panel")]
    ]


def ask_timezone(current: str) -> Screen:
    return rtl(
        f"🕐 منطقهٔ زمانی\n\nالان: {current}\n\n"
        "این ساعتی را تعیین می‌کند که خلاصهٔ روزانه به دستت می‌رسد."
    ), [
        [Button("تهران", data="acc:tzset:Asia/Tehran")],
        [Button("دبی", data="acc:tzset:Asia/Dubai"),
         Button("استانبول", data="acc:tzset:Europe/Istanbul")],
        [Button("لندن", data="acc:tzset:Europe/London"),
         Button("برلین", data="acc:tzset:Europe/Berlin")],
        [Button("تورنتو", data="acc:tzset:America/Toronto")],
        [Button("⬅️ بازگشت", data="acc:panel")],
    ]


def session_list(sessions) -> Screen:
    """Where this account is signed in, so a surprise can be noticed."""
    from ..shared import jalali

    rows = list(sessions)
    if not rows:
        return rtl(
            "🖥 هیچ نشست فعالی نداری.\n\n"
            "نشست وقتی ساخته می‌شود که از وب یا API وارد شوی."
        ), [[Button("⬅️ بازگشت", data="acc:panel")]]

    lines = ["🖥 نشست‌های فعال:", ""]
    for row in rows[:10]:
        where = row.ip_address or "نامشخص"
        agent = (row.user_agent or "")[:40] or "نامشخص"
        lines.append(f"• {jalali.to_text(row.created_at.date())} — {where}\n  {agent}")

    lines += ["", "اگر چیزی این‌جا را نمی‌شناسی، همه را خارج کن و رمزت را عوض کن."]
    return rtl("\n".join(lines)), [
        [Button("🚪 خروج از همهٔ نشست‌ها", data="acc:signout")],
        [Button("⬅️ بازگشت", data="acc:panel")],
    ]


CLOSE_WORD = "حذف"


def confirm_close(preview) -> Screen:
    """Say exactly what will be destroyed before asking anyone to agree to it.

    "Are you sure?" is a useless question when the person cannot see what they
    are agreeing to.
    """
    if preview.blocked:
        return rtl(
            "🚫 هنوز نمی‌شود\n\n"
            "این دفترها عضو دیگری دارند و مال تو تنها نیستند:\n"
            + "\n".join(f"  • {name}" for name in preview.books_to_hand_over)
            + "\n\nاول هرکدام را به یکی از اعضایش واگذار کن، بعد دوباره بیا."
        ), [[Button("⬅️ بازگشت", data="acc:panel")]]

    lines = ["⚠️ حذف حساب", ""]
    if preview.books_to_delete:
        lines.append("این دفترها با همهٔ تراکنش‌هایشان پاک می‌شوند:")
        lines += [f"  • {name}" for name in preview.books_to_delete]
        lines.append("")
    if preview.other_books_left:
        lines.append(
            f"از {preview.other_books_left} دفتر دیگر بیرون می‌آیی، ولی آن دفترها "
            "می‌مانند."
        )
        lines.append("")
    lines += [
        "ایمیل، شماره، رمز و پیام‌رسان‌های متصلت پاک می‌شوند و دیگر نمی‌توانی "
        "وارد شوی.",
        "",
        "اگر در دفتر کسِ دیگری تراکنشی ثبت کرده باشی، آن تراکنش می‌ماند — "
        "چون پول واقعاً جابه‌جا شده — ولی دیگر نام تو را ندارد.",
        "",
        "این کار برگشت ندارد.",
    ]
    return rtl("\n".join(lines)), [
        [Button("🗑 می‌دانم، حذف کن", data="acc:closeok")],
        [Button("⬅️ منصرف شدم", data="acc:panel")],
    ]


def ask_close_word() -> Screen:
    return rtl(
        f"برای تأیید نهایی کلمهٔ «{CLOSE_WORD}» را بنویس.\n\n"
        "هر چیز دیگری بنویسی، لغو می‌شود."
    ), [[Button("⬅️ منصرف شدم", data="acc:panel")]]


def account_closed(removed: bool) -> Screen:
    """The last screen this account ever sees."""
    if removed:
        text = (
            "حسابت پاک شد.\n\n"
            "چیزی از تو نمانده. اگر روزی برگردی، از صفر شروع می‌کنی."
        )
    else:
        text = (
            "حسابت بسته شد.\n\n"
            "همهٔ اطلاعات شخصی‌ات پاک شد. تراکنش‌هایی که در دفتر دیگران ثبت "
            "کرده بودی مانده‌اند، چون آن پول واقعاً جابه‌جا شده — ولی دیگر به "
            "تو وصل نیستند."
        )
    return rtl("👋 " + text), [[Button("شروع دوباره", data="acc:create")]]


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
        # Only where there is more than one person to pay. On a personal book
        # the whole idea is noise, so it is not offered.
        *([[Button("👥 حقوق و سهم", data=f"pr:list:{book.id}")]]
          if book.type in (BookType.TEAM, BookType.ORGANIZATION) else []),
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


RECEIPT_KINDS = {
    "photo": "عکس",
    "document": "فایل",
    "voice": "صدا",
}


def _receipt_line(tx) -> str:
    """"دارد" is true but unhelpful once a receipt can be a PDF invoice."""
    if not tx.receipt_file_id:
        return "ندارد"

    label = RECEIPT_KINDS.get(tx.receipt_kind or "", "دارد")
    # The name is the useful part when there is one; a till-roll photo has none.
    return f"{label} — {tx.receipt_file_name}" if tx.receipt_file_name else label


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
    lines.append("🧾 رسید: " + _receipt_line(tx))

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


# ---------------------------------------------------------------- treasury
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
            "مثل ذخیرهٔ اضطراری یا کنارگذاشتن مالیات."
        ), [
            [Button("➕ صندوق تازه", data=f"tf:add:{book.id}")],
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

    buttons = [[Button("➕ صندوق تازه", data=f"tf:add:{book.id}")]]
    for fund, _ in funds_with_balance[:10]:
        buttons.append([Button(f"{fund.name[:20]}", data=f"tf:open:{fund.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"pr:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def fund_ask_name() -> Screen:
    return rtl(
        "🏦 نام صندوق چیست؟\n\nمثلاً: ذخیرهٔ اضطراری، مالیات، توسعه"
    ), [[Button("⬅️ انصراف", data="nav:home")]]


def fund_pick_kind(name: str) -> Screen:
    return rtl(f"«{name}» از چه نوعی است؟"), [
        [Button("🏦 اصلی", data="tf:kind:main"),
         Button("🚨 اضطراری", data="tf:kind:emergency")],
        [Button("🧾 مالیات", data="tf:kind:tax"),
         Button("🌱 توسعه", data="tf:kind:development")],
        [Button("🛠 تجهیزات", data="tf:kind:equipment"),
         Button("🎁 پاداش", data="tf:kind:bonus")],
        [Button("⬅️ انصراف", data="nav:home")],
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
        [Button("⬅️ انصراف", data="nav:home")],
    ]


def rule_ask_value(basis: str) -> Screen:
    if basis == "fixed":
        return rtl("چه مبلغی هر دوره کنار گذاشته شود؟\n\nمثلاً: ۵م"), [
            [Button("⬅️ انصراف", data="nav:home")]
        ]
    return rtl("چند درصد؟\n\nفقط عدد بنویس. مثلاً: ۱۰"), [
        [Button("⬅️ انصراف", data="nav:home")]
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


def period_detail(book: Book, period, distribution, slip_count: int) -> Screen:
    """The whole arithmetic, shown rather than asserted.

    Every line of it is here on purpose: someone about to be paid a share of a
    number should be able to see how that number was reached.
    """
    currency = book.base_currency
    state = PERIOD_LABELS.get(period.status.value, period.status.value)

    lines = [
        f"📅 {period.label}",
        f"وضعیت: {state}",
        "",
        f"درآمد دوره:     {fmt(distribution.gross_income, currency)}",
        f"هزینهٔ دوره:    {fmt(distribution.direct_costs, currency)}",
        f"سود خالص:      {fmt(distribution.net_profit, currency)}",
    ]
    if distribution.treasury_total:
        lines.append(f"سهم خزانه:     {fmt(distribution.treasury_total, currency)}")
    lines += [
        "",
        f"قابل تقسیم:    {fmt(distribution.distributable, currency)}",
    ]

    if slip_count:
        lines += ["", f"{slip_count} فیش صادر شده."]

    buttons = []
    if period.status.value not in ("locked", "paid"):
        buttons.append([Button("🧮 محاسبهٔ فیش‌ها", data=f"pr:calc:{period.id}")])
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
    if period.status.value == "approved":
        buttons.append([Button("🔒 بستن دوره", data=f"pr:lock:{period.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"pr:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def payslip_list(book: Book, slips, names) -> Screen:
    if not slips:
        return rtl(
            "💵 هنوز فیشی صادر نشده.\n\n"
            "«محاسبهٔ فیش‌ها» را بزن تا سهم هر نفر حساب شود."
        ), [[Button("⬅️ بازگشت", data="nav:home")]]

    currency = book.base_currency
    lines = ["💵 فیش‌های این دوره", ""]
    total = Decimal("0")
    for slip in slips:
        total += slip.net_pay
        paid = sum((p.amount for p in slip.payments), Decimal("0"))
        mark = "✅" if paid >= slip.net_pay else ("🟡" if paid else "⚪️")
        lines.append(
            f"{mark} {names.get(slip.user_id, '—')}: {fmt(slip.net_pay, currency)}"
        )
    lines += ["", f"مجموع: {fmt(total, currency)}"]

    buttons = [
        [Button(f"{names.get(slip.user_id, '—')[:18]}", data=f"pr:slip:{slip.id}")]
        for slip in slips[:10]
    ]
    buttons.append([Button("⬅️ بازگشت", data=f"pr:open:{slips[0].period_id}")])
    return rtl("\n".join(lines)), buttons


def payslip_detail(book: Book, slip, name: str) -> Screen:
    """One person's slip, with every input that produced it."""
    currency = book.base_currency
    paid = sum((p.amount for p in slip.payments), Decimal("0"))
    outstanding = slip.net_pay - paid

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
            lines.append(f"  • {fmt(payment.amount, currency)} — {payment.paid_on}")
        lines.append("")
        lines.append(
            f"مانده: {fmt(outstanding, currency)}" if outstanding > 0
            else "کامل پرداخت شده ✅"
        )

    buttons = []
    if outstanding > 0:
        buttons.append([
            Button(f"💵 پرداخت کامل ({fmt(outstanding, currency)})",
                   data=f"pr:payall:{slip.id}")
        ])
        buttons.append([Button("✏️ پرداخت جزئی", data=f"pr:pay:{slip.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"pr:slips:{slip.period_id}")])
    return rtl("\n".join(lines)), buttons


def payslip_ask_amount(name: str, outstanding: Decimal, currency: str) -> Screen:
    return rtl(
        f"چقدر به {name} پرداخت شد؟\n\n"
        f"مانده: {fmt(outstanding, currency)}\n"
        "مثلاً: ۵م"
    ), [[Button("⬅️ انصراف", data="nav:home")]]


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
        "مثلاً: ۲م یا ‎-۵۰۰ک"
    ), [[Button("⬅️ انصراف", data="nav:home")]]


def adjustment_ask_reason() -> Screen:
    return rtl("بابت چه چیزی؟\n\nمثلاً: پاداش پروژه، جریمهٔ تأخیر"), [
        [Button("بدون توضیح", data="pr:adjnoreason")],
        [Button("⬅️ انصراف", data="nav:home")],
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
            lines.append("⚠️ بیشتر از ۱۰۰٪ است — بیش از قابل‌تقسیم پرداخت می‌شود.")
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
        return rtl(f"{name} چند درصد بگیرد؟\n\nفقط عدد. مثلاً: ۵۰"), [
            [Button("⬅️ انصراف", data="sh:list")]
        ]
    if basis == "fixed":
        return rtl(f"{name} هر دوره چه مبلغی بگیرد؟\n\nمثلاً: ۱۵م"), [
            [Button("⬅️ انصراف", data="sh:list")]
        ]

    unit = {"hours": "ساعت", "days": "روز", "points": "امتیاز"}.get(basis, "واحد")
    return rtl(
        f"ضریب {name} چند باشد؟\n\n"
        f"سهمش به نسبت {unit}هایی که در هر دوره ثبت می‌شود حساب می‌شود، "
        f"ضربدر این عدد.\nبرای وزن برابر ۱ بنویس."
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
        [Button("⬅️ انصراف", data="nav:home")]
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
