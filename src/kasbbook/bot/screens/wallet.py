"""Wallet screens: a book's currencies, balances, and conversions."""

from __future__ import annotations

from ...adapters.base import Button
from ...modules.books.models import Book
from ...modules.exchange.models import CURRENCY_NAMES
from .common import (
    Screen,
    WHOLE_UNIT_CURRENCIES,
    back_row,
    cancel_row,
    fmt,
    fmt_currency,
    home_row,
    rows_of,
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
    buttons.append(back_row(f"book:open:{book.id}"))
    return rtl("\n".join(lines)), buttons


def currency_settings(book: Book, options) -> Screen:
    """Tick the currencies this book is allowed to hold."""
    base_name = CURRENCY_NAMES.get(book.base_currency, book.base_currency)
    lines = [f"⚙️ ارزهای {book.name}", ""]
    marks, ticks = [], []
    for option in options:
        if option.is_base:
            marks.append(f"✅ {option.name} — ارز پایه، همیشه فعال")
            continue
        mark = "✅" if option.enabled else "⬜️"
        marks.append(f"{mark} {option.name}")
        ticks.append(Button(f"{mark} {option.name}", data=f"cu:tog:{option.code}"))

    if not ticks:
        # A title above a lone back button says nothing about what the screen is
        # for. Nothing to tick means this build offers no currency beyond the
        # book's own, so the wallet is one currency deep and that is the answer.
        lines.append(
            "با تیک‌زدن یک ارز، موجودی‌اش جدا نگه داشته می‌شود و هنگام ثبت "
            "تراکنش پیشنهاد می‌شود.\n\n"
            f"الان ارز دیگری در دسترس نیست؛ این دفتر با {base_name} کار می‌کند."
        )
        return rtl("\n".join(lines)), [back_row(f"cu:home:{book.id}")]

    lines += [
        "هر ارزی که تیک بخورد، هنگام ثبت تراکنش پیشنهاد می‌شود و موجودی‌اش "
        "جدا نگه داشته می‌شود.",
        "",
        *marks,
    ]
    # Two to a row: a currency name is one short word, and one per row pushed
    # the way out off the first screenful.
    return rtl("\n".join(lines)), rows_of(ticks) + [back_row(f"cu:home:{book.id}")]


def conversion_pick_source(book: Book, balances) -> Screen:
    """Which currency the money leaves.

    The way out is بازگشت, not انصراف: the draft starts at the next step, so
    there is nothing yet to abandon — only a wallet to go back to.
    """
    rows = list(balances)
    lines = [f"دفتر {book.name} · تبدیل ارز", ""]

    if not rows:
        lines.append(
            "تبدیل، موجودی یک ارز را به ارز دیگری می‌برد؛ مثلاً تتر به تومان.\n\n"
            "الان چیزی برای تبدیل نداری. اول درآمدی به آن ارز ثبت کن."
        )
        return rtl("\n".join(lines)), [back_row(f"cu:home:{book.id}")]

    lines += ["🔄 از کدام ارز تبدیل می‌کنی؟", ""]
    picks = []
    for balance in rows:
        lines.append(f"• {fmt_currency(balance.amount, balance.code)}")
        picks.append(Button(balance.name, data=f"cu:from:{balance.code}"))
    return rtl("\n".join(lines)), rows_of(picks) + [back_row(f"cu:home:{book.id}")]


def conversion_ask_amount(book: Book, code: str, held) -> Screen:
    """How much leaves, with the whole balance one tap away.

    Emptying a currency is the common case — a token is bought to be spent, not
    trimmed — and this screen already prints the figure, so offering it as a
    button saves typing a number that is known to the last digit. No button when
    the balance is gone: a dead offer is worse than none.
    """
    name = CURRENCY_NAMES.get(code, code)
    # Toman is counted whole; a token's fraction is real money, so the example
    # for one shows a decimal rather than teaching a round number.
    example = "250000" if code in WHOLE_UNIT_CURRENCIES else "12.5"
    buttons = []
    if held > 0:
        buttons.append([Button(f"👛 همهٔ موجودی ({fmt_currency(held, code)})",
                               data=f"cu:all:{code}")])
    buttons.append(cancel_row())
    return rtl(
        f"دفتر {book.name} · تبدیل ارز\n\n"
        f"🔄 چقدر {name} تبدیل می‌کنی؟\n\n"
        f"موجودی: {fmt_currency(held, code)}\n"
        f"مثلاً: {example}"
    ), buttons


def conversion_pick_target(book: Book, from_code: str, codes) -> Screen:
    name = CURRENCY_NAMES.get(from_code, from_code)
    lines = [f"دفتر {book.name} · تبدیل ارز", ""]
    others = [code for code in codes if code != from_code]

    if not others:
        # Nothing to convert into: the book's only ticked currency is the one
        # being converted out of. Say where the other side comes from, and
        # offer the screen that puts it there.
        lines.append(
            f"تبدیل، {name} را به ارز دیگری از همین دفتر می‌برد.\n\n"
            "ولی این دفتر ارز دیگری فعال ندارد؛ از «ارزهای دفتر» یکی را تیک "
            "بزن، بعد دوباره بیا."
        )
        return rtl("\n".join(lines)), [
            [Button("⚙️ ارزهای دفتر", data=f"cu:set:{book.id}")],
            cancel_row(),
        ]

    lines.append(f"🔄 {name} به کدام ارز تبدیل شود؟")
    picks = [Button(CURRENCY_NAMES.get(code, code), data=f"cu:to:{code}")
             for code in others]
    return rtl("\n".join(lines)), rows_of(picks) + [cancel_row()]


def conversion_ask_target_amount(
    book: Book, from_code: str, from_amount, to_code: str, suggested=None,
) -> Screen:
    """How much came back, with today's rate offered as a button.

    `ask_description_with_rate` is the precedent: apply the live rate, say so,
    and keep the typed path. Here the typed path is no edge case — an exchange
    takes its cut, and the figure that actually arrived is the one the book has
    to carry — so the rate is an offer, never an assumption. Without a quote
    there is no button and nothing is guessed.
    """
    to_name = CURRENCY_NAMES.get(to_code, to_code)
    example = "250000" if to_code in WHOLE_UNIT_CURRENCIES else "12.5"
    lines = [
        f"دفتر {book.name} · تبدیل ارز",
        "",
        f"🔄 {fmt_currency(from_amount, from_code)} تبدیل می‌شود به چقدر {to_name}؟",
        "",
    ]
    buttons = []
    if suggested is not None:
        lines += [
            f"💱 به نرخ امروز: {fmt_currency(suggested, to_code)}",
            f"اگر عدد دیگری گرفتی، همان را بنویس؛ مثلاً: {example}",
        ]
        buttons.append([Button(f"✅ {fmt_currency(suggested, to_code)} به نرخ امروز",
                               data=f"cu:ok:{to_code}")])
    else:
        lines.append(f"همان عددی را بنویس که واقعاً گرفتی؛ مثلاً: {example}")
    buttons.append(cancel_row())
    return rtl("\n".join(lines)), buttons


def conversion_ask_base_value(book: Book, base_code: str) -> Screen:
    name = CURRENCY_NAMES.get(base_code, base_code)
    example = "250000" if base_code in WHOLE_UNIT_CURRENCIES else "12.5"
    return rtl(
        f"دفتر {book.name} · تبدیل ارز\n\n"
        f"🔄 ارزش این تبدیل به {name} چقدر بود؟\n\n"
        f"چون هیچ سمت این تبدیل {name} نیست، برای ثبت در دفتر به ارزش "
        f"{name} آن نیاز است.\n\n"
        f"مثلاً: {example}"
    ), [cancel_row()]


def conversion_saved(book: Book, conversion) -> Screen:
    return rtl(
        "✅ تبدیل ثبت شد\n\n"
        f"{fmt_currency(conversion.from_amount, conversion.from_currency)}"
        f"  ←  {fmt_currency(conversion.to_amount, conversion.to_currency)}\n"
        f"ارزش دفتری: {fmt(conversion.base_value, conversion.base_currency)}"
    ), [
        [Button("👛 کیف پول", data=f"cu:home:{book.id}")],
        # A saved conversion has no parent to go up to, so this is home, not
        # back — the same move `transaction_saved` makes, through the same row.
        home_row(),
    ]
