"""Planning screens: budgets, debts, loans, recurring rules, reminders.

`cancel_data` is keyword-only everywhere it appears. These prompts used to take
the text the person had typed as their first argument, so a caller left
positional against the new order would bind someone's typed line to a button's
callback data — thirty characters of Persian is past the sixty-four bytes a
callback gets, and `Button` would raise rather than draw the screen. Keyword-only
makes that a TypeError at the call site instead of a surprise in production.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from ...adapters.base import Button
from ...modules.books.models import Book
from ...modules.ledger.models import Flow
from ...shared import jalali
from .common import (
    Screen,
    _problem,
    back_row,
    cancel_row,
    fmt,
    rows_of,
    rtl,
)


# ------------------------------------------------------------------ budgets
def _bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, round(percent * width / 100)))
    return "█" * filled + "░" * (width - filled)


def budget_list(book: Book, statuses, month_label: str) -> Screen:
    if not statuses:
        text = rtl(
            f"🎯 بودجه‌های {book.name}\n\n"
            "هنوز بودجه‌ای نساخته‌ای.\n"
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

    rows = [[Button("➕ ساخت بودجه", data=f"bg:add:{book.id}")]]
    for status in statuses:
        # The name rides on the delete button itself: a separate label button
        # had nothing to do and sent the person home when pressed.
        rows.append([Button(f"🗑 حذف بودجهٔ {status.label[:22]}", data=f"bg:del:{status.budget.id}")])
    rows.append(back_row(f"book:open:{book.id}"))
    return text, rows


def budget_pick_kind(book: Book, categories: Sequence[str] = ()) -> Screen:
    """What the budget is for — answered with the book's own category names.

    The target used to be typed on a screen of its own and stored unchecked,
    while `BudgetService.status` matches it against a transaction's category by
    exact equality: one typo, one half-space in a different place, and the
    budget read 0% for ever with nothing on screen saying why. A name that is
    offered cannot be mistyped, so the categories the book already uses and the
    two whole-book caps are one screen — a step fewer and that failure mode
    gone with it. The buttons carry the index of the name the feature stashed,
    the way the recording flow's do: a Persian name does not fit in the
    sixty-four bytes a callback gets.
    """
    text = rtl(
        "بودجه برای چه چیزی؟\n\n"
        "یک دسته را از زیر بزن، یا برای کل دفتر سقف بگذار."
    )
    buttons = rows_of([
        Button(f"🏷 {name[:18]}", data=f"bg:cat:{index}")
        for index, name in enumerate(categories[:8])
    ])
    buttons.append([
        Button("🧾 کل هزینه‌ها", data="bg:kind:expense"),
        Button("💰 کل درآمدها", data="bg:kind:income"),
    ])
    # Free text stays for the one case the buttons cannot cover: a category the
    # book has not used yet is on no list, and a cap is exactly the thing one
    # wants before the first spend rather than after it.
    buttons.append([Button("✍️ دستهٔ دیگر", data="bg:kind:category")])
    buttons.append(cancel_row(f"bg:list:{book.id}"))
    return text, buttons


def budget_ask_target(*, cancel_data: str = "nav:cancel",
                      problem: Optional[str] = None) -> Screen:
    """Reached only through «دستهٔ دیگر»; the feature matches what is typed
    against the book's own names before it is stored."""
    return rtl(
        _problem(problem)
        + "نام دسته را همان‌طور که در تراکنش‌ها ثبت کرده‌ای بنویس.\nمثال: اجاره"
    ), [cancel_row(cancel_data)]


def budget_ask_amount(label: str, problem: Optional[str] = None, *,
                      cancel_data: str = "nav:cancel") -> Screen:
    return rtl(
        _problem(problem)
        + f"سقف ماهانهٔ «{label}» چقدر باشد؟\nمثال: 500ک یا 2 میلیون"
    ), [cancel_row(cancel_data)]


# ------------------------------------------------------------------- debts
def debt_list(book: Book, debts, totals, rows_shown: int = 10) -> Screen:
    """The list and its buttons show the same rows, and say when there are more.

    The text looped over every row while the buttons stopped at ten, so a
    person with fifteen debts read fifteen and could settle ten, with nothing
    on screen admitting which five had gone out of reach. Both ends are cut to
    `rows_shown` now and the count that is left over is printed on a line of
    its own. The three totals are the service's own and still count every
    debt, which is why they can exceed what the rows below add up to.
    """
    shown = list(debts)[:rows_shown]
    lines = [
        f"🤝 طلب و بدهی — {book.name}",
        "",
        f"📥 طلب من: {fmt(totals.owed_to_me, book.base_currency)}",
        f"📤 بدهی من: {fmt(totals.i_owe, book.base_currency)}",
        f"⚖️ خالص: {fmt(totals.net, book.base_currency)}",
    ]

    if not debts:
        lines += ["", "مورد بازی نیست.", "نسیه‌ها و قرض‌ها اینجا می‌مانند و روی درآمد اثر نمی‌گذارند."]
    else:
        lines.append("")
        for debt in shown:
            arrow = "📥" if debt.direction.value == "owed_to_me" else "📤"
            line = f"{arrow} {debt.person}: {fmt(debt.amount, book.base_currency)}"
            if debt.due_on:
                line += f"\n  سررسید: {jalali.to_text(debt.due_on)}"
            if debt.note:
                # Set from the web or the API; the bot has no step for it, and
                # hiding it here would hide what someone did write.
                line += f"\n  {debt.note[:40]}"
            lines.append(line)
        if len(debts) > len(shown):
            lines += ["", f"و {len(debts) - len(shown)} مورد دیگر"]

    # The direction rides on the entry button, so the screen that asked for it
    # is no longer in the path: two taps became one.
    rows = rows_of([
        Button("➕ ثبت طلب من", data=f"dt:add:{book.id}:owed_to_me"),
        Button("➕ ثبت بدهی من", data=f"dt:add:{book.id}:i_owe"),
    ])
    for debt in shown:
        rows.append([
            Button(f"✅ تسویه {debt.person[:14]}", data=f"dt:settle:{debt.id}"),
            Button("🗑 حذف", data=f"dt:del:{debt.id}"),
        ])
    rows.append(back_row(f"book:open:{book.id}"))
    return rtl("\n".join(lines)), rows


def debt_ask_person(*, cancel_data: str = "nav:cancel", what: str = "") -> Screen:
    """`what` names the direction the entry button just answered, so the tap is
    visible on the next screen instead of being taken on trust."""
    return rtl(
        (f"{what}\n\n" if what else "")
        + "نام طرف حساب را بنویس.\nمثال: آقای رضایی"
    ), [cancel_row(cancel_data)]


def debt_pick_direction(person: str, problem: Optional[str] = None, *,
                        cancel_data: str = "nav:cancel") -> Screen:
    """Still here for a draft that began before the list split its entry button
    in two. The two answers are peers, so they share a row."""
    return rtl(_problem(problem) + f"{person}\n\nکدام است؟"), [
        *rows_of([
            Button("📥 طلب من", data="dt:dir:owed_to_me"),
            Button("📤 بدهی من", data="dt:dir:i_owe"),
        ]),
        cancel_row(cancel_data),
    ]


def debt_ask_amount(problem: Optional[str] = None, *,
                    cancel_data: str = "nav:cancel", person: str = "") -> Screen:
    return rtl(
        _problem(problem)
        + (f"{person}\n\n" if person else "")
        + "مبلغ را بنویس؛ مثلاً 2000000 یا 2م"
    ), [cancel_row(cancel_data)]


def debt_ask_due(*, cancel_data: str = "nav:cancel",
                 problem: Optional[str] = None) -> Screen:
    """The due dates a credit sale actually has, as buttons.

    Typing was the only way to answer, so the two commonest answers — a week, a
    month — cost a date written by hand. The offset rides in the callback and
    the feature counts it from the person's own today, not the server's.
    """
    return rtl(
        _problem(problem)
        + "سررسید کِی است؟\n\n"
        "یکی از دکمه‌ها را بزن — «بدون سررسید» هم هست — یا تاریخ بنویس؛ مثلاً 1405/08/15."
    ), [
        *rows_of([
            Button("7 روز بعد", data="dt:due:7"),
            Button("30 روز بعد", data="dt:due:30"),
        ]),
        [Button("بدون سررسید", data="dt:nodue")],
        cancel_row(cancel_data),
    ]


# ------------------------------------------------------------------- loans
def loan_list(book: Book, rows_with_progress, rows_shown: int = 10) -> Screen:
    if not rows_with_progress:
        text = rtl(
            f"📄 وام‌های {book.name}\n\n"
            "هنوز وامی ثبت نشده.\n"
            "وام را یک بار تعریف کن تا ربات بگوید چند قسط مانده."
        )
        buttons = [
            [Button("➕ افزودن وام", data=f"ln:add:{book.id}")],
            back_row(f"book:open:{book.id}"),
        ]
        return text, buttons

    # See debt_list: the printed rows and the buttons are the same rows.
    shown = list(rows_with_progress)[:rows_shown]
    lines = [f"📄 وام‌های {book.name}", ""]
    remaining_total = Decimal("0")
    for progress in rows_with_progress:
        # Every loan counts towards the total, listed or not.
        remaining_total += progress.remaining_amount
    for progress in shown:
        lines.append(
            f"• {progress.loan.title}\n"
            f"  {progress.paid_count} از {progress.total_count} پرداخت شده ({progress.percent}%)\n"
            f"  باقی‌مانده: {fmt(progress.remaining_amount, book.base_currency)}"
        )
    if len(rows_with_progress) > len(shown):
        lines += ["", f"و {len(rows_with_progress) - len(shown)} وام دیگر"]
    lines += ["", f"مجموع باقی‌مانده: {fmt(remaining_total, book.base_currency)}"]

    buttons = [[Button("➕ افزودن وام", data=f"ln:add:{book.id}")]]
    for progress in shown:
        buttons.append([
            Button(
                f"{progress.loan.title[:16]} — {progress.remaining_count} قسط",
                data=f"ln:open:{progress.loan.id}",
            )
        ])
    buttons.append(back_row(f"book:open:{book.id}"))
    return rtl("\n".join(lines)), buttons


def loan_detail(book: Book, progress) -> Screen:

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

    # Three buttons, and no two of them are peers: recording a payment is the
    # one thing this screen is for, deleting the loan stands alone so it is
    # never the neighbour of a mis-tap, and leaving is its own row.
    buttons = []
    if progress.remaining_count:
        buttons.append([Button("✅ ثبت پرداخت قسط",
                               data=f"ln:pay:{loan.id}:{progress.paid_count}")])
    buttons.append([Button("🗑 حذف وام", data=f"ln:del:{loan.id}")])
    buttons.append(back_row(f"ln:list:{book.id}"))
    return rtl("\n".join(lines)), buttons


def loan_ask_title(problem: Optional[str] = None, *,
                   cancel_data: str = "nav:cancel") -> Screen:
    return rtl(_problem(problem) + "نام وام چیست؟\n\nمثال: وام مسکن"), [
        cancel_row(cancel_data)
    ]


def loan_ask_amount(title: str, problem: Optional[str] = None, *,
                    cancel_data: str = "nav:cancel") -> Screen:
    return rtl(
        _problem(problem) + f"{title}\n\nمبلغ هر قسط چقدر است؟ مثال: 5م یا 5000000"
    ), [cancel_row(cancel_data)]


def loan_ask_count(title: str = "", problem: Optional[str] = None, *,
                   cancel_data: str = "nav:cancel") -> Screen:
    """The counts a loan actually has, as buttons — and it names the loan.

    This was the only prompt in the flow that did not say which loan was being
    described, and the only answer in the bot where buttons cover nearly every
    real case. A pressed count starts the loan today, which is what
    `loan_detail` then prints straight back; a typed count means some other
    first instalment date, so that path asks for one.
    """
    return rtl(
        _problem(problem)
        + (f"{title}\n\n" if title else "")
        + "تعداد کل اقساط چند تاست؟\n\n"
        "دکمه‌ها وام را از امروز شروع می‌کنند. اگر اولین قسط تاریخ دیگری دارد، "
        "تعداد را بنویس؛ مثال: 24"
    ), [
        *rows_of([
            Button("12 قسط", data="ln:count:12"),
            Button("18 قسط", data="ln:count:18"),
            Button("24 قسط", data="ln:count:24"),
            Button("36 قسط", data="ln:count:36"),
            Button("48 قسط", data="ln:count:48"),
            Button("60 قسط", data="ln:count:60"),
        ], 3),
        cancel_row(cancel_data),
    ]


def loan_ask_start(*, cancel_data: str = "nav:cancel",
                   problem: Optional[str] = None) -> Screen:
    return rtl(
        _problem(problem)
        + "تاریخ اولین قسط؟\n\nمثال: 1405/08/01 یا «فردا»؛ یا دکمهٔ «امروز» را بزن."
    ), [
        [Button("✅ امروز", data="ln:today")],
        cancel_row(cancel_data),
    ]


def debt_confirm_settle(book: Book, debt) -> Screen:
    """Settling asks whether the money itself should be recorded (owner decision D-2).

    "Only close it" comes first and is the safe answer: if the sale on credit or
    the purchase was recorded when it happened, recording the payment too
    counts the same money twice.

    It opens with ⚠️, the mark every other confirmation in the package opens
    with. It used to open with ✅ — the done mark — on a settlement the person
    had not agreed to yet. The two answers keep a row each, the shape
    `confirm_delete` has: they are not peers, and what separates them is a
    transaction.
    """
    received = debt.direction.value == "owed_to_me"
    as_what = "درآمد" if received else "هزینه"
    return rtl(
        f"⚠️ تسویهٔ «{debt.person}» — {fmt(debt.amount, book.base_currency)}\n\n"
        f"اگر فروش یا خرید اصلی را قبلاً ثبت کرده‌ای، فقط ببند تا دوبار شمرده نشود. "
        f"اگر نه، این مبلغ به‌عنوان {as_what} هم ثبت شود."
    ), [
        *rows_of([
            Button("فقط ببند", data=f"dt:settleonly:{debt.id}"),
            Button(f"ببند و {as_what} ثبت کن", data=f"dt:settletx:{debt.id}"),
        ], 1),
        cancel_row(f"dt:list:{book.id}"),
    ]


# =============================================================== recurring
# Not PERIOD_LABELS: payroll defines that name further down for its period
# statuses, and the later definition silently replaced this one, so every
# recurring rule was listed with an empty frequency.
RECURRING_PERIOD_LABELS = {"daily": "روزانه", "weekly": "هفتگی", "monthly": "ماهانه"}


def recurring_list(book: Book, rules, rows_shown: int = 10) -> Screen:

    # See debt_list: the printed rows and the buttons are the same rows.
    shown = list(rules)[:rows_shown]
    if not rules:
        text = rtl(
            f"🔁 تراکنش‌های تکرارشونده — {book.name}\n\n"
            "هنوز چیزی تعریف نشده.\n"
            "اجاره یا حقوق را یک بار تعریف کن تا خودکار ثبت شوند."
        )
    else:
        lines = [f"🔁 تراکنش‌های تکرارشونده — {book.name}", ""]
        for rule in shown:
            state = "فعال ✅" if rule.is_active else "متوقف ⏸"
            word = "درآمد" if rule.flow is Flow.INCOME else "هزینه"
            lines.append(
                f"• {rule.category} — {fmt(rule.amount, book.base_currency)}\n"
                f"  {word} | {RECURRING_PERIOD_LABELS.get(rule.period.value, '')} | {state}\n"
                f"  بعدی: {jalali.to_text(rule.next_run_on)}"
            )
        if len(rules) > len(shown):
            lines += ["", f"و {len(rules) - len(shown)} مورد دیگر"]
        text = rtl("\n".join(lines))

    buttons = [[Button("➕ افزودن تراکنش تکرارشونده", data=f"rr:add:{book.id}")]]
    for rule in shown:
        toggle = f"⏸ توقف {rule.category[:12]}" if rule.is_active else f"▶️ ادامهٔ {rule.category[:12]}"
        buttons.append([
            Button(toggle, data=f"rr:tog:{rule.id}"),
            Button("🗑 حذف", data=f"rr:del:{rule.id}"),
        ])
    buttons.append(back_row(f"book:open:{book.id}"))
    return text, buttons


def recurring_pick_flow(*, cancel_data: str = "nav:cancel") -> Screen:
    """Asked only of a category the book has never seen.

    A `Category` row carries its own flow, so a category picked off the list
    answers this question in the same tap; nothing is left to ask.
    """
    return rtl("این تراکنش تکرارشونده درآمد است یا هزینه؟"), [
        *rows_of([
            Button("💰 درآمد", data="rr:flow:income"),
            Button("🧾 هزینه", data="rr:flow:expense"),
        ]),
        cancel_row(cancel_data),
    ]


def recurring_ask_category(problem: Optional[str] = None,
                           categories: Sequence[Tuple[str, str]] = (), *,
                           cancel_data: str = "nav:cancel") -> Screen:
    """One tap for two questions: which category, and income or expense.

    A `Category` row carries its own flow, so offering the book's own
    categories answers «درآمد است یا هزینه؟» at the same time — the screen
    that used to ask it first is off the path. Offered by index, like the
    recording flow's: a Persian name does not fit in sixty-four callback bytes.
    """
    text = rtl(
        _problem(problem)
        + "دسته چیست؟\n\n"
        "یکی از دسته‌های دفتر را بزن، یا نامش را بنویس.\n"
        "مثال: اجاره، حقوق، اشتراک"
    )

    offered: List[Button] = []
    for index, (name, flow) in enumerate(categories[:6]):
        mark = "💰" if flow == Flow.INCOME.value else "🧾"
        offered.append(Button(f"{mark} {name[:16]}", data=f"rr:cat:{index}"))
    buttons = rows_of(offered)
    buttons.append(cancel_row(cancel_data))
    return text, buttons


def recurring_ask_amount(category: str, problem: Optional[str] = None, *,
                         cancel_data: str = "nav:cancel") -> Screen:
    return rtl(
        _problem(problem) + f"{category}\n\nمبلغ چقدر است؟ مثال: 5000000 یا 5م"
    ), [cancel_row(cancel_data)]


def recurring_pick_period(problem: Optional[str] = None, *,
                          cancel_data: str = "nav:cancel") -> Screen:
    """Monthly is the answer nearly every rule has, so it keeps its own row and
    the two rarer ones share the next."""
    return rtl(_problem(problem) + "هر چند وقت تکرار شود؟"), [
        [Button("ماهانه", data="rr:period:monthly")],
        *rows_of([
            Button("هفتگی", data="rr:period:weekly"),
            Button("روزانه", data="rr:period:daily"),
        ]),
        cancel_row(cancel_data),
    ]


def recurring_ask_start(*, cancel_data: str = "nav:cancel",
                        problem: Optional[str] = None, period: str = "") -> Screen:
    """The last screen of the flow, with both remaining answers already filled in.

    Monthly is what these rules are — the screen's own examples, rent, wages
    and a subscription, are all monthly — and a rule someone is defining starts
    today. So the period is defaulted instead of asked on a screen of its own,
    and the start is one tap instead of a typed date. Both defaults are printed
    here and both can be changed from here, and `recurring_list` prints the
    period and the next run date on every row, so a wrong default shows up at
    once rather than months later.
    """
    picked = period or "monthly"
    label = RECURRING_PERIOD_LABELS.get(picked, "")
    text = rtl(
        _problem(problem)
        + f"تکرار: {label}\n\n"
        "از چه تاریخی شروع شود؟\n\n"
        "مثال: 1405/08/01 یا «فردا»؛ یا دکمهٔ «امروز» را بزن."
    )
    return text, [
        [Button("✅ ثبت از امروز", data="rr:today")],
        *rows_of([
            Button(("◉ " if picked == "monthly" else "◯ ") + "ماهانه", data="rr:period:monthly"),
            Button(("◉ " if picked == "weekly" else "◯ ") + "هفتگی", data="rr:period:weekly"),
            Button(("◉ " if picked == "daily" else "◯ ") + "روزانه", data="rr:period:daily"),
        ], 3),
        cancel_row(cancel_data),
    ]


# =============================================================== reminders
def reminder_settings(user) -> Screen:
    digest = "روشن ✅" if user.digest_enabled else "خاموش ❌"
    text = rtl(
        "🔔 یادآورها\n\n"
        "خلاصهٔ روزانه، آخر هر روزی که چیزی ثبت شده باشد، فرستاده می‌شود.\n"
        "یادآور قسط و سررسید، قبل از موعد خبر می‌دهد."
    )
    # The switch is what this panel is for; the two numbers that tune it are
    # peers and share a row. Home really is this screen's parent: the main
    # menu is where «یادآورها» is pressed.
    return text, [
        [Button(f"📊 خلاصهٔ روزانه: {digest}", data="rm:toggle")],
        *rows_of([
            Button(f"🕘 ساعت ارسال: {user.digest_hour}", data="rm:hour"),
            Button(f"⏳ چند روز قبل: {user.reminder_days}", data="rm:days"),
        ]),
        back_row("nav:home"),
    ]


def ask_hour(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "ساعت ارسال خلاصه را بنویس (0 تا 23)؛ مثلاً: 21"), [
        cancel_row("rm:panel")
    ]


def ask_days(problem: Optional[str] = None) -> Screen:
    return rtl(_problem(problem) + "چند روز قبل از سررسید خبر بدهم؟ مثال: 3"), [
        cancel_row("rm:panel")
    ]
