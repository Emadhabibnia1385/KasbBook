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
    rtl,
)


def book_list(books: Sequence[Book]) -> Screen:
    if not books:
        return (
            rtl("هنوز دفتری نداری.\n\nبا دکمهٔ زیر اولین دفترت را بساز."),
            [[Button("➕ ساخت دفتر", data="book:new")], [Button("⬅️ بازگشت", data="nav:home")]],
        )

    names = _book_names(books)
    lines = ["دفترهای تو:", ""]
    for book in books:
        kind = BOOK_LABELS.get(book.type, book.type.value).split(" ", 1)[-1]
        lines.append(f"• {names[book.id]} — {kind}")
    buttons = _book_buttons(books, lambda b: f"book:open:{b.id}")
    buttons.append([Button("➕ ساخت دفتر", data="book:new")])
    buttons.append([Button("⬅️ بازگشت", data="nav:home")])
    return rtl("\n".join(lines)), buttons


def book_created(book: Book, first: bool) -> Screen:
    """The first book is a beginning, not a list: say what to do with it."""
    if first:
        return rtl(
            f"✅ دفتر «{book.name}» ساخته شد.\n\n"
            "حالا اولین تراکنش را بنویس؛ مثلاً «فروش 250ک» — یا از دکمهٔ زیر شروع کن."
        ), [
            [Button("📌 ثبت تراکنش", data=f"tx:book:{book.id}")],
            [Button("⬅️ بازگشت", data="nav:home")],
        ]
    return rtl(f"✅ دفتر «{book.name}» ساخته شد."), [
        [Button("📌 ثبت تراکنش", data=f"tx:book:{book.id}")],
        [Button("📚 دفترهای من", data="book:list")],
        [Button("⬅️ بازگشت", data="nav:home")],
    ]


def new_book_type() -> Screen:
    return rtl("چه نوع دفتری می‌خواهی؟"), [
        [Button("👤 مالی شخصی", data="book:type:personal")],
        [Button("💼 کسب‌وکار", data="book:type:business")],
        [Button("👥 تیم", data="book:type:team")],
        [Button("⬅️ بازگشت", data="book:list")],
    ]


def ask_book_name(book_type: BookType, problem: Optional[str] = None) -> Screen:
    label = BOOK_LABELS.get(book_type, "")
    return rtl(
        _problem(problem)
        + "اسم دفتر را بنویس.\n"
        "مثال: مغازه، خرج خانه، تیم طراحی\n\n"
        f"نوع دفتر: {label}"
    ), [
        [Button("↩️ انصراف", data="nav:cancel")]
    ]


# =========================================================== book workspace
def book_menu(book: Book) -> Screen:
    """Everything that belongs to one book, one press away."""
    kind = BOOK_LABELS.get(book.type, "").split(" ", 1)[-1]
    return rtl(f"{_book_mark(book)} {book.name} — {kind}"), [
        [Button("📌 ثبت تراکنش", data=f"tx:book:{book.id}")],
        [Button("🏷 دسته‌ها", data=f"cg:list:{book.id}")],
        [Button("📄 تراکنش‌ها", data=f"td:list:{book.id}"),
         Button("🔎 جست‌وجو", data=f"sr:new:{book.id}")],
        [Button("📊 گزارش", data=f"rep:book:{book.id}")],
        [Button("🎯 بودجه‌ها", data=f"bg:list:{book.id}"),
         Button("🤝 طلب و بدهی", data=f"dt:list:{book.id}")],
        [Button("💳 وام و اقساط", data=f"ln:list:{book.id}"),
         Button("🔁 تراکنش تکرارشونده", data=f"rr:list:{book.id}")],
        [Button("👛 کیف پول و ارزها", data=f"cu:home:{book.id}")],
        # Only where there is more than one person to pay. On a personal book
        # the whole idea is noise, so it is not offered.
        *([[Button("👥 حقوق و سهم", data=f"pr:list:{book.id}")]]
          if book.type in (BookType.TEAM, BookType.ORGANIZATION) else []),
        *([[Button("👤 افزودن هم‌تیمی", data=f"iv:new:{book.id}")]]
          if book.type in (BookType.TEAM, BookType.ORGANIZATION) else []),
        [Button("⬅️ بازگشت", data="book:list")],
    ]


def category_list(book, categories) -> Screen:
    rows = [[Button("➕ افزودن دسته", data=f"cg:new:{book.id}")]]
    for category in categories:
        kind = "درآمد" if category.flow is Flow.INCOME else "هزینه" if category.flow is Flow.EXPENSE else "تعیین‌نشده"
        rows.append([Button(f"{category.name[:18]} · {kind}", data=f"cg:open:{category.id}"),
                     Button("ویرایش", data=f"cg:edit:{category.id}"),
                     Button("حذف", data=f"cg:del:{category.id}")])
    rows.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl(f"🏷 دسته‌های {book.name}\n\n" +
               ("برای ویرایش یا حذف یک دسته، دکمهٔ کنارش را بزن." if categories
                else "هنوز دسته‌ای نداری؛ از دکمهٔ بالا اضافه کن.")), rows


def ask_category_name(current_name=None) -> Screen:
    rows = [[Button("حفظ نام و ویرایش نوع", data="cg:keep")]] if current_name else []
    rows.append([Button("↩️ انصراف", data="nav:cancel")])
    return rtl("نام دسته را بنویس (1 تا 80 حرف)؛ مثلاً: اجاره."), rows


def ask_category_flow() -> Screen:
    return rtl("این دسته برای درآمد است یا هزینه؟"), [
        [Button("درآمد", data="cg:type:income"), Button("هزینه", data="cg:type:expense")],
        [Button("↩️ انصراف", data="nav:cancel")]]


def ask_teammate() -> Screen:
    return rtl("یوزرنیم یا شناسهٔ عددی هم‌تیمی را در همین پیام‌رسان بفرست.\n"
               "باید قبلاً ربات را استارت کرده باشد. دعوت پس از پذیرش او فعال می‌شود."), [
        [Button("↩️ انصراف", data="nav:cancel")]]


def team_invitation(book, invitation) -> Screen:
    return rtl(f"👥 دعوت به تیم «{book.name}»\n\nآیا دعوت را می‌پذیری؟"), [[
        Button("✅ پذیرش", data=f"iv:yes:{invitation.id}"),
        Button("❌ رد", data=f"iv:no:{invitation.id}"),
    ]]


def invitation_inbox(invitations, books) -> Screen:
    rows = [[Button(books[row.book_id].name[:24], data=f"iv:open:{row.id}")] for row in invitations]
    rows.append([Button("⬅️ حساب کاربری", data="acc:panel")])
    return rtl("👥 دعوت‌های تیمی" if invitations else "دعوت فعالی نداری."), rows
