"""Admin management panel."""

import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from typing import List

from ..access import access_allowed, deny, is_primary_admin
from ..config import ACCESS_ADMIN_ONLY, ADMIN_PAGE_SIZE, CB_AC, CB_AD, DB_LOCK, PRIMARY_ADMIN_USER_ID
from ..menus import access_menu, main_menu
from ..states import ADM_ADD_NAME, ADM_ADD_UID
from ..store import db, get_setting
from ..text import ikb, page_nav_row, rtl, safe_edit
from ..timeutil import now_ts
from ..screen import render

# =========================
# Admin management
# =========================
def build_admin_panel_kb(page: int = 0) -> InlineKeyboardMarkup:
    with db() as conn:
        admins = conn.execute("SELECT user_id, name FROM admins ORDER BY added_at DESC").fetchall()

    page = max(0, min(page, max(0, (len(admins) - 1) // ADMIN_PAGE_SIZE)))
    window = admins[page * ADMIN_PAGE_SIZE:(page + 1) * ADMIN_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton("➕ اضافه کردن ادمین", callback_data=f"{CB_AD}:add")])

    for r in window:
        nm = (r["name"] or "").strip() or str(r["user_id"])
        rows.append(
            [
                InlineKeyboardButton(nm, callback_data=f"{CB_AD}:noop"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"{CB_AD}:del:{r['user_id']}"),
            ]
        )

    nav = page_nav_row(f"{CB_AD}:page:", page, len(admins), ADMIN_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_AC}:noop")])
    return InlineKeyboardMarkup(rows)

async def admin_panel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    if not is_primary_admin(user.id):
        await safe_edit(q, rtl("⛔ فقط ادمین اصلی."), reply_markup=main_menu())
        return ConversationHandler.END

    if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
        await safe_edit(q, rtl("این بخش فقط در حالت ادمین فعال است."), reply_markup=access_menu(user.id))
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    act = parts[1]

    if act in ("panel", "noop"):
        await safe_edit(q, rtl("👥 مدیریت ادمین‌ها:"), reply_markup=build_admin_panel_kb())
        return ConversationHandler.END

    if act == "page":
        try:
            page = int(parts[2])
        except (IndexError, ValueError):
            page = 0
        await safe_edit(q, rtl("👥 مدیریت ادمین‌ها:"), reply_markup=build_admin_panel_kb(page))
        return ConversationHandler.END

    if act == "del":
        try:
            uid = int(parts[2])
        except Exception:
            await safe_edit(q, rtl("آیدی نامعتبر."), reply_markup=build_admin_panel_kb())
            return ConversationHandler.END

        with db() as conn:
            row = conn.execute("SELECT name FROM admins WHERE user_id=?", (uid,)).fetchone()
        if not row:
            await safe_edit(q, rtl("این ادمین پیدا نشد."), reply_markup=build_admin_panel_kb())
            return ConversationHandler.END

        nm = (row["name"] or "").strip() or str(uid)
        kb = ikb(
            [
                [("🗑 بله، حذف کن", f"{CB_AD}:delok:{uid}")],
                [("↩️ انصراف", f"{CB_AD}:panel")],
            ]
        )
        await safe_edit(q,
            rtl(f"⚠️ حذف ادمین\n\n👤 {nm}\n🆔 {uid}\n\nآیا مطمئنی؟"),
            reply_markup=kb,
        )
        return ConversationHandler.END

    if act == "delok":
        try:
            uid = int(parts[2])
        except Exception:
            await safe_edit(q, rtl("آیدی نامعتبر."), reply_markup=build_admin_panel_kb())
            return ConversationHandler.END

        async with DB_LOCK:
            with db() as conn:
                conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
                conn.commit()

        await safe_edit(q, rtl("✅ حذف شد.\n\n👥 مدیریت ادمین‌ها:"), reply_markup=build_admin_panel_kb())
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        await safe_edit(q, rtl("🆔 user_id عددی ادمین جدید را وارد کنید:"))
        return ADM_ADD_UID

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=build_admin_panel_kb())
    return ConversationHandler.END

async def adm_add_uid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_primary_admin(user.id):
        await render(update, context, rtl("⛔ فقط ادمین اصلی."))
        context.user_data.clear()
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if not re.fullmatch(r"\d+", t):
        await render(update, context, rtl("❌ فقط user_id عددی وارد کنید:"))
        return ADM_ADD_UID

    uid = int(t)
    if uid == PRIMARY_ADMIN_USER_ID:
        await render(update, context, rtl("ادمین اصلی را اضافه نکن. یک آیدی دیگر بده:"))
        return ADM_ADD_UID

    context.user_data["new_admin_uid"] = uid
    await render(update, context, rtl("👤 نام/یوزرنیم ادمین را وارد کنید (مثلاً @ali یا Ali):"))
    return ADM_ADD_NAME

async def adm_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_primary_admin(user.id):
        await render(update, context, rtl("⛔ فقط ادمین اصلی."))
        context.user_data.clear()
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await render(update, context, rtl("نام خالی است. دوباره:"))
        return ADM_ADD_NAME

    uid = context.user_data.get("new_admin_uid")
    if not isinstance(uid, int):
        await render(update, context, rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    async with DB_LOCK:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO admins(user_id, name, added_at)
                VALUES(?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, added_at=excluded.added_at
                """,
                (uid, name, now_ts()),
            )
            conn.commit()

    await render(update, context, 
        rtl("✅ اضافه شد.\n\n👥 مدیریت ادمین‌ها:"),
        reply_markup=build_admin_panel_kb(),
    )
    context.user_data.clear()
    return ConversationHandler.END
