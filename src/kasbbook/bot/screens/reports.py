"""Report screens: choosing a book and a period, the summary, the breakdown."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence

from ...adapters.base import Button
from ...modules.books.models import Book
from ...shared import jalali
from .common import (
    Screen,
    _book_buttons,
    fmt,
    rtl,
)


# ------------------------------------------------------------------ reports
def report_menu(books: Sequence[Book]) -> Screen:
    if not books:
        return rtl("هنوز دفتری نداری."), [[Button("⬅️ بازگشت", data="nav:home")]]

    buttons = _book_buttons(books, lambda b: f"rep:book:{b.id}")
    buttons.append([Button("⬅️ بازگشت", data="nav:home")])
    return rtl("گزارش کدام دفتر؟"), buttons


# ------------------------------------------------------------ jalali reports
def period_menu(book: Book, years: Sequence[int], today: Optional[date] = None) -> Screen:
    """Which stretch of time to look at. `today` is the person's day, not the server's."""
    rows: List[List[Button]] = [
        [
            Button("این هفته", data=f"rp:{book.id}:w:0"),
            Button("هفتهٔ گذشته", data=f"rp:{book.id}:w:1"),
        ]
    ]


    this_year, this_month, _ = jalali.to_parts(today or date.today())
    last_year, last_month = (this_year, this_month - 1) if this_month > 1 else (this_year - 1, 12)
    rows.append([
        Button(f"{jalali.month_name(this_month)} {this_year}",
               data=f"rp:{book.id}:m:{this_year}:{this_month:02d}"),
        Button(f"{jalali.month_name(last_month)} {last_year}",
               data=f"rp:{book.id}:m:{last_year}:{last_month:02d}"),
    ])

    buffer: List[Button] = []
    for year in years[:6]:
        buffer.append(Button(f"سال {year}", data=f"rp:{book.id}:y:{year}"))
        if len(buffer) == 2:
            rows.append(buffer)
            buffer = []
    if buffer:
        rows.append(buffer)

    rows.append([Button("⬅️ بازگشت", data="rep:menu")])
    return rtl(f"📊 {book.name}\n\nگزارش کدام بازه را ببینم؟"), rows


def period_report(
    book: Book, period_label: str, summary, spec: str, comparison: Optional[str] = None
) -> Screen:
    body = (
        f"📊 {book.name} — {period_label}\n\n"
        f"💰 درآمد: {fmt(summary.income, book.base_currency)}\n"
        f"🧾 هزینه: {fmt(summary.expense, book.base_currency)}\n"
        f"➖ خالص: {fmt(summary.net, book.base_currency)}"
    )
    if not summary.count:
        # Three zeros read as a broken report; the sentence says it is a quiet one.
        body += "\n\nدر این بازه تراکنشی ثبت نشده. بازهٔ دیگری را امتحان کن."
    if comparison:
        body += f"\n\n{comparison}"

    return rtl(body), [
        [Button("🏷 تفکیک دسته‌ها", data=f"rb:{book.id}:{spec}")],
        [Button("📥 خروجی CSV", data=f"rc:{book.id}:{spec}")],
        [Button("⬅️ بازگشت", data=f"rep:book:{book.id}")],
    ]


def category_breakdown(book: Book, period_label: str, buckets, spec: str) -> Screen:
    from ...modules.ledger.models import Flow

    lines = [f"🏷 تفکیک — {period_label}"]
    for flow, title in ((Flow.INCOME, "💰 درآمد"), (Flow.EXPENSE, "🧾 هزینه")):
        rows = buckets.get(flow, [])
        lines += ["", title]
        if not rows:
            lines.append("تراکنشی نیست.")
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
