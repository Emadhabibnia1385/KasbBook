"""Bank account screens: a book's accounts, and choosing one for a transaction."""

from __future__ import annotations

from typing import List, Sequence

from ...adapters.base import Button
from ...modules.books.models import Book
from .common import Screen, back_row, fmt, rows_of, rtl


def bank_code(bank) -> str:
    """The first eight hex digits of an account's id: what fits in a button next to a book or
    a transaction id inside the callback-data limit. Matched against the book's own accounts, so
    it cannot name a stranger's."""
    return bank.id.hex[:8]


def bank_home(book: Book, rows: Sequence) -> Screen:
    """The book's accounts, each with this book's own share, and a way to change the default."""
    lines = [f"🏦 حساب‌های بانکی {book.name}", ""]
    def line(row) -> str:
        marks = []
        if row.link.is_default:
            marks.append("⭐ پیش‌فرض")
        if not (row.link.is_active and row.bank.is_active):
            marks.append("غیرفعال")
        card = f" {row.bank.card_number[-4:]}" if row.bank.card_number else ""
        share = f" — {fmt(row.balance, row.bank.currency)}" if row.balance is not None else ""
        tail = f" ({'، '.join(marks)})" if marks else ""
        return f"• {row.bank.title}{card}{share}{tail}"

    if not rows:
        lines += [
            "هنوز حسابی به این دفتر وصل نیست.",
            "",
            "حساب را از پنل وب اضافه کن؛ بعد هنگام ثبت تراکنش می‌گویی پول از کدام حساب "
            "آمده یا به کدام رفته.",
        ]
        return rtl("\n".join(lines)), [back_row(f"book:open:{book.id}")]
    lines += [line(row) for row in rows]
    lines += ["", "عددها سهم همین دفتر است؛ حسابی که در دفترهای دیگر هم هست، فقط سهم این دفتر را نشان می‌دهد.",
              "برای پیش‌فرض‌کردن یک حساب، دکمهٔ ⭐ آن را بزن."]
    buttons: List[Button] = []
    for row in rows:
        active = row.link.is_active and row.bank.is_active
        if active and not row.link.is_default:
            buttons.append(Button(f"⭐ {row.bank.title}", data=f"ba:df:{book.id}:{bank_code(row.bank)}"))
    return rtl("\n".join(lines)), [*rows_of(buttons), back_row(f"book:open:{book.id}")]


def pick_for_transaction(book: Book, tx, rows: Sequence, tail: str = "") -> Screen:
    """The accounts a transaction can be moved to, and «بدون حساب»."""
    here = tx.bank_account_id
    lines = [f"🏦 این تراکنش از کدام حساب باشد؟", ""]
    buttons: List[Button] = []
    for row in rows:
        if not (row.link.is_active and row.bank.is_active) and row.bank.id != here:
            continue
        mark = "✅ " if row.bank.id == here else ""
        buttons.append(Button(f"{mark}{row.bank.title}", data=f"ba:st:{tx.id}:{bank_code(row.bank)}{tail}"))
    buttons.append(Button(("✅ " if here is None else "") + "بدون حساب", data=f"ba:st:{tx.id}:-{tail}"))
    return rtl("\n".join(lines)), [*rows_of(buttons), back_row(f"td:open:{tx.id}{tail}")]


def bank_changed(tx, title: str, tail: str = "") -> Screen:
    said = f"✅ حساب این تراکنش شد: {title}" if title else "✅ حساب این تراکنش برداشته شد"
    return rtl(said), [[Button("⬅️ به تراکنش", data=f"td:open:{tx.id}{tail}")]]
