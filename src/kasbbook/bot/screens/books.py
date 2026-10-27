"""Book screens: the list, creating one, its menu, categories, invitations."""

from __future__ import annotations

from typing import Optional, Sequence

from ...adapters.base import Button
from ...modules.books.models import Book, BookType
from ...modules.ledger.models import Flow
from .common import (
    BOOK_LABELS,
    Screen,
    _book_buttons,
    _book_mark,
    _book_names,
    _problem,
    back_row,
    cancel_row,
    rows_of,
    rtl,
)


def book_list(books: Sequence[Book]) -> Screen:
    if not books:
        # One state, one sentence: the entry flow's pick_book and the report
        # menu say exactly this, so arriving from any of the three reads as one
        # answer instead of three guesses at the same question.
        return (
            rtl("هنوز دفتری نداری. اول یک دفتر بساز (مثلاً «مغازه»)، بعد تراکنش‌هایت را در آن ثبت کن."),
            [[Button("➕ ساخت دفتر", data="book:new")], back_row("nav:home")],
        )

    names = _book_names(books)
    lines = ["دفترهای تو:", ""]
    for book in books:
        kind = BOOK_LABELS.get(book.type, book.type.value).split(" ", 1)[-1]
        lines.append(f"• {names[book.id]} — {kind}")
    buttons = _book_buttons(books, lambda b: f"book:open:{b.id}")
    buttons.append([Button("➕ ساخت دفتر", data="book:new")])
    # The book list is a child of the main menu, so here home really is up.
    buttons.append(back_row("nav:home"))
    return rtl("\n".join(lines)), buttons


def book_created(book: Book, first: bool) -> Screen:
    """The first book is a beginning, not a list: say what to do with it.

    Back goes to the list the new book just joined. It used to say «بازگشت» and
    go home, two levels up, while a separate «دفترهای من» button offered the
    level in between — one destination now, reached by the button that means it.
    """
    if first:
        return rtl(
            f"✅ دفتر «{book.name}» ساخته شد.\n\n"
            "حالا اولین تراکنش را بنویس؛ مثلاً «فروش 250ک» — یا از دکمهٔ زیر شروع کن."
        ), [
            [Button("📌 ثبت تراکنش", data=f"tx:book:{book.id}")],
            back_row("book:list"),
        ]
    return rtl(f"✅ دفتر «{book.name}» ساخته شد."), [
        [Button("📌 ثبت تراکنش", data=f"tx:book:{book.id}")],
        back_row("book:list"),
    ]


def new_book_type() -> Screen:
    """The four kinds a book can be, two to a row, under a line saying where this is.

    The labels come from BOOK_LABELS so the choice here and the type shown on
    every later screen cannot drift apart — and so سازمان, which the menu has
    always known how to draw, is offered rather than only reachable by API.
    """
    return rtl(
        "دفترهای من · دفتر جدید\n\n"
        "چه نوع دفتری می‌خواهی؟\n"
        "روی «تیم» و «سازمان» بخش هم‌تیمی و حقوق هم اضافه می‌شود."
    ), [
        *rows_of([
            Button(BOOK_LABELS[BookType.PERSONAL], data="book:type:personal"),
            Button(BOOK_LABELS[BookType.BUSINESS], data="book:type:business"),
            Button(BOOK_LABELS[BookType.TEAM], data="book:type:team"),
            Button(BOOK_LABELS[BookType.ORGANIZATION], data="book:type:organization"),
        ]),
        back_row("book:list"),
    ]


def ask_book_name(book_type: BookType, problem: Optional[str] = None) -> Screen:
    label = BOOK_LABELS.get(book_type, "")
    return rtl(
        _problem(problem)
        + "اسم دفتر را بنویس.\n"
        "مثال: مغازه، خرج خانه، تیم طراحی\n\n"
        f"نوع دفتر: {label}"
    ), [
        cancel_row()
    ]


# =========================================================== book workspace
def book_menu(book: Book) -> Screen:
    """Everything that belongs to one book, one press away.

    Recording is the reason the book exists, so it keeps a row of its own; the
    rest are peers and go two to a row. That is six rows for a business book
    instead of eight, and seven for a team instead of ten — the difference
    between a menu and a scroll.
    """
    kind = BOOK_LABELS.get(book.type, "").split(" ", 1)[-1]
    peers = [
        Button("📄 تراکنش‌ها", data=f"td:list:{book.id}"),
        Button("🔎 جست‌وجو", data=f"sr:new:{book.id}"),
        Button("📊 گزارش", data=f"rep:book:{book.id}"),
        Button("🏷 دسته‌ها", data=f"cg:list:{book.id}"),
        Button("🎯 بودجه‌ها", data=f"bg:list:{book.id}"),
        Button("🤝 طلب و بدهی", data=f"dt:list:{book.id}"),
        Button("💳 وام و اقساط", data=f"ln:list:{book.id}"),
        Button("🔁 تراکنش تکرارشونده", data=f"rr:list:{book.id}"),
        Button("👛 کیف پول و ارزها", data=f"cu:home:{book.id}"),
    ]
    # Only where there is more than one person to pay. On a personal book the
    # whole idea is noise, so it is not offered.
    if book.type in (BookType.TEAM, BookType.ORGANIZATION):
        peers += [
            Button("👥 حقوق و سهم", data=f"pr:list:{book.id}"),
            Button("👤 افزودن هم‌تیمی", data=f"iv:new:{book.id}"),
        ]
    return rtl(f"{_book_mark(book)} {book.name} — {kind}"), [
        [Button("📌 ثبت تراکنش", data=f"tx:book:{book.id}")],
        *rows_of(peers),
        back_row("book:list"),
    ]


def category_list(book, categories) -> Screen:
    """The book's categories, and the two buttons that make one.

    A category's type used to be a third step, asked after the name: «درآمد است
    یا هزینه؟» — a question whose answer is the button the person had already
    pressed to get here. One button per type carries it in the callback, so
    making a category is a tap and a word.
    """
    rows = rows_of([
        Button("➕ افزودن دستهٔ هزینه", data=f"cg:new:{book.id}:expense"),
        Button("➕ افزودن دستهٔ درآمد", data=f"cg:new:{book.id}:income"),
    ])
    for category in categories:
        kind = "درآمد" if category.flow is Flow.INCOME else "هزینه" if category.flow is Flow.EXPENSE else "تعیین‌نشده"
        rows.append([Button(f"{category.name[:18]} · {kind}", data=f"cg:open:{category.id}"),
                     Button("ویرایش", data=f"cg:edit:{category.id}"),
                     Button("حذف", data=f"cg:del:{category.id}")])
    rows.append(back_row(f"book:open:{book.id}"))
    # The heading stays in both branches: an empty list is this screen with
    # nothing in it, not a different screen. And the empty one is the only
    # place left to say what a category is for.
    body = (
        "برای ویرایش یا حذف یک دسته، دکمهٔ کنارش را بزن."
        if categories else
        "دسته همان چیزی است که هر تراکنش را با آن صدا می‌زنی؛ مثلاً اجاره، فروش یا قبض برق. "
        "گزارش‌ها هم بر اساس همین دسته‌ها جمع می‌شوند.\n\n"
        "هنوز دسته‌ای نساخته‌ای؛ با یکی از دکمه‌های بالا بساز."
    )
    return rtl(f"🏷 دسته‌های {book.name}\n\n{body}"), rows


def ask_category_name(current_name=None, book_name: str = "", direction: str = "") -> Screen:
    """Asks for the name under the heading its parent showed.

    A bare «نام دسته را بنویس» drops every fact the person arrived with: which
    book, and whether they pressed income or expense. The breadcrumb carries
    both forward, in the «دفتر مغازه · ...» form the entry flow already uses.
    """
    rows = [[Button("حفظ نام و ویرایش نوع", data="cg:keep")]] if current_name else []
    rows.append(cancel_row())
    kind = {Flow.INCOME.value: "درآمد", Flow.EXPENSE.value: "هزینه"}.get(direction, "")
    crumbs = [part for part in (
        f"دفتر {book_name}" if book_name else "",
        f"ویرایش «{current_name}»" if current_name else (f"دستهٔ {kind}" if kind else "دستهٔ تازه"),
    ) if part]
    return rtl(f"🏷 {' · '.join(crumbs)}\n\n"
               "نام دسته را بنویس (1 تا 80 حرف)؛ مثلاً: اجاره."), rows


def ask_category_flow(book_name: str = "", name: str = "") -> Screen:
    """The type, asked only where it is still unknown: an edit.

    Creating carries the type in the button that started it. Editing does not —
    «حفظ نام و ویرایش نوع» exists precisely to land here — so this screen also
    has to echo the name, or the last step of an edit shows no sign of what is
    being edited.
    """
    crumbs = [part for part in (f"دفتر {book_name}" if book_name else "",
                                f"«{name}»" if name else "") if part]
    head = f"🏷 {' · '.join(crumbs)}\n\n" if crumbs else ""
    return rtl(f"{head}این دسته برای درآمد است یا هزینه؟"), [
        [Button("درآمد", data="cg:type:income"), Button("هزینه", data="cg:type:expense")],
        cancel_row()]


def ask_teammate() -> Screen:
    # The last typed prompt in the bot without an example. Both forms are shown
    # because a username and a numeric id look nothing alike, and someone who
    # has only ever seen one of them cannot tell which this wants.
    return rtl("یوزرنیم یا شناسهٔ عددی هم‌تیمی را در همین پیام‌رسان بفرست؛\n"
               "مثلاً @hamkar یا 123456789.\n"
               "باید قبلاً ربات را استارت کرده باشد. دعوت پس از پذیرش او فعال می‌شود."), [
        cancel_row()]


def team_invitation(book, invitation) -> Screen:
    return rtl(f"👥 دعوت به تیم «{book.name}»\n\nآیا دعوت را می‌پذیری؟"), [[
        Button("✅ پذیرش", data=f"iv:yes:{invitation.id}"),
        Button("❌ رد", data=f"iv:no:{invitation.id}"),
    ]]


def invitation_queued(display_name: str, book_id) -> Screen:
    """Said once an invitation is on its way.

    Built here rather than in the feature: a screen assembled out of rtl() and
    Button() inside features/ is invisible to the sweeps that check every
    callback's size and every Persian line's direction.
    """
    return rtl(f"✅ دعوت برای «{display_name}» ثبت شد و برای ارسال در صف قرار گرفت.\n\n"
               "تا او دعوت را بپذیرد، چیزی در دفتر عوض نمی‌شود."), [
        back_row(f"book:open:{book_id}"),
    ]


def invitation_declined() -> Screen:
    """The answer to «❌ رد». A declined invitation is final in the service."""
    return rtl("دعوت رد شد؛ به این دفتر اضافه نشدی.\n\n"
               "اگر نظرت عوض شد، باید دوباره دعوتت کنند."), [back_row("acc:panel")]


def invitation_inbox(invitations, books) -> Screen:
    """Invitations waiting for an answer — and, when there are none, the same
    screen saying so, rather than one bare line with no heading above it."""
    rows = [[Button(books[row.book_id].name[:24], data=f"iv:open:{row.id}")] for row in invitations]
    rows.append(back_row("acc:panel"))
    body = (
        "روی هر دعوت بزن تا دفترش را ببینی و بپذیری یا رد کنی."
        if invitations else
        "وقتی کسی تو را به دفتر تیمی‌اش دعوت کند، دعوتش همین‌جا می‌آید و با یک دکمه می‌پذیری.\n\n"
        "الان دعوت فعالی نداری."
    )
    return rtl(f"👥 دعوت‌های تیمی\n\n{body}"), rows
