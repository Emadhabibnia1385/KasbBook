"""Report screens, search and custom ranges."""

import io
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from ..access import access_allowed, deny, resolve_scope_owner
from ..config import SEARCH_PAGE_SIZE
from ..jalali import g_to_j, j_month_range_g, j_year_range_g, jmonth_name
from ..ledger import sums_all, sums_for_range
from ..menus import main_menu
from ..parsing import parse_date_any
from ..reports import TREND_METRICS, back_to_period_kb, breakdown_text, category_breakdown, comparison_lines, csv_filename, jalali_years_with_data, make_csv_bytes, parse_period, range_report_kb, report_lines, report_month_kb, report_root_kb, report_year_kb, search_results_kb, search_results_text, search_transactions, trend_kb, trend_text
from ..states import RG_END, RG_START, SR_QUERY
from ..text import rtl, safe_edit

# --- report screens --------------------------------------------------------
async def report_root(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return

    scope, owner = resolve_scope_owner(user.id)
    s = sums_all(scope, owner)
    years = jalali_years_with_data(scope, owner)

    text = report_lines("📊 گزارش کلی", s)
    kb = report_root_kb(years)

    if edit and update.callback_query:
        await safe_edit(update.callback_query, text, reply_markup=kb)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb)

async def report_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    parts = (q.data or "").split(":")
    act = parts[1]

    scope, owner = resolve_scope_owner(user.id)

    if act == "root":
        await report_root(update, context, edit=True)
        return

    if act == "y":
        jy = int(parts[2])
        start, end = j_year_range_g(jy)
        s = sums_for_range(scope, owner, start, end)
        extra = comparison_lines(scope, owner, f"y:{jy}")
        await safe_edit(q, report_lines(f"📊 گزارش سال {jy}", s, extra), reply_markup=report_year_kb(jy))
        return

    if act == "m":
        jy, jm = int(parts[2]), int(parts[3])
        start, end = j_month_range_g(jy, jm)
        s = sums_for_range(scope, owner, start, end)
        title = f"📊 گزارش {jmonth_name(jm)} {jy}"
        extra = comparison_lines(scope, owner, f"m:{jy}:{jm:02d}")
        await safe_edit(q, report_lines(title, s, extra), reply_markup=report_month_kb(jy, jm))
        return

    if act == "r":
        s_g, e_g = parts[2], parts[3]
        _, title, start, end = parse_period(["r", s_g, e_g])
        s = sums_for_range(scope, owner, start, end)
        await safe_edit(q, report_lines(f"📊 گزارش {title}", s), reply_markup=range_report_kb(s_g, e_g))
        return

    if act == "bd":
        spec, title, start, end = parse_period(parts[2:])
        data = category_breakdown(scope, owner, start, end)
        await safe_edit(q, breakdown_text(title, data), reply_markup=back_to_period_kb(spec))
        return

    if act == "csv":
        spec, title, start, end = parse_period(parts[2:])
        payload = make_csv_bytes(scope, owner, start, end)

        bio = io.BytesIO(payload)
        fname = csv_filename(spec)
        bio.name = fname

        await context.bot.send_document(
            chat_id=user.id,
            document=bio,
            filename=fname,
            caption=rtl(f"📥 خروجی تراکنش‌ها — {title}"),
        )
        return

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=main_menu())

# =========================
# Search handlers
# =========================
async def search_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    await safe_edit(q, rtl(
        "🔎 جست‌وجو\n\n"
        "بخشی از نام دسته یا توضیح را بنویس.\n"
        "مثال: اجاره"
    ))
    return SR_QUERY

async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, edit: bool) -> None:
    user = update.effective_user
    scope, owner = resolve_scope_owner(user.id)

    query = context.chat_data.get("search_query", "")
    rows, total = search_transactions(scope, owner, query, None, None, page, SEARCH_PAGE_SIZE)
    context.chat_data["search_page"] = page

    text = search_results_text(query, rows, total, page)
    kb = search_results_kb(query, "a", page, total)

    if edit and update.callback_query:
        await safe_edit(update.callback_query, text, reply_markup=kb)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb)

async def search_query_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    query = (update.message.text or "").strip()
    if len(query) < 2:
        await update.effective_chat.send_message(rtl("❌ حداقل ۲ نویسه بنویس:"))
        return SR_QUERY

    context.chat_data["search_query"] = query[:60]
    await show_search_results(update, context, 0, edit=False)
    return ConversationHandler.END

async def search_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    if not context.chat_data.get("search_query"):
        await safe_edit(q, rtl("جست‌وجو منقضی شده. دوباره شروع کن."), reply_markup=main_menu())
        return

    try:
        page = int((q.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 0
    await show_search_results(update, context, page, edit=True)

# =========================
# Custom date range
# =========================
async def range_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    context.user_data.clear()
    await safe_edit(q, rtl(
        "📆 بازهٔ دلخواه\n\n"
        "تاریخ شروع را بنویس (شمسی یا میلادی).\n"
        "مثال: 1404/01/01"
    ))
    return RG_START

async def range_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    start = parse_date_any(update.message.text or "")
    if not start:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره:"))
        return RG_START

    context.user_data["range_start"] = start
    await update.effective_chat.send_message(
        rtl(f"شروع: {g_to_j(start)}\n\nحالا تاریخ پایان را بنویس:")
    )
    return RG_END

async def range_end_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    end = parse_date_any(update.message.text or "")
    if not end:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره:"))
        return RG_END

    start = context.user_data.get("range_start")
    if not start:
        await update.effective_chat.send_message(rtl("خطا: تاریخ شروع مشخص نیست."))
        context.user_data.clear()
        return ConversationHandler.END

    if end < start:
        start, end = end, start

    context.user_data.clear()
    scope, owner = resolve_scope_owner(user.id)
    _, title, s_g, e_ex = parse_period(["r", start, end])
    s = sums_for_range(scope, owner, s_g, e_ex)

    await update.effective_chat.send_message(
        report_lines(f"📊 گزارش {title}", s), reply_markup=range_report_kb(start, end)
    )
    return ConversationHandler.END

# =========================
# Trend handler
# =========================
async def trend_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    parts = (q.data or "").split(":")
    metric = parts[2] if len(parts) > 2 else "savings_final"
    try:
        months = int(parts[3])
    except (IndexError, ValueError):
        months = 6

    if metric not in TREND_METRICS:
        metric = "savings_final"
    months = 12 if months == 12 else 6

    scope, owner = resolve_scope_owner(user.id)
    await safe_edit(q, trend_text(scope, owner, metric, months), reply_markup=trend_kb(metric, months))
