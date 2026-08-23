"""Recording, listing and editing transactions."""

import re
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from typing import Optional

from ..access import access_allowed, deny, resolve_scope_owner, within_quota
from ..budgets import budget_warning
from ..categories import cat_pick_keyboard, ensure_installment
from ..config import CB_DL, CB_DTX, CB_M, DB_LOCK
from ..jalali import g_to_j
from ..ledger import current_pages, daily_back_cb, daily_list_text, daily_rows_kb, ed_date_menu_kb, get_tx, remember_pages, restore_tx, set_receipt, snapshot_tx, tx_cat_change_kb, tx_detail_text, tx_view_kb
from ..menus import daily_pick_menu, tx_date_menu_kb, tx_menu, tx_ttype_kb
from ..money import fmt_money
from ..parsing import parse_gregorian, parse_jalali_to_g
from ..states import DL_DATE_G, DL_DATE_J, DL_DATE_MENU, ED_AMOUNT, ED_DATE_G, ED_DATE_J, ED_DATE_MENU, ED_DESC, RCP_WAIT, TX_AMOUNT, TX_CAT_ADD_NAME, TX_CAT_PICK, TX_DATE_G, TX_DATE_J, TX_DATE_MENU, TX_DESC, TX_TTYPE
from ..store import db
from ..text import fmt_num, ikb, rtl, safe_edit, ttype_label
from ..timeutil import now_ts, today_g

async def tx_entry_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    context.user_data.clear()
    context.user_data["tx_origin"] = "menu"

    await safe_edit(q,
        rtl("📅 تاریخ را انتخاب کنید:"),
        reply_markup=tx_date_menu_kb(back_cb=f"{CB_M}:tx"),
    )
    return TX_DATE_MENU

async def tx_entry_from_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    gdate = parts[2]
    ttype = parts[3]
    if ttype not in ("work_in", "work_out", "personal_in", "personal_out"):
        await safe_edit(q, rtl("نوع نامعتبر."), reply_markup=tx_menu())
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["tx_origin"] = "daily"
    context.user_data["tx_date_g"] = gdate
    context.user_data["tx_ttype"] = ttype
    context.user_data["tx_daily_gdate"] = gdate

    scope, owner = resolve_scope_owner(user.id)
    context.user_data["tx_cat_back"] = f"{CB_DL}:show:{gdate}"
    await safe_edit(q,
        rtl(f"🏷 دسته را انتخاب کنید:\n\n📅 تاریخ: {gdate} ({g_to_j(gdate)})\n🔖 نوع: {ttype_label(ttype)}"),
        reply_markup=cat_pick_keyboard(scope, owner, ttype, back_cb=f"{CB_DL}:show:{gdate}"),
    )
    return TX_CAT_PICK

async def tx_date_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    mode = parts[2]

    if mode == "today":
        gdate = today_g()
        context.user_data["tx_date_g"] = gdate
        await safe_edit(q,
            rtl(f"🔖 نوع تراکنش را انتخاب کنید:\n\n📅 تاریخ: {gdate} ({g_to_j(gdate)})"),
            reply_markup=tx_ttype_kb(back_cb=f"{CB_M}:tx"),
        )
        return TX_TTYPE

    if mode == "g":
        await safe_edit(q, rtl("تاریخ میلادی را وارد کنید (YYYY-MM-DD):"))
        return TX_DATE_G

    if mode == "j":
        await safe_edit(q, rtl("تاریخ شمسی را وارد کنید (YYYY/MM/DD):"))
        return TX_DATE_J

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=tx_menu())
    return ConversationHandler.END

async def tx_date_g_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_gregorian(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره (YYYY-MM-DD):"))
        return TX_DATE_G

    context.user_data["tx_date_g"] = g
    await update.effective_chat.send_message(
        rtl(f"🔖 نوع تراکنش را انتخاب کنید:\n\n📅 تاریخ: {g} ({g_to_j(g)})"),
        reply_markup=tx_ttype_kb(back_cb=f"{CB_M}:tx"),
    )
    return TX_TTYPE

async def tx_date_j_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_jalali_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره (YYYY/MM/DD):"))
        return TX_DATE_J

    context.user_data["tx_date_g"] = g
    await update.effective_chat.send_message(rtl(f"✅ تبدیل شد به میلادی: {g}"))
    await update.effective_chat.send_message(
        rtl(f"🔖 نوع تراکنش را انتخاب کنید:\n\n📅 تاریخ: {g} ({g_to_j(g)})"),
        reply_markup=tx_ttype_kb(back_cb=f"{CB_M}:tx"),
    )
    return TX_TTYPE

async def tx_ttype_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    ttype = parts[2]
    if ttype not in ("work_in", "work_out", "personal_in", "personal_out"):
        await safe_edit(q, rtl("نوع نامعتبر."), reply_markup=tx_menu())
        return ConversationHandler.END

    gdate = context.user_data.get("tx_date_g")
    if not gdate:
        await safe_edit(q, rtl("خطا: تاریخ مشخص نیست."), reply_markup=tx_menu())
        return ConversationHandler.END

    context.user_data["tx_ttype"] = ttype
    context.user_data["tx_cat_back"] = f"{CB_M}:tx"
    scope, owner = resolve_scope_owner(user.id)
    await safe_edit(q,
        rtl(f"🏷 دسته را انتخاب کنید:\n\n📅 تاریخ: {gdate} ({g_to_j(gdate)})\n🔖 نوع: {ttype_label(ttype)}"),
        reply_markup=cat_pick_keyboard(scope, owner, ttype, back_cb=f"{CB_M}:tx"),
    )
    return TX_CAT_PICK

async def tx_cat_pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "cat_add":
        await safe_edit(q, rtl("نام دسته جدید را وارد کنید:"))
        return TX_CAT_ADD_NAME

    if act == "catp":
        ttype = context.user_data.get("tx_ttype")
        gdate = context.user_data.get("tx_date_g")
        if ttype not in ("work_in", "work_out", "personal_in", "personal_out") or not gdate:
            await safe_edit(q, rtl("خطا: اطلاعات ناقص."), reply_markup=tx_menu())
            context.user_data.clear()
            return ConversationHandler.END

        try:
            page = int(parts[2])
        except (IndexError, ValueError):
            page = 0

        back_cb = context.user_data.get("tx_cat_back") or f"{CB_M}:tx"
        scope, owner = resolve_scope_owner(user.id)
        await safe_edit(q,
            rtl(f"🏷 دسته را انتخاب کنید:\n\n📅 تاریخ: {gdate} ({g_to_j(gdate)})\n🔖 نوع: {ttype_label(ttype)}"),
            reply_markup=cat_pick_keyboard(scope, owner, ttype, back_cb=back_cb, page=page),
        )
        return TX_CAT_PICK

    if act != "cat":
        await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=tx_menu())
        return ConversationHandler.END

    try:
        cid = int(parts[2])
    except Exception:
        await safe_edit(q, rtl("دسته نامعتبر."), reply_markup=tx_menu())
        return ConversationHandler.END

    ttype = context.user_data.get("tx_ttype")
    gdate = context.user_data.get("tx_date_g")
    if ttype not in ("work_in", "work_out", "personal_in", "personal_out") or not gdate:
        await safe_edit(q, rtl("خطا: اطلاعات ناقص."), reply_markup=tx_menu())
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    with db() as conn:
        row = conn.execute(
            "SELECT name FROM categories WHERE id=? AND scope=? AND owner_user_id=? AND grp=?",
            (cid, scope, owner, ttype),
        ).fetchone()

    if not row:
        await safe_edit(q, rtl("دسته پیدا نشد. دوباره انتخاب کنید."))
        return TX_CAT_PICK

    context.user_data["tx_category"] = row["name"]
    await safe_edit(q, rtl("💵 مبلغ را وارد کنید (عدد صحیح):"))
    return TX_AMOUNT

async def tx_cat_add_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message(rtl("نام خالی است. دوباره وارد کنید:"))
        return TX_CAT_ADD_NAME

    ttype = context.user_data.get("tx_ttype")
    gdate = context.user_data.get("tx_date_g")
    if ttype not in ("work_in", "work_out", "personal_in", "personal_out") or not gdate:
        await update.effective_chat.send_message(rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)

    async with DB_LOCK:
        with db() as conn:
            try:
                conn.execute(
                    "INSERT INTO categories(scope, owner_user_id, grp, name, is_locked) VALUES(?,?,?,?,0)",
                    (scope, owner, ttype, name),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass

    context.user_data["tx_category"] = name
    await update.effective_chat.send_message(rtl("✅ دسته اضافه شد.\n\n💵 حالا مبلغ را وارد کنید:"))
    return TX_AMOUNT

async def tx_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    t = (update.message.text or "").strip().replace(",", "").replace("،", "")
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message(rtl("❌ مبلغ نامعتبر است. فقط عدد وارد کنید:"))
        return TX_AMOUNT

    context.user_data["tx_amount"] = int(t)
    await update.effective_chat.send_message(rtl("📝 توضیحات (اختیاری) را وارد کنید یا /skip بزنید:"))
    return TX_DESC

async def tx_desc_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await finalize_tx(update, context, None)

async def tx_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = (update.message.text or "").strip()
    return await finalize_tx(update, context, desc if desc else None)

async def finalize_tx(update: Update, context: ContextTypes.DEFAULT_TYPE, desc: Optional[str]) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    ttype = context.user_data.get("tx_ttype")
    date_g_ = context.user_data.get("tx_date_g")
    category = context.user_data.get("tx_category")
    amount = context.user_data.get("tx_amount")

    if ttype not in ("work_in", "work_out", "personal_in", "personal_out") or not date_g_ or not category or amount is None:
        await update.effective_chat.send_message(rtl("خطا: اطلاعات ناقص است."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)

    ok, why = within_quota(scope, owner, "tx")
    if not ok:
        await update.effective_chat.send_message(rtl(f"⛔ {why}"))
        context.user_data.clear()
        return ConversationHandler.END

    ensure_installment(scope, owner)

    ts = now_ts()
    async with DB_LOCK:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO transactions(
                    scope, owner_user_id, actor_user_id,
                    date_g, ttype, category, amount, description,
                    created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (scope, owner, user.id, date_g_, ttype, category, int(amount), desc, ts, ts),
            )
            conn.commit()

    origin = context.user_data.get("tx_origin")
    daily_g = context.user_data.get("tx_daily_gdate")

    if origin == "daily" and isinstance(daily_g, str):
        await update.effective_chat.send_message(
            daily_list_text(scope, owner, daily_g),
            reply_markup=daily_rows_kb(scope, owner, daily_g),
        )
        context.user_data.clear()
        return ConversationHandler.END

    done = "✅ ثبت شد."
    warning = budget_warning(scope, owner, ttype, category, date_g_)
    if warning:
        done += f"\n\n{warning}"

    await update.effective_chat.send_message(rtl(done), reply_markup=tx_menu())
    context.user_data.clear()
    return ConversationHandler.END

async def daily_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    data = (q.data or "").split(":")
    act = data[1] if len(data) > 1 else ""

    if act == "pick":
        context.user_data.clear()
        await safe_edit(q, rtl("📄 لیست روزانه\n\nتاریخ را انتخاب کنید:"), reply_markup=daily_pick_menu())
        return DL_DATE_MENU

    if act == "noop":
        return ConversationHandler.END

    if act == "d":
        mode = data[2]
        if mode == "today":
            gdate = today_g()
            scope, owner = resolve_scope_owner(user.id)
            pages = remember_pages(context, ())
            await safe_edit(q,
                daily_list_text(scope, owner, gdate),
                reply_markup=daily_rows_kb(scope, owner, gdate, pages),
            )
            return ConversationHandler.END

        if mode == "g":
            await safe_edit(q, rtl("تاریخ میلادی را وارد کنید (YYYY-MM-DD):"))
            return DL_DATE_G

        if mode == "j":
            await safe_edit(q, rtl("تاریخ شمسی را وارد کنید (YYYY/MM/DD):"))
            return DL_DATE_J

    if act in ("show", "page"):
        gdate = data[2]
        # "show" opens at page 1; "page" carries the requested page numbers.
        pages = remember_pages(context, data[3:] if act == "page" else ())
        scope, owner = resolve_scope_owner(user.id)
        await safe_edit(q,
            daily_list_text(scope, owner, gdate),
            reply_markup=daily_rows_kb(scope, owner, gdate, pages),
        )
        return ConversationHandler.END

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=tx_menu())
    return ConversationHandler.END

async def dl_date_g_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_gregorian(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره (YYYY-MM-DD):"))
        return DL_DATE_G

    scope, owner = resolve_scope_owner(user.id)
    await update.effective_chat.send_message(
        daily_list_text(scope, owner, g),
        reply_markup=daily_rows_kb(scope, owner, g),
    )
    context.user_data.clear()
    return ConversationHandler.END

async def dl_date_j_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_jalali_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره (YYYY/MM/DD):"))
        return DL_DATE_J

    scope, owner = resolve_scope_owner(user.id)
    await update.effective_chat.send_message(rtl(f"✅ تبدیل شد به میلادی: {g}"))
    await update.effective_chat.send_message(
        daily_list_text(scope, owner, g),
        reply_markup=daily_rows_kb(scope, owner, g),
    )
    context.user_data.clear()
    return ConversationHandler.END

async def dtx_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    act = parts[1]
    gdate = parts[2]
    tx_id = int(parts[3])

    scope, owner = resolve_scope_owner(user.id)
    tx = get_tx(scope, owner, tx_id)
    if not tx:
        await safe_edit(q, rtl("تراکنش پیدا نشد."), reply_markup=tx_menu())
        return ConversationHandler.END

    back_cb = daily_back_cb(gdate, current_pages(context))

    has_receipt = bool(tx["receipt_file_id"])

    if act == "open":
        await safe_edit(q, tx_detail_text(tx), reply_markup=tx_view_kb(gdate, tx_id, back_cb, has_receipt))
        return ConversationHandler.END

    if act == "rcpv":
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=str(tx["receipt_file_id"]),
                caption=rtl(f"🧾 رسید — {tx['category']} | {fmt_money(int(tx['amount']))}"),
            )
        except Exception:
            # It may have been sent as a file rather than a photo.
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=str(tx["receipt_file_id"]),
                caption=rtl("🧾 رسید"),
            )
        return ConversationHandler.END

    if act == "rcpd":
        async with DB_LOCK:
            set_receipt(scope, owner, tx_id, None)
        tx2 = get_tx(scope, owner, tx_id)
        await safe_edit(q, tx_detail_text(tx2, "🧾 رسید حذف شد."),
                        reply_markup=tx_view_kb(gdate, tx_id, back_cb, False))
        return ConversationHandler.END

    if act == "rcp":
        context.user_data.clear()
        context.user_data["receipt_tx_id"] = tx_id
        context.user_data["receipt_gdate"] = gdate
        await safe_edit(q, rtl(
            "🧾 عکس یا فایل رسید را بفرست.\n\nبرای انصراف /cancel بزن."
        ))
        return RCP_WAIT

    if act == "undo":
        snap = context.chat_data.get("deleted_tx")
        if not snap or int(snap.get("id", -1)) != tx_id:
            await q.answer("چیزی برای بازگرداندن نیست.", show_alert=True)
            return ConversationHandler.END

        async with DB_LOCK:
            restore_tx(snap)
        context.chat_data.pop("deleted_tx", None)

        await safe_edit(q,
            daily_list_text(scope, owner, gdate),
            reply_markup=daily_rows_kb(scope, owner, gdate, current_pages(context)),
        )
        return ConversationHandler.END

    if act == "del":
        # Deleting is irreversible, so confirm before touching the row.
        lines = [
            "⚠️ حذف تراکنش",
            "",
            f"🔖 نوع: {ttype_label(tx['ttype'])}",
            f"🏷 دسته: {tx['category']}",
            f"💵 مبلغ: {fmt_num(int(tx['amount']))}",
            f"📅 تاریخ: {tx['date_g']} ({g_to_j(tx['date_g'])})",
            "",
            "آیا مطمئنی؟ این کار برگشت‌پذیر نیست.",
        ]
        kb = ikb(
            [
                [("🗑 بله، حذف کن", f"{CB_DTX}:delok:{gdate}:{tx_id}")],
                [("↩️ انصراف", f"{CB_DTX}:open:{gdate}:{tx_id}")],
            ]
        )
        await safe_edit(q, rtl("\n".join(lines)), reply_markup=kb)
        return ConversationHandler.END

    if act == "delok":
        # Keep a copy so the delete can be taken back — people mis-tap.
        context.chat_data["deleted_tx"] = snapshot_tx(tx)

        async with DB_LOCK:
            with db() as conn:
                conn.execute(
                    "DELETE FROM transactions WHERE id=? AND scope=? AND owner_user_id=?",
                    (tx_id, scope, owner),
                )
                conn.commit()

        pages = current_pages(context)
        base = daily_rows_kb(scope, owner, gdate, pages)
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("↩️ بازگرداندن حذف", callback_data=f"{CB_DTX}:undo:{gdate}:{tx_id}")]]
            + list(base.inline_keyboard)
        )
        await safe_edit(q, daily_list_text(scope, owner, gdate), reply_markup=kb)
        return ConversationHandler.END

    if act == "amt":
        context.user_data.clear()
        context.user_data["edit_tx_id"] = tx_id
        context.user_data["edit_gdate"] = gdate
        await safe_edit(q, rtl("💵 مبلغ جدید را وارد کنید (عدد):"))
        return ED_AMOUNT

    if act == "desc":
        context.user_data.clear()
        context.user_data["edit_tx_id"] = tx_id
        context.user_data["edit_gdate"] = gdate
        await safe_edit(q, rtl("📝 توضیح جدید را وارد کنید (یا - برای حذف):"))
        return ED_DESC

    if act == "date":
        context.user_data.clear()
        context.user_data["edit_tx_id"] = tx_id
        context.user_data["edit_gdate"] = gdate
        await safe_edit(q,
            rtl(
                "📅 تاریخ جدید تراکنش را انتخاب کنید:\n\n"
                f"تاریخ فعلی: {tx['date_g']} ({g_to_j(tx['date_g'])})"
            ),
            reply_markup=ed_date_menu_kb(gdate, tx_id),
        )
        return ED_DATE_MENU

    if act in ("cat", "catp"):
        page = 0
        if act == "catp":
            try:
                page = int(parts[4])
            except (IndexError, ValueError):
                page = 0
        await safe_edit(q,
            rtl("🏷 دسته جدید را انتخاب کنید:"),
            reply_markup=tx_cat_change_kb(scope, owner, tx["ttype"], gdate, tx_id, page),
        )
        return ConversationHandler.END

    if act == "setcat":
        cat_id = int(parts[4])
        async with DB_LOCK:
            with db() as conn:
                row = conn.execute(
                    "SELECT name FROM categories WHERE id=? AND scope=? AND owner_user_id=? AND grp=?",
                    (cat_id, scope, owner, tx["ttype"]),
                ).fetchone()
                if not row:
                    await safe_edit(q,
                        rtl("دسته پیدا نشد."),
                        reply_markup=tx_view_kb(gdate, tx_id, back_cb, has_receipt),
                    )
                    return ConversationHandler.END

                conn.execute(
                    "UPDATE transactions SET category=?, updated_at=? WHERE id=? AND scope=? AND owner_user_id=?",
                    (row["name"], now_ts(), tx_id, scope, owner),
                )
                conn.commit()

        tx2 = get_tx(scope, owner, tx_id)
        await safe_edit(q,
            tx_detail_text(tx2, "✅ ویرایش شد."),
            reply_markup=tx_view_kb(gdate, tx_id, back_cb, has_receipt),
        )
        return ConversationHandler.END

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=tx_view_kb(gdate, tx_id, back_cb, has_receipt))
    return ConversationHandler.END

async def apply_tx_date(update: Update, context: ContextTypes.DEFAULT_TYPE, new_gdate: str) -> int:
    """Move a transaction to another day, then show that day's list."""
    user = update.effective_user
    tx_id = context.user_data.get("edit_tx_id")
    if not isinstance(tx_id, int):
        await update.effective_chat.send_message(rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        with db() as conn:
            conn.execute(
                "UPDATE transactions SET date_g=?, updated_at=? WHERE id=? AND scope=? AND owner_user_id=?",
                (new_gdate, now_ts(), tx_id, scope, owner),
            )
            conn.commit()

    context.user_data.clear()
    pages = remember_pages(context, ())
    await update.effective_chat.send_message(
        rtl(f"✅ تاریخ تراکنش به {new_gdate} ({g_to_j(new_gdate)}) تغییر کرد.")
    )
    await update.effective_chat.send_message(
        daily_list_text(scope, owner, new_gdate),
        reply_markup=daily_rows_kb(scope, owner, new_gdate, pages),
    )
    return ConversationHandler.END

async def edit_date_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    mode = parts[4]

    if mode == "today":
        await safe_edit(q, rtl("⏳ در حال ثبت..."))
        return await apply_tx_date(update, context, today_g())

    if mode == "g":
        await safe_edit(q, rtl("تاریخ میلادی را وارد کنید (YYYY-MM-DD):"))
        return ED_DATE_G

    if mode == "j":
        await safe_edit(q, rtl("تاریخ شمسی را وارد کنید (YYYY/MM/DD):"))
        return ED_DATE_J

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=tx_menu())
    context.user_data.clear()
    return ConversationHandler.END

async def edit_date_g_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_gregorian(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره (YYYY-MM-DD):"))
        return ED_DATE_G
    return await apply_tx_date(update, context, g)

async def edit_date_j_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_jalali_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره (YYYY/MM/DD):"))
        return ED_DATE_J
    return await apply_tx_date(update, context, g)

async def edit_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    t = (update.message.text or "").strip().replace(",", "").replace("،", "")
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message(rtl("❌ مبلغ نامعتبر است. فقط عدد وارد کنید:"))
        return ED_AMOUNT

    tx_id = context.user_data.get("edit_tx_id")
    gdate = context.user_data.get("edit_gdate")
    if not isinstance(tx_id, int) or not isinstance(gdate, str):
        await update.effective_chat.send_message(rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        with db() as conn:
            conn.execute(
                "UPDATE transactions SET amount=?, updated_at=? WHERE id=? AND scope=? AND owner_user_id=?",
                (int(t), now_ts(), tx_id, scope, owner),
            )
            conn.commit()

    context.user_data.clear()
    await update.effective_chat.send_message(
        daily_list_text(scope, owner, gdate),
        reply_markup=daily_rows_kb(scope, owner, gdate),
    )
    return ConversationHandler.END

async def edit_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    desc = (update.message.text or "").strip()
    if desc == "-":
        desc = ""

    tx_id = context.user_data.get("edit_tx_id")
    gdate = context.user_data.get("edit_gdate")
    if not isinstance(tx_id, int) or not isinstance(gdate, str):
        await update.effective_chat.send_message(rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        with db() as conn:
            conn.execute(
                "UPDATE transactions SET description=?, updated_at=? WHERE id=? AND scope=? AND owner_user_id=?",
                (desc if desc else None, now_ts(), tx_id, scope, owner),
            )
            conn.commit()

    context.user_data.clear()
    await update.effective_chat.send_message(
        daily_list_text(scope, owner, gdate),
        reply_markup=daily_rows_kb(scope, owner, gdate),
    )
    return ConversationHandler.END

# =========================
# Receipt upload
# =========================
async def receipt_wait(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    msg = update.message
    file_id = None
    if msg and msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg and msg.document:
        file_id = msg.document.file_id

    if not file_id:
        await update.effective_chat.send_message(rtl("❌ عکس یا فایل بفرست، یا /cancel بزن."))
        return RCP_WAIT

    tx_id = context.user_data.get("receipt_tx_id")
    gdate = context.user_data.get("receipt_gdate")
    if not isinstance(tx_id, int) or not isinstance(gdate, str):
        await update.effective_chat.send_message(rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        set_receipt(scope, owner, tx_id, file_id)

    context.user_data.clear()
    tx = get_tx(scope, owner, tx_id)
    if not tx:
        await update.effective_chat.send_message(rtl("تراکنش پیدا نشد."), reply_markup=tx_menu())
        return ConversationHandler.END

    await update.effective_chat.send_message(
        tx_detail_text(tx, "🧾 رسید ذخیره شد."),
        reply_markup=tx_view_kb(gdate, tx_id, daily_back_cb(gdate, current_pages(context)), True),
    )
    return ConversationHandler.END
