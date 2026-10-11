"""Wallet screens: a book's currencies, balances, and conversions."""

from __future__ import annotations

from ...adapters.base import Button
from ...modules.books.models import Book
from ...modules.exchange.models import CURRENCY_NAMES
from .common import (
    Screen,
    fmt,
    fmt_currency,
    rtl,
)


# ------------------------------------------------------- wallet & currencies
def currency_home(book: Book, balances, has_extra: bool, total=None) -> Screen:
    """What the book holds, in the currencies it holds it in."""
    lines = [f"👛 کیف پول {book.name}", ""]
    if not has_extra:
        lines += [
            "این دفتر فقط با "
            f"{CURRENCY_NAMES.get(book.base_currency, book.base_currency)} کار می‌کند.",
            "",
            "اگر تتر، تون یا ترون هم می‌گیری، از «ارزهای دفتر» فعالش کن تا هنگام "
            "ثبت تراکنش ازت بپرسد و موجودی هر کدام جدا نگه داشته شود.",
        ]
    else:
        base_name = CURRENCY_NAMES.get(book.base_currency, book.base_currency)
        for balance in balances:
            line = f"• {fmt_currency(balance.amount, balance.code)}"
            worth = getattr(balance, "value", None)
            if worth is not None and not balance.is_base:
                line += f"  ≈ {fmt(worth, base_name)}"
            lines.append(line)
        if total is not None:
            lines += ["", f"ارزش کل به نرخ امروز: {fmt(total, base_name)}"]
        lines += ["", "هر ارز همان ارز می‌ماند تا وقتی تبدیلش کنی."]

    buttons = [[Button("⚙️ ارزهای دفتر", data=f"cu:set:{book.id}")]]
    if has_extra:
        buttons.append([Button("🔄 تبدیل ارز", data=f"cu:conv:{book.id}")])
    buttons.append([Button("⬅️ بازگشت", data=f"book:open:{book.id}")])
    return rtl("\n".join(lines)), buttons


def currency_settings(book: Book, options) -> Screen:
    """Tick the currencies this book is allowed to hold."""
    lines = [
        f"⚙️ ارزهای {book.name}",
        "",
        "هر ارزی که تیک بخورد، هنگام ثبت تراکنش پیشنهاد می‌شود و موجودی‌اش "
        "جدا نگه داشته می‌شود.",
        "",
    ]
    buttons = []
    for option in options:
        if option.is_base:
            lines.append(f"✅ {option.name} — ارز پایه، همیشه فعال")
            continue
        mark = "✅" if option.enabled else "⬜️"
        lines.append(f"{mark} {option.name}")
        buttons.append([Button(f"{mark} {option.name}", data=f"cu:tog:{option.code}")])

    buttons.append([Button("⬅️ کیف پول", data=f"cu:home:{book.id}")])
    return rtl("\n".join(lines)), buttons


def conversion_pick_source(book: Book, balances) -> Screen:
    lines = ["🔄 از کدام ارز تبدیل می‌کنی؟", ""]
    buttons = []
    for balance in balances:
        lines.append(f"• {fmt_currency(balance.amount, balance.code)}")
        buttons.append([Button(balance.name, data=f"cu:from:{balance.code}")])
    buttons.append([Button("⬅️ انصراف", data=f"cu:home:{book.id}")])
    return rtl("\n".join(lines)), buttons


def conversion_ask_amount(code: str, held) -> Screen:
    name = CURRENCY_NAMES.get(code, code)
    return rtl(
        f"🔄 چقدر {name} تبدیل می‌کنی؟\n\n"
        f"موجودی: {fmt_currency(held, code)}"
    ), [[Button("⬅️ انصراف", data="nav:cancel")]]


def conversion_pick_target(from_code: str, codes) -> Screen:
    name = CURRENCY_NAMES.get(from_code, from_code)
    buttons = [
        [Button(CURRENCY_NAMES.get(code, code), data=f"cu:to:{code}")]
        for code in codes if code != from_code
    ]
    buttons.append([Button("⬅️ انصراف", data="nav:cancel")])
    return rtl(f"🔄 {name} به کدام ارز تبدیل شود؟"), buttons


def conversion_ask_target_amount(from_code: str, from_amount, to_code: str) -> Screen:
    return rtl(
        f"🔄 {fmt_currency(from_amount, from_code)} تبدیل می‌شود به چقدر "
        f"{CURRENCY_NAMES.get(to_code, to_code)}؟\n\n"
        "همان عددی را بنویس که واقعاً گرفتی."
    ), [[Button("⬅️ انصراف", data="nav:cancel")]]


def conversion_ask_base_value(base_code: str) -> Screen:
    name = CURRENCY_NAMES.get(base_code, base_code)
    return rtl(
        f"🔄 ارزش این تبدیل به {name} چقدر بود؟\n\n"
        f"چون هیچ سمت این تبدیل {name} نیست، برای ثبت در دفتر به ارزش "
        f"{name} آن نیاز است."
    ), [[Button("⬅️ انصراف", data="nav:cancel")]]


def conversion_saved(book: Book, conversion) -> Screen:
    return rtl(
        "✅ تبدیل ثبت شد\n\n"
        f"{fmt_currency(conversion.from_amount, conversion.from_currency)}"
        f"  ←  {fmt_currency(conversion.to_amount, conversion.to_currency)}\n"
        f"ارزش دفتری: {fmt(conversion.base_value, conversion.base_currency)}"
    ), [
        [Button("👛 کیف پول", data=f"cu:home:{book.id}")],
        [Button("🏠 خانه", data="nav:home")],
    ]
