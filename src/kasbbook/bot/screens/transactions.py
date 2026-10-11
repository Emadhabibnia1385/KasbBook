"""Entry screens: recording, the quick line, the daily list, a card, receipts, search."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Sequence

from ...adapters.base import Button
from ...modules.books.models import Book, BookType
from ...modules.exchange.models import CURRENCY_NAMES
from ...modules.ledger.models import Flow, Scope
from ...shared import jalali
from .common import (
    Screen,
    _book_buttons,
    _book_mark,
    _problem,
    fmt,
    fmt_currency,
    main_menu,
    rtl,
    unclear_reason,
)


def pick_book(books: Sequence[Book], purpose: str = "tx") -> Screen:
    """The question every recording flow starts with: whose money is this?"""
    if not books:
        return (
            rtl("هنوز دفتری نداری. اول یک دفتر بساز (مثلاً «مغازه»)، بعد تراکنش‌هایت را در آن ثبت کن."),
            [[Button("➕ ساخت دفتر", data="book:new")], [Button("⬅️ بازگشت", data="nav:home")]],
        )

    buttons = _book_buttons(books, lambda b: f"{purpose}:book:{b.id}")
    buttons.append([Button("⬅️ بازگشت", data="nav:home")])
    return rtl("این تراکنش مربوط به کدام دفتر است؟"), buttons


# ------------------------------------------------------------- transactions
# How a transaction is described when its type is chosen. The codes are two
# letters because a daily-list button already spends forty-four of Telegram's
# sixty-four callback bytes on a book id and a date.
ENTRY_TYPES = {
    # One word per concept: درآمد and هزینه. "شخصی" survives only where it is
    # the thing that tells two entries in the same book apart.
    "wi": (Flow.INCOME, Scope.WORK, "💰", "درآمد"),
    "we": (Flow.EXPENSE, Scope.WORK, "🧾", "هزینه"),
    "ti": (Flow.INCOME, Scope.TEAM, "💰", "درآمد"),
    "te": (Flow.EXPENSE, Scope.TEAM, "🧾", "هزینه"),
    "pi": (Flow.INCOME, Scope.PERSONAL, "💵", "درآمد شخصی"),
    "pe": (Flow.EXPENSE, Scope.PERSONAL, "👤", "هزینه شخصی"),
}


# What each kind of book offers. A team book has no personal money — keeping
# someone's groceries out of it is what scope exists for — and a household has
# no business. A shop has both, which is the four-way split the first
# generation's daily list was built around.
TYPES_FOR_BOOK = {
    BookType.BUSINESS: ("wi", "we", "pi", "pe"),
    BookType.PERSONAL: ("pi", "pe"),
    BookType.TEAM: ("ti", "te"),
    BookType.ORGANIZATION: ("ti", "te"),
}


# The business first, then the person — the order the old list was read in.
# Every flow and scope pair is here, so no transaction can fall out of the list.
SECTION_ORDER = ("wi", "we", "ti", "te", "pi", "pe")


DAY_PAGE = 12


def day_token(value: date) -> str:
    """A date as it travels in a button: eight bytes, and still readable in a log."""
    return value.strftime("%Y%m%d")


def _entry_code(flow: Flow, scope: Scope) -> str:
    for code, (entry_flow, entry_scope, _, _) in ENTRY_TYPES.items():
        if entry_flow is flow and entry_scope is scope:
            return code
    return "we"


def _pairs(buttons: List[Button], per_row: int = 2) -> List[List[Button]]:
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def entry_label(code: str, book: Book) -> str:
    """What a type button says. A personal book has no other kind of money."""
    label = ENTRY_TYPES[code][3]
    if book.type is BookType.PERSONAL:
        label = label.replace(" شخصی", "")
    return label


def tx_home(today: date) -> Screen:
    """The two ways in that the first generation had, and people kept asking for."""
    return rtl(
        "📌 ثبت تراکنش\n\n"
        "• ثبت تراکنش — قدم‌به‌قدم، با هر تاریخی\n"
        "• تراکنش‌های هر روز — دیدن، ویرایش، حذف\n\n"
        "راه سریع: یک خط بنویس، مثلاً «فروش 250ک»."
    ), [
        [Button("➕ ثبت تراکنش", data="tx:one")],
        [Button("📅 تراکنش‌های هر روز", data=f"dl:v:{day_token(today)}:a:0")],
        [Button("⬅️ بازگشت", data="nav:home")],
    ]


def pick_date(book: Book, today: date) -> Screen:

    return rtl(f"دفتر {book.name}\n\nتاریخ این تراکنش؟"), [
        [Button(f"✅ امروز ({jalali.to_text(today)})", data="tx:on:today")],
        [Button("✍️ تاریخ دیگر", data="tx:on:ask")],
        [Button("⬅️ بازگشت", data="tx:new")],
    ]


def ask_date(cancel_data: str, typed: Optional[str] = None) -> Screen:
    """One prompt for both calendars: the parser tells them apart by the year."""
    return rtl(
        (f"⚠️ «{typed}» را به‌عنوان تاریخ نفهمیدم.\n\n" if typed else "")
        + "تاریخ را بنویس؛ مثلاً 1404/12/28 یا «دیروز».\n"
        "تاریخ میلادی هم می‌شود (2026-03-19). «امروز» و «فردا» هم می‌شود."
    ), [[Button("↩️ انصراف", data=cancel_data)]]


def pick_type(book: Book, on: date) -> Screen:

    buttons = _pairs([
        Button(f"{ENTRY_TYPES[code][2]} {entry_label(code, book)}", data=f"tx:type:{code}")
        for code in TYPES_FOR_BOOK.get(book.type, ("wi", "we"))
    ])
    buttons.append([Button("⬅️ بازگشت", data="tx:new")])
    return rtl(f"دفتر {book.name} · {jalali.to_text(on)}\n\nدرآمد است یا هزینه؟"), buttons


def daily_pick_type(book: Book, on: date) -> Screen:
    """Adding from the all-books list: the book is chosen, now what kind of entry."""

    token = day_token(on)
    buttons = _pairs([
        Button(f"{ENTRY_TYPES[code][2]} {entry_label(code, book)}",
               data=f"dl:add:{token}:{book.id}:{code}:a")
        for code in TYPES_FOR_BOOK.get(book.type, ("wi", "we"))
    ])
    buttons.append([Button("⬅️ بازگشت", data=f"dl:v:{token}:a:0")])
    return rtl(f"دفتر {book.name} · {jalali.to_text(on)}\n\nچه چیزی ثبت شود؟"), buttons


def _day_summary(sheet) -> List[str]:
    """The first generation's lines, for whichever of them this book can have.

    A line is shown when the book's kind implies it or when there is money on
    it, so an unusual entry — a loan installment in a team book, say — is never
    in the list below and missing from the totals above. A line that would only
    say zero because it can't apply (no installment) is left out.
    """
    totals, kind = sheet.totals, sheet.book.type
    team = kind in (BookType.TEAM, BookType.ORGANIZATION)
    has_business = kind is not BookType.PERSONAL or bool(
        totals.business_income or totals.business_expense
    )
    has_personal = not team or bool(
        totals.personal_income or totals.personal_expense or totals.installment
    )

    lines: List[str] = []
    if has_business:
        word = "" if team else " کاری"
        lines += [
            f"💰 درآمد{word}: {fmt(totals.business_income)}",
            f"🧾 هزینه{word}: {fmt(totals.business_expense)}",
            f"➖ سود{word}: {fmt(totals.business_net)}",
        ]
    if has_personal:
        if totals.personal_income or kind is BookType.PERSONAL:
            lines.append(f"💵 درآمد شخصی: {fmt(totals.personal_income)}")
        lines.append(f"👤 هزینه شخصی: {fmt(totals.personal_expense)}")
        if totals.installment:
            lines += [
                f"قسط وام: {fmt(totals.installment)}",
                f"💾 مانده پس از هزینه‌ها: {fmt(totals.savings_operational)}",
                f"💾 مانده پس از قسط: {fmt(totals.savings_final)}",
            ]
        else:
            lines.append(f"💾 مانده پس از هزینه‌ها: {fmt(totals.savings_final)}")
    return lines


def daily_view(
    on: date,
    today: date,
    sheets,
    books: Sequence[Book],
    filter_book_id=None,
    page: int = 0,
    per_page: int = DAY_PAGE,
) -> Screen:
    """The first generation's daily list, across every book the person is on.

    Each book keeps its own summary — a team's revenue is not its members'
    savings — and the filter narrows the list to one of them.
    """

    token = day_token(on)
    view = "a" if filter_book_id is None else str(filter_book_id)
    # Where a transaction opened from here should come back to: all books, or
    # "the book this transaction is in", which needs no id of its own.
    origin = "a" if filter_book_id is None else "b"
    single = len(sheets) == 1
    here = f"dl:v:{token}:{view}:{page}"

    lines = [f"📅 {jalali.to_text(on)}"]
    if filter_book_id is not None and sheets:
        lines.append(f"🔎 فقط: {_book_mark(sheets[0].book)} {sheets[0].book.name}")
    lines += ["", "خلاصهٔ روز"]

    # One book is always summarised, zeros included, as the old list was. Of
    # several, only the ones that moved today — five blocks of zeros bury the
    # one that matters.
    shown = [sheet for sheet in sheets if single or sheet.rows]
    if not shown:
        lines.append("برای این روز هنوز چیزی ثبت نشده.")
    for sheet in shown:
        if not single:
            lines += ["", f"— {_book_mark(sheet.book)} {sheet.book.name} —"]
        lines += _day_summary(sheet)

    buttons: List[List[Button]] = []

    recordable = [sheet for sheet in sheets if sheet.can_record]
    if single and recordable:
        book = sheets[0].book
        buttons += _pairs([
            Button(f"➕ {ENTRY_TYPES[code][3]}", data=f"dl:add:{token}:{book.id}:{code}:{origin}")
            for code in TYPES_FOR_BOOK.get(book.type, ("wi", "we"))
        ])
    elif recordable:
        buttons += _pairs([
            Button(f"➕ {_book_mark(sheet.book)} {sheet.book.name}"[:30],
                   data=f"dl:ab:{token}:{sheet.book.id}")
            for sheet in recordable
        ])

    buttons.append([
        Button("◀️ روز قبل", data=f"dl:v:{day_token(on - timedelta(days=1))}:{view}:0"),
        Button("📆 تاریخ", data=f"dl:go:{view}"),
        Button("روز بعد ▶️", data=f"dl:v:{day_token(on + timedelta(days=1))}:{view}:0"),
    ])
    if on != today:
        buttons.append([Button("↩️ امروز", data=f"dl:v:{day_token(today)}:{view}:0")])

    # Filters only mean something when there is more than one book to filter.
    if len(books) > 1:
        chips = [Button(("✅ " if filter_book_id is None else "") + "همه",
                        data=f"dl:v:{token}:a:0")]
        for book in books:
            mark = "✅ " if book.id == filter_book_id else ""
            chips.append(Button(f"{mark}{_book_mark(book)} {book.name}"[:24],
                                data=f"dl:v:{token}:{book.id}:0"))
        buttons += _pairs(chips, 3)

    entries = [
        (sheet, code, tx)
        for sheet in sheets
        for code in SECTION_ORDER
        for tx in sheet.rows
        if _entry_code(tx.flow, tx.scope) == code
    ]
    last = max(0, (len(entries) - 1) // per_page)
    page = max(0, min(page, last))

    current = None
    for sheet, code, tx in entries[page * per_page:(page + 1) * per_page]:
        if (sheet.book.id, code) != current:
            current = (sheet.book.id, code)
            count = sum(1 for s, c, _ in entries if s is sheet and c == code)
            where = "" if single else f"{_book_mark(sheet.book)} {sheet.book.name} · "
            # A header is not a button anyone means to press. Pressing it
            # redraws this same list, rather than leaving for somewhere else.
            buttons.append([Button(f"— {where}{ENTRY_TYPES[code][3]} ({count}) —", data=here)])
        buttons.append([
            Button(tx.category[:24], data=f"td:open:{tx.id}:{origin}"),
            Button(fmt(tx.converted_amount), data=f"td:open:{tx.id}:{origin}"),
        ])

    if last:
        nav: List[Button] = []
        if page > 0:
            nav.append(Button("◀️ قبلی", data=f"dl:v:{token}:{view}:{page - 1}"))
        nav.append(Button(f"{page + 1}/{last + 1}", data=here))
        if page < last:
            nav.append(Button("بعدی ▶️", data=f"dl:v:{token}:{view}:{page + 1}"))
        buttons.append(nav)

    buttons.append([Button("⬅️ بازگشت", data="tx:new")])
    return rtl("\n".join(lines)), buttons


def ask_category(flow: Flow, recent: Sequence[str] = (), problem: Optional[str] = None) -> Screen:
    """Ask, but offer what this book already uses.

    A category is typed on every single entry, so the recent ones are the
    highest-value buttons in the whole bot. They are offered by *index* rather
    than by name: a category is free text up to eighty characters, and Telegram
    gives a callback payload sixty-four bytes — a Persian category would
    overflow it and the button would silently fail to send.
    """
    word = "درآمد" if flow is Flow.INCOME else "هزینه"
    text = rtl(_problem(problem) + f"دستهٔ این {word} چیست؟\n\nمثال: فروش، اجاره، حقوق")

    buttons: List[List[Button]] = []
    row: List[Button] = []
    for index, category in enumerate(recent[:6]):
        row.append(Button(category[:18], data=f"tx:cat:{index}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([Button("↩️ انصراف", data="nav:cancel")])
    return text, buttons


def ask_amount(category: str, currency: str | None = None, problem: Optional[str] = None,
               current: Optional[str] = None) -> Screen:
    """`current` is shown when an existing amount is being changed."""
    return (
        rtl(
            _problem(problem)
            + f"دسته: {category}\n"
            + (f"مبلغ فعلی: {current}\n" if current else "")
            + "\n"
            + (f"مبلغ اصلی به {CURRENCY_NAMES.get(currency, currency)} است؛ نرخ تبدیل ثبت‌شده حفظ می‌شود.\n" if currency else "")
            + "مبلغ را بنویس؛ مثلاً 250000 یا 250ک یا 1.2م"
        ),
        [[Button("↩️ انصراف", data="nav:cancel")]],
    )


def transaction_saved(
    book: Book, flow: Flow, category: str, amount: Decimal, currency: str,
    on: Optional[date] = None, note: Optional[str] = None,
) -> Screen:
    """What was recorded, said back in full so a wrong reading is seen at once."""

    word = "درآمد" if flow is Flow.INCOME else "هزینه"
    facts = [category, f"دفتر {book.name}"]
    if on is not None:
        facts.append(jalali.to_text(on))
    lines = [f"✅ {word} {fmt(amount, currency)} ثبت شد", " · ".join(facts)]
    if note:
        lines.append(note)
    return rtl("\n".join(lines)), [
        [Button("➕ ثبت بعدی", data="tx:new")],
        [Button("📊 گزارش این دفتر", data=f"rep:book:{book.id}")],
        [Button("⬅️ منوی اصلی", data="nav:home")],
    ]


# --------------------------------------------------------------- quick entry
def _quick_facts(entry, book: Optional[Book], today: Optional[date]) -> str:
    """Everything the line was understood as, so a wrong reading is seen before the tap.

    The amount, the category, the day (said as «امروز» when none was typed, since
    that is what will be recorded), the book and the note. A person who typed
    «۲ عدد نان ۲۰۰۰۰» can see here that 20,000 was taken as the amount.
    """

    lines = [f"{entry.category} — {fmt(entry.amount, 'IRT')}"]
    when = entry.on or today
    if when is not None:
        day = jalali.to_text(when)
        lines.append(f"{day}" if entry.on else f"امروز ({day})")
    if book is not None:
        lines[-1] += f" · دفتر {book.name}"
    if entry.description:
        lines.append(f"توضیح: {entry.description}")
    return "\n".join(lines)


def quick_pick_book(entry, books: Sequence[Book], nonce: str,
                    today: Optional[date] = None) -> Screen:
    """A one-line entry still has to say which book it belongs to.

    Every button carries the draft's nonce: the chat keeps old messages, and a
    button from an earlier line must not act on a later one.
    """
    text = rtl(_quick_facts(entry, None, today) + "\n\nدر کدام دفتر ثبت شود؟")
    rows = _book_buttons(books, lambda b: f"qk:book:{b.id}:{nonce}")
    rows.append([Button("↩️ انصراف", data="nav:cancel")])
    return text, rows


def quick_pick_flow(entry, nonce: str, book: Optional[Book] = None,
                    today: Optional[date] = None) -> Screen:
    return (
        rtl(_quick_facts(entry, book, today) + "\n\nهمین را ثبت کنم؟ درآمد است یا هزینه؟"),
        [
            [Button("💰 درآمد", data=f"qk:flow:income:{nonce}"), Button("🧾 هزینه", data=f"qk:flow:expense:{nonce}")],
            [Button("↩️ انصراف", data="nav:cancel")],
        ],
    )


def unreadable_line() -> Screen:
    return (
        rtl(
            "❓ مبلغی در این پیام ندیدم.\n\n"
            "برای ثبت سریع بنویس: «دسته مبلغ»\n"
            "مثال‌ها:\n"
            "• فروش 250000\n"
            "• اجاره 1.2م بابت مرداد\n\n"
            "یا دکمهٔ «ثبت تراکنش» را بزن:"
        ),
        main_menu(),
    )


def unclear_line(reason: str, numbers: Sequence[str]) -> Screen:
    """A line with numbers in it that could not be read as one amount.

    Nothing is recorded and nothing is guessed: the person is told which
    numbers were seen and how to write the line so it is unambiguous.
    """
    return rtl("❓ " + unclear_reason(reason, numbers)), main_menu()


# ======================================================= transaction detail
def transaction_list(book: Book, rows, page: int, total: int, per_page: int = 8) -> Screen:

    if not rows:
        return rtl(f"📄 {book.name}\n\nهنوز تراکنشی ثبت نشده."), [
            [Button("➕ ثبت تراکنش", data=f"tx:book:{book.id}")],
            [Button("⬅️ بازگشت", data=f"book:open:{book.id}")],
        ]

    lines = [f"📄 تراکنش‌های {book.name} — {total} مورد", ""]
    buttons: List[List[Button]] = []
    for tx in rows:
        mark = "💰" if tx.flow is Flow.INCOME else "🧾"
        clip = " 🧾" if tx.receipt_file_id else ""
        lines.append(
            f"{mark} {jalali.to_text(tx.occurred_on)} | {tx.category}: "
            f"{fmt(tx.converted_amount, book.base_currency)}{clip}"
        )
        buttons.append([
            Button(f"{tx.category[:16]} — {fmt(tx.converted_amount)}", data=f"td:open:{tx.id}")
        ])

    last = max(0, (total - 1) // per_page)
    if last:
        nav: List[Button] = []
        if page > 0:
            nav.append(Button("◀️ قبلی", data=f"td:page:{book.id}:{page - 1}"))
        # The counter is a label, not a command; pressing it redraws this page
        # instead of sending the person somewhere else.
        nav.append(Button(f"{page + 1}/{last + 1}", data=f"td:page:{book.id}:{page}"))
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


def transaction_detail(book: Book, tx, origin: str = "", activity=None) -> Screen:
    """One transaction, and a way back to wherever it was opened from.

    `origin` is "a" when it came from the all-books daily list and "b" when it
    came from that list filtered to this book; empty means the book's own list.
    It rides along on every button here, so managing a receipt or deleting from
    the daily list lands back on the daily list rather than somewhere else.
    """

    word = "درآمد" if tx.flow is Flow.INCOME else "هزینه"
    # Words, not an emoji per line: nine pictograms made the card harder to
    # scan than the labels they stood in for.
    lines = [
        "جزئیات تراکنش",
        "",
        f"دفتر: {book.name}",
        f"تاریخ: {jalali.to_text(tx.occurred_on)}",
        f"نوع: {word}",
        f"دسته: {tx.category}",
        f"مبلغ: {fmt(tx.converted_amount, book.base_currency)}",
    ]
    if tx.original_currency != book.base_currency:
        lines.append(f"مبلغ اصلی: {fmt(tx.original_amount, tx.original_currency)}"
                     f" (نرخ {tx.conversion_rate})")
    if tx.description:
        lines.append(f"توضیح: {tx.description}")
    if tx.receipt_file_id:
        lines.append("رسید: " + _receipt_line(tx))
    if activity is not None:
        label = "ویرایش‌شده توسط" if activity.kind == "edited" else "ثبت‌شده توسط"
        lines.append(f"{label}: {activity.display_name}")
        lines.append(f"زمان: {jalali.datetime_text(activity.at, book.timezone)}")

    tail = f":{origin}" if origin in ("a", "b") else ""
    buttons: List[List[Button]] = []
    buttons.append([
        Button("ویرایش دسته", data=f"td:ec:{tx.id}{tail}"),
        Button("ویرایش مبلغ", data=f"td:ea:{tx.id}{tail}"),
        Button("ویرایش توضیحات", data=f"td:ed:{tx.id}{tail}"),
        Button("ویرایش تاریخ", data=f"td:eo:{tx.id}{tail}"),
    ])
    if tx.receipt_file_id:
        buttons.append([
            Button("🧾 دیدن رسید", data=f"td:rcpv:{tx.id}{tail}"),
            Button("❌ حذف رسید", data=f"td:rcpd:{tx.id}{tail}"),
        ])
    else:
        buttons.append([Button("🧾 افزودن رسید", data=f"td:rcp:{tx.id}{tail}")])

    buttons.append([Button("🗑 حذف تراکنش", data=f"td:del:{tx.id}{tail}")])
    day = day_token(tx.occurred_on)
    if origin == "a":
        buttons.append([Button("⬅️ بازگشت", data=f"dl:v:{day}:a:0")])
    elif origin == "b":
        buttons.append([Button("⬅️ بازگشت", data=f"dl:v:{day}:{book.id}:0")])
    else:
        buttons.append([Button("⬅️ بازگشت", data=f"td:list:{book.id}")])
    return rtl("\n".join(lines)), buttons


def ask_receipt() -> Screen:
    return rtl("🧾 عکس یا فایل رسید را بفرست.\n\nبرای انصراف /cancel بزن."), [
        [Button("↩️ انصراف", data="nav:cancel")]
    ]


def ask_description(editing=False) -> Screen:
    text = "توضیحات تراکنش را بنویس (حداکثر 500 حرف)؛ مثلاً: «بابت مرداد»."
    if not editing:
        text += "\nاگر رسید، عکس یا فایلی داری، همراه توضیحات بفرست."
    data = "td:clear_description" if editing else "tx:skip"
    return rtl(text), [[Button("حذف توضیحات" if editing else "ثبت بدون توضیحات", data=data)],
                       [Button("↩️ انصراف", data="nav:cancel")]]


def ask_description_with_rate(code: str, rate, base_code: str, converted) -> Screen:
    """The live rate was applied; say so, and offer to change it."""
    name = CURRENCY_NAMES.get(code, code)
    return rtl(
        f"💱 نرخ امروز {name}: {fmt(rate, CURRENCY_NAMES.get(base_code, base_code))}\n"
        f"معادل: {fmt(converted, CURRENCY_NAMES.get(base_code, base_code))}\n\n"
        "توضیحات تراکنش را بنویس (حداکثر 500 حرف)؛ مثلاً: «بابت مرداد».\n"
        "اگر رسید، عکس یا فایلی داری، همراه توضیحات بفرست."
    ), [
        [Button("ثبت بدون توضیحات", data="tx:skip")],
        [Button("✏️ نرخ دیگری دارم", data="tx:rate:x")],
        [Button("↩️ انصراف", data="nav:cancel")],
    ]


# ================================================================== search
def ask_search(problem: Optional[str] = None) -> Screen:
    return rtl(
        _problem(problem) + "🔎 جست‌وجو\n\nبخشی از نام دسته یا توضیح را بنویس؛ مثلاً: اجاره"
    ), [
        [Button("↩️ انصراف", data="nav:cancel")]
    ]


def search_results(book: Book, query: str, rows, total: int, amount, page: int,
                   per_page: int = 10) -> Screen:

    if not total:
        return rtl(f"🔎 «{query}»\n\nچیزی پیدا نشد."), [
            [Button("🔎 جست‌وجوی دیگر", data=f"sr:new:{book.id}")],
            [Button("⬅️ بازگشت", data=f"book:open:{book.id}")],
        ]

    lines = [f"🔎 «{query}» — {total} نتیجه", f"جمع کل: {fmt(amount, book.base_currency)}", ""]
    buttons: List[List[Button]] = []
    for tx in rows:
        mark = "💰" if tx.flow is Flow.INCOME else "🧾"
        note = f" — {tx.description[:24]}" if tx.description else ""
        lines.append(
            f"{mark} {jalali.to_text(tx.occurred_on)} | {tx.category}: "
            f"{fmt(tx.converted_amount)}{note}"
        )
        # A result you cannot open is a dead end: finding a transaction is
        # nearly always the first step of editing or deleting it.
        buttons.append([
            Button(f"{mark} {tx.category[:16]} — {fmt(tx.converted_amount)}", data=f"td:open:{tx.id}")
        ])

    last = max(0, (total - 1) // per_page)
    if last:
        nav: List[Button] = []
        if page > 0:
            nav.append(Button("◀️ قبلی", data=f"sr:page:{page - 1}"))
        nav.append(Button(f"{page + 1}/{last + 1}", data=f"sr:page:{page}"))
        if page < last:
            nav.append(Button("بعدی ▶️", data=f"sr:page:{page + 1}"))
        buttons.append(nav)

    buttons.append([Button("🔎 جست‌وجوی دیگر", data=f"sr:new:{book.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl("\n".join(lines)), buttons


def pick_currency(codes, balances_by_code) -> Screen:
    """Which currency is this transaction in? Only asked when there is a choice."""
    buttons = [
        [Button(CURRENCY_NAMES.get(code, code), data=f"tx:cur:{code}")]
        for code in codes
    ]
    buttons.append([Button("⬅️ انصراف", data="nav:cancel")])
    lines = ["💱 این مبلغ به چه ارزی است؟", ""]
    for code in codes:
        held = balances_by_code.get(code)
        if held is not None:
            lines.append(f"• {fmt_currency(held, code)}")
    return rtl("\n".join(lines)), buttons


def ask_rate(code: str, base_code: str, problem: Optional[str] = None) -> Screen:
    """A foreign amount needs a rate, because the book reports in its own currency."""
    name = CURRENCY_NAMES.get(code, code)
    base = CURRENCY_NAMES.get(base_code, base_code)
    return rtl(
        _problem(problem)
        + f"💱 نرخ هر {name} به {base} چند است؟\n\n"
        f"همین عدد در تراکنش ثبت و قفل می‌شود، تا گزارش این ماه با نرخ فردا عوض نشود."
    ), [[Button("⬅️ انصراف", data="nav:cancel")]]
