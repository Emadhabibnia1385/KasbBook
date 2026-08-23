"""Loans, recurring rules, budgets and debts."""

import re
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from typing import Optional

from ..access import access_allowed, deny, guarded, resolve_scope_owner, within_quota
from ..budgets import budgets_kb, budgets_text, delete_budget, set_budget
from ..config import CB_BG, CB_DT, CB_LN, CB_RC, DB_LOCK
from ..debts import DEBT_LABELS, create_debt, debts_kb, debts_text, delete_debt, settle_debt
from ..jalali import g_to_j_parts
from ..ledger import SECTION_ORDER
from ..loans import create_loan, delete_loan, get_loan, loan_detail_kb, loan_detail_text, loans_kb, loans_text, record_loan_payment
from ..parsing import parse_amount, parse_date_any, to_ascii_digits
from ..recurring import PERIOD_LABELS, create_recurring, delete_recurring, recurring_kb, recurring_text, run_due_recurring, toggle_recurring
from ..states import BG_AMOUNT, BG_CATNAME, BG_PICK, DT_AMOUNT, DT_DIR, DT_DUE, DT_NOTE, DT_PERSON, LN_AMOUNT, LN_COUNT, LN_START, LN_TITLE, RC_AMOUNT, RC_CAT, RC_DESC, RC_PERIOD, RC_START, RC_TTYPE
from ..text import grp_label, ikb, rtl, safe_edit
from ..timeutil import today_g
from ..screen import render

# =========================
# Loan handlers
# =========================
async def loans_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "noop":
        return ConversationHandler.END

    if act in ("panel", "page"):
        page = 0
        if act == "page":
            try:
                page = int(parts[2])
            except (IndexError, ValueError):
                page = 0
        await safe_edit(q, loans_text(scope, owner, page), reply_markup=loans_kb(scope, owner, page))
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        await safe_edit(q, rtl("📄 نام وام را بنویس (مثلاً: وام مسکن):"))
        return LN_TITLE

    loan_id = int(parts[2])

    if act == "open":
        await safe_edit(q, loan_detail_text(scope, owner, loan_id), reply_markup=loan_detail_kb(loan_id))
        return ConversationHandler.END

    if act == "pay":
        loan = get_loan(scope, owner, loan_id)
        if not loan:
            await safe_edit(q, loans_text(scope, owner), reply_markup=loans_kb(scope, owner))
            return ConversationHandler.END

        ok, why = within_quota(scope, owner, "tx")
        if not ok:
            await safe_edit(q, rtl(f"⛔ {why}"), reply_markup=loan_detail_kb(loan_id))
            return ConversationHandler.END

        async with DB_LOCK:
            record_loan_payment(scope, owner, user.id, loan_id)

        await safe_edit(q, loan_detail_text(scope, owner, loan_id), reply_markup=loan_detail_kb(loan_id))
        return ConversationHandler.END

    if act == "del":
        loan = get_loan(scope, owner, loan_id)
        if not loan:
            await safe_edit(q, loans_text(scope, owner), reply_markup=loans_kb(scope, owner))
            return ConversationHandler.END

        kb = ikb([
            [("🗑 بله، حذف کن", f"{CB_LN}:delok:{loan_id}")],
            [("↩️ انصراف", f"{CB_LN}:open:{loan_id}")],
        ])
        await safe_edit(q, rtl(
            f"⚠️ حذف وام «{loan['title']}»\n\n"
            "پرداخت‌های ثبت‌شده حذف نمی‌شوند و در گزارش‌ها می‌مانند؛\n"
            "فقط پیگیری تعداد اقساط از بین می‌رود.\n\n"
            "آیا مطمئنی؟"
        ), reply_markup=kb)
        return ConversationHandler.END

    if act == "delok":
        async with DB_LOCK:
            delete_loan(scope, owner, loan_id)
        await safe_edit(q, loans_text(scope, owner), reply_markup=loans_kb(scope, owner))
        return ConversationHandler.END

    await safe_edit(q, loans_text(scope, owner), reply_markup=loans_kb(scope, owner))
    return ConversationHandler.END

@guarded
async def loan_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = (update.message.text or "").strip()
    if not title:
        await render(update, context, rtl("نام خالی است. دوباره بنویس:"))
        return LN_TITLE

    context.user_data["loan_title"] = title[:60]
    await render(update, context, rtl("💵 مبلغ هر قسط را بنویس (مثلاً ۲م یا 2000000):"))
    return LN_AMOUNT

@guarded
async def loan_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount = parse_amount(update.message.text or "")
    if amount is None or amount <= 0:
        await render(update, context, rtl("❌ مبلغ نامعتبر است. دوباره:"))
        return LN_AMOUNT

    context.user_data["loan_amount"] = amount
    await render(update, context, rtl("🔢 تعداد کل اقساط را بنویس (مثلاً 24):"))
    return LN_COUNT

@guarded
async def loan_count_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = to_ascii_digits(update.message.text or "").strip()
    if not re.fullmatch(r"\d{1,4}", raw) or int(raw) <= 0:
        await render(update, context, rtl("❌ فقط عدد بین ۱ تا ۹۹۹۹ وارد کن:"))
        return LN_COUNT

    context.user_data["loan_count"] = int(raw)
    await render(update, context, 
        rtl("🗓 تاریخ اولین قسط را بنویس (شمسی یا میلادی) یا «امروز»:")
    )
    return LN_START

@guarded
async def loan_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    start = parse_date_any(update.message.text or "")
    if not start:
        await render(update, context, rtl("❌ تاریخ نامعتبر است. مثلاً 1404/05/01 یا «امروز»:"))
        return LN_START

    title = context.user_data.get("loan_title")
    amount = context.user_data.get("loan_amount")
    count = context.user_data.get("loan_count")
    if not title or amount is None or not count:
        await render(update, context, rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        create_loan(scope, owner, title, int(amount), int(count), start)

    context.user_data.clear()
    await render(update, context, 
        loans_text(scope, owner), reply_markup=loans_kb(scope, owner)
    )
    return ConversationHandler.END

# =========================
# Recurring handlers
# =========================
def rc_ttype_kb() -> InlineKeyboardMarkup:
    rows = [[(grp_label(g), f"{CB_RC}:tt:{g}")] for g in SECTION_ORDER]
    rows.append([("↩️ انصراف", f"{CB_RC}:panel")])
    return ikb(rows)

def rc_period_kb() -> InlineKeyboardMarkup:
    rows = [[(PERIOD_LABELS[p], f"{CB_RC}:pr:{p}")] for p in ("monthly", "weekly", "daily")]
    rows.append([("↩️ انصراف", f"{CB_RC}:panel")])
    return ikb(rows)

async def recurring_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "noop":
        return ConversationHandler.END

    if act in ("panel", "page"):
        page = 0
        if act == "page":
            try:
                page = int(parts[2])
            except (IndexError, ValueError):
                page = 0
        context.user_data.pop("rc_draft", None)
        await safe_edit(q, recurring_text(scope, owner, page), reply_markup=recurring_kb(scope, owner, page))
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        context.user_data["rc_draft"] = {}
        await safe_edit(q, rtl("🔁 نوع تراکنش تکرارشونده را انتخاب کن:"), reply_markup=rc_ttype_kb())
        return RC_TTYPE

    if act == "tog":
        async with DB_LOCK:
            toggle_recurring(scope, owner, int(parts[2]))
        await safe_edit(q, recurring_text(scope, owner), reply_markup=recurring_kb(scope, owner))
        return ConversationHandler.END

    if act == "del":
        kb = ikb([
            [("🗑 بله، حذف کن", f"{CB_RC}:delok:{parts[2]}")],
            [("↩️ انصراف", f"{CB_RC}:panel")],
        ])
        await safe_edit(q, rtl(
            "⚠️ حذف قاعدهٔ تکرارشونده\n\n"
            "تراکنش‌هایی که تا الان ساخته حذف نمی‌شوند.\n\n"
            "آیا مطمئنی؟"
        ), reply_markup=kb)
        return ConversationHandler.END

    if act == "delok":
        async with DB_LOCK:
            delete_recurring(scope, owner, int(parts[2]))
        await safe_edit(q, recurring_text(scope, owner), reply_markup=recurring_kb(scope, owner))
        return ConversationHandler.END

    await safe_edit(q, recurring_text(scope, owner), reply_markup=recurring_kb(scope, owner))
    return ConversationHandler.END

@guarded
async def rc_ttype_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    ttype = (q.data or "").split(":")[2]
    if ttype not in SECTION_ORDER:
        await safe_edit(q, rtl("نوع نامعتبر."), reply_markup=rc_ttype_kb())
        return RC_TTYPE

    context.user_data.setdefault("rc_draft", {})["ttype"] = ttype
    await safe_edit(q, rtl(f"🏷 نام دسته را بنویس ({grp_label(ttype)}):"))
    return RC_CAT

@guarded
async def rc_cat_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.message.text or "").strip()
    if not name:
        await render(update, context, rtl("نام خالی است. دوباره:"))
        return RC_CAT

    context.user_data.setdefault("rc_draft", {})["category"] = name[:40]
    await render(update, context, rtl("💵 مبلغ را بنویس:"))
    return RC_AMOUNT

@guarded
async def rc_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount = parse_amount(update.message.text or "")
    if amount is None:
        await render(update, context, rtl("❌ مبلغ نامعتبر است. دوباره:"))
        return RC_AMOUNT

    context.user_data.setdefault("rc_draft", {})["amount"] = amount
    await render(update, context, rtl("📝 توضیح (اختیاری) یا /skip:"))
    return RC_DESC

@guarded
async def rc_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = (update.message.text or "").strip()
    context.user_data.setdefault("rc_draft", {})["description"] = desc or None
    await render(update, context, rtl("⏱ هر چند وقت تکرار شود؟"), reply_markup=rc_period_kb())
    return RC_PERIOD

@guarded
async def rc_desc_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("rc_draft", {})["description"] = None
    await render(update, context, rtl("⏱ هر چند وقت تکرار شود؟"), reply_markup=rc_period_kb())
    return RC_PERIOD

@guarded
async def rc_period_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    period = (q.data or "").split(":")[2]
    if period not in PERIOD_LABELS:
        await safe_edit(q, rtl("دوره نامعتبر."), reply_markup=rc_period_kb())
        return RC_PERIOD

    context.user_data.setdefault("rc_draft", {})["period"] = period
    await safe_edit(q, rtl("🗓 اولین اجرا از چه تاریخی؟ (شمسی/میلادی یا «امروز»)"))
    return RC_START

@guarded
async def rc_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    start = parse_date_any(update.message.text or "")
    if not start:
        await render(update, context, rtl("❌ تاریخ نامعتبر است. دوباره:"))
        return RC_START

    draft = context.user_data.get("rc_draft") or {}
    needed = ("ttype", "category", "amount", "period")
    if any(draft.get(k) is None for k in needed):
        await render(update, context, rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        create_recurring(
            scope, owner, draft["ttype"], draft["category"], int(draft["amount"]),
            draft.get("description"), draft["period"], start,
        )
        # Anything already due fires immediately, so the first run is not a surprise.
        run_due_recurring()

    context.user_data.clear()
    await render(update, context, 
        recurring_text(scope, owner), reply_markup=recurring_kb(scope, owner)
    )
    return ConversationHandler.END

# =========================
# Budget handlers
# =========================
def budget_pick_kb() -> InlineKeyboardMarkup:
    rows = [[(f"کل {grp_label(g)}", f"{CB_BG}:t:g:{g}")] for g in SECTION_ORDER]
    rows.append([("🏷 یک دستهٔ مشخص", f"{CB_BG}:t:c")])
    rows.append([("↩️ انصراف", f"{CB_BG}:panel")])
    return ikb(rows)

async def budgets_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "noop":
        return ConversationHandler.END

    if act in ("panel", "page"):
        page = 0
        if act == "page":
            try:
                page = int(parts[2])
            except (IndexError, ValueError):
                page = 0
        context.user_data.pop("bg_draft", None)
        jy, jm, _ = g_to_j_parts(today_g())
        await safe_edit(q, budgets_text(scope, owner, jy, jm, page),
                        reply_markup=budgets_kb(scope, owner, page))
        return ConversationHandler.END

    if act == "del":
        async with DB_LOCK:
            delete_budget(scope, owner, int(parts[2]))
        jy, jm, _ = g_to_j_parts(today_g())
        await safe_edit(q, budgets_text(scope, owner, jy, jm), reply_markup=budgets_kb(scope, owner))
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        context.user_data["bg_draft"] = {}
        await safe_edit(q, rtl("🎯 بودجه برای چه چیزی؟"), reply_markup=budget_pick_kb())
        return BG_PICK

    if act == "t":
        draft = context.user_data.setdefault("bg_draft", {})
        if parts[2] == "g":
            draft["kind"] = "group"
            draft["target"] = parts[3]
            await safe_edit(q, rtl(f"💵 سقف ماهانه برای {grp_label(parts[3])} را بنویس:"))
            return BG_AMOUNT

        draft["kind"] = "category"
        await safe_edit(q, rtl("🏷 نام دقیق دسته را بنویس:"))
        return BG_CATNAME

    jy, jm, _ = g_to_j_parts(today_g())
    await safe_edit(q, budgets_text(scope, owner, jy, jm), reply_markup=budgets_kb(scope, owner))
    return ConversationHandler.END

@guarded
async def budget_catname_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.message.text or "").strip()
    if not name:
        await render(update, context, rtl("نام خالی است. دوباره:"))
        return BG_CATNAME

    context.user_data.setdefault("bg_draft", {})["target"] = name[:40]
    await render(update, context, rtl(f"💵 سقف ماهانه برای «{name}» را بنویس:"))
    return BG_AMOUNT

@guarded
async def budget_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    amount = parse_amount(update.message.text or "")
    if amount is None or amount <= 0:
        await render(update, context, rtl("❌ مبلغ نامعتبر است. دوباره:"))
        return BG_AMOUNT

    draft = context.user_data.get("bg_draft") or {}
    if not draft.get("kind") or not draft.get("target"):
        await render(update, context, rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        set_budget(scope, owner, draft["kind"], draft["target"], amount)

    context.user_data.clear()
    jy, jm, _ = g_to_j_parts(today_g())
    await render(update, context, 
        budgets_text(scope, owner, jy, jm), reply_markup=budgets_kb(scope, owner)
    )
    return ConversationHandler.END

# =========================
# Debt handlers
# =========================
def debt_dir_kb() -> InlineKeyboardMarkup:
    return ikb([
        [("📥 به من بدهکار است", f"{CB_DT}:dir:owed_to_me")],
        [("📤 من بدهکارم", f"{CB_DT}:dir:i_owe")],
        [("↩️ انصراف", f"{CB_DT}:panel")],
    ])

async def debts_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "noop":
        return ConversationHandler.END

    if act in ("panel", "page", "all"):
        page = 0
        if act == "page":
            try:
                page = int(parts[2])
            except (IndexError, ValueError):
                page = 0
        context.user_data.pop("dt_draft", None)
        await safe_edit(q,
            debts_text(scope, owner, page, include_settled=(act == "all")),
            reply_markup=debts_kb(scope, owner, page),
        )
        return ConversationHandler.END

    if act == "settle":
        async with DB_LOCK:
            settle_debt(scope, owner, int(parts[2]))
        await safe_edit(q, debts_text(scope, owner), reply_markup=debts_kb(scope, owner))
        return ConversationHandler.END

    if act == "del":
        async with DB_LOCK:
            delete_debt(scope, owner, int(parts[2]))
        await safe_edit(q, debts_text(scope, owner), reply_markup=debts_kb(scope, owner))
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        context.user_data["dt_draft"] = {}
        await safe_edit(q, rtl("👤 نام طرف حساب را بنویس:"))
        return DT_PERSON

    await safe_edit(q, debts_text(scope, owner), reply_markup=debts_kb(scope, owner))
    return ConversationHandler.END

@guarded
async def debt_person_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    person = (update.message.text or "").strip()
    if not person:
        await render(update, context, rtl("نام خالی است. دوباره:"))
        return DT_PERSON

    context.user_data.setdefault("dt_draft", {})["person"] = person[:40]
    await render(update, context, rtl("جهت را انتخاب کن:"), reply_markup=debt_dir_kb())
    return DT_DIR

@guarded
async def debt_dir_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    direction = (q.data or "").split(":")[2]
    if direction not in DEBT_LABELS:
        await safe_edit(q, rtl("گزینه نامعتبر."), reply_markup=debt_dir_kb())
        return DT_DIR

    context.user_data.setdefault("dt_draft", {})["direction"] = direction
    await safe_edit(q, rtl("💵 مبلغ را بنویس:"))
    return DT_AMOUNT

@guarded
async def debt_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount = parse_amount(update.message.text or "")
    if amount is None:
        await render(update, context, rtl("❌ مبلغ نامعتبر است. دوباره:"))
        return DT_AMOUNT

    context.user_data.setdefault("dt_draft", {})["amount"] = amount
    await render(update, context, rtl("📝 توضیح (اختیاری) یا /skip:"))
    return DT_NOTE

@guarded
async def debt_note_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note = (update.message.text or "").strip()
    context.user_data.setdefault("dt_draft", {})["note"] = note or None
    await render(update, context, rtl("🗓 سررسید (اختیاری) یا /skip:"))
    return DT_DUE

@guarded
async def debt_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("dt_draft", {})["note"] = None
    await render(update, context, rtl("🗓 سررسید (اختیاری) یا /skip:"))
    return DT_DUE

async def _save_debt(update: Update, context: ContextTypes.DEFAULT_TYPE, due: Optional[str]) -> int:
    user = update.effective_user
    draft = context.user_data.get("dt_draft") or {}
    if not draft.get("person") or not draft.get("direction") or draft.get("amount") is None:
        await render(update, context, rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        create_debt(scope, owner, draft["person"], draft["direction"],
                    int(draft["amount"]), draft.get("note"), due)

    context.user_data.clear()
    await render(update, context, 
        debts_text(scope, owner), reply_markup=debts_kb(scope, owner)
    )
    return ConversationHandler.END

@guarded
async def debt_due_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    due = parse_date_any(update.message.text or "")
    if not due:
        await render(update, context, rtl("❌ تاریخ نامعتبر است. دوباره یا /skip:"))
        return DT_DUE
    return await _save_debt(update, context, due)

@guarded
async def debt_due_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_debt(update, context, None)
