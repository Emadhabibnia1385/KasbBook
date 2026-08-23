"""Category management screens."""

import sqlite3
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from ..access import access_allowed, deny, resolve_scope_owner, within_quota
from ..categories import build_cat_kb, ensure_installment
from ..config import CB_CT, DB_LOCK, INSTALLMENT_NAME
from ..menus import cats_root_menu
from ..states import CAT_ADD_NAME, CAT_RENAME_NAME
from ..store import db
from ..text import grp_label, ikb, rtl, safe_edit
from ..timeutil import now_ts
from ..screen import render

# =========================
# Categories management
# =========================
async def cat_rename_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    new_name = (update.message.text or "").strip()
    if not new_name:
        await render(update, context, rtl("نام خالی است. دوباره وارد کنید:"))
        return CAT_RENAME_NAME

    cid = context.user_data.get("rename_cat_id")
    grp = context.user_data.get("rename_cat_grp")
    old_name = context.user_data.get("rename_old_name")

    scope, owner = resolve_scope_owner(user.id)

    async with DB_LOCK:
        with db() as conn:
            try:
                conn.execute(
                    "UPDATE categories SET name=? WHERE id=? AND scope=? AND owner_user_id=?",
                    (new_name, cid, scope, owner),
                )

                conn.execute(
                    """
                    UPDATE transactions
                    SET category=?, updated_at=?
                    WHERE scope=? AND owner_user_id=? AND ttype=? AND category=?
                    """,
                    (new_name, now_ts(), scope, owner, grp, old_name),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                await render(update, context, rtl("❌ این نام قبلاً وجود دارد."))
                return CAT_RENAME_NAME

    await render(update, context, 
        rtl(f"✅ ویرایش شد.\n\n🧩 {grp_label(grp)}"),
        reply_markup=build_cat_kb(scope, owner, grp),
    )

    context.user_data.clear()
    return ConversationHandler.END

async def cats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    if act == "grp":
        grp = parts[2]
        context.user_data.clear()
        context.user_data["cat_grp"] = grp
        await safe_edit(q, rtl(f"🧩 {grp_label(grp)}"), reply_markup=build_cat_kb(scope, owner, grp))
        return ConversationHandler.END

    if act == "add":
        grp = parts[2]
        context.user_data.clear()
        context.user_data["cat_grp"] = grp
        await safe_edit(q, rtl(f"نام دسته جدید برای «{grp_label(grp)}» را وارد کنید:"))
        return CAT_ADD_NAME

    if act == "page":
        grp = parts[2]
        try:
            page = int(parts[3])
        except (IndexError, ValueError):
            page = 0
        await safe_edit(q,
            rtl(f"🧩 {grp_label(grp)}"),
            reply_markup=build_cat_kb(scope, owner, grp, page),
        )
        return ConversationHandler.END

    if act in ("del", "delok"):
        cid = int(parts[2])
        with db() as conn:
            row = conn.execute(
                "SELECT grp, name, is_locked FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cid, scope, owner),
            ).fetchone()

        if not row:
            await safe_edit(q, rtl("پیدا نشد."), reply_markup=cats_root_menu())
            return ConversationHandler.END

        grp = row["grp"]
        if grp == "personal_out" and row["name"] == INSTALLMENT_NAME and int(row["is_locked"]) == 1:
            await safe_edit(q,
                rtl("⛔ دسته «قسط» قفل است و حذف نمی‌شود."),
                reply_markup=build_cat_kb(scope, owner, grp),
            )
            return ConversationHandler.END

        if act == "del":
            with db() as conn:
                used = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM transactions
                    WHERE scope=? AND owner_user_id=? AND ttype=? AND category=?
                    """,
                    (scope, owner, grp, row["name"]),
                ).fetchone()

            lines = [
                "⚠️ حذف دسته",
                "",
                f"🏷 نام: {row['name']}",
                f"🧩 گروه: {grp_label(grp)}",
            ]
            if int(used["c"]):
                # Transactions keep the category name as text, so they survive.
                lines += [
                    "",
                    f"ℹ️ {int(used['c'])} تراکنش با این دسته ثبت شده است.",
                    "تراکنش‌ها حذف نمی‌شوند و نامشان همین می‌ماند.",
                ]
            lines += ["", "آیا مطمئنی؟"]

            kb = ikb(
                [
                    [("🗑 بله، حذف کن", f"{CB_CT}:delok:{cid}")],
                    [("↩️ انصراف", f"{CB_CT}:grp:{grp}")],
                ]
            )
            await safe_edit(q, rtl("\n".join(lines)), reply_markup=kb)
            return ConversationHandler.END

        async with DB_LOCK:
            with db() as conn:
                conn.execute(
                    "DELETE FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                    (cid, scope, owner),
                )
                conn.commit()

        await safe_edit(q,
            rtl(f"✅ حذف شد.\n\n🧩 {grp_label(grp)}"),
            reply_markup=build_cat_kb(scope, owner, grp),
        )
        return ConversationHandler.END

    if act == "ren":
        cid = int(parts[2])

        with db() as conn:
            row = conn.execute(
                "SELECT grp, name, is_locked FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cid, scope, owner),
            ).fetchone()

        if not row:
            await safe_edit(q, rtl("پیدا نشد."))
            return ConversationHandler.END

        if row["grp"] == "personal_out" and row["name"] == INSTALLMENT_NAME and int(row["is_locked"]) == 1:
            await safe_edit(q, rtl("⛔ دسته «قسط» قفل است و ویرایش نمی‌شود."))
            return ConversationHandler.END

        context.user_data.clear()
        context.user_data["rename_cat_id"] = cid
        context.user_data["rename_cat_grp"] = row["grp"]
        context.user_data["rename_old_name"] = row["name"]

        await safe_edit(q, rtl(f"✏️ نام جدید برای دسته «{row['name']}» را وارد کنید:"))
        return CAT_RENAME_NAME

    await safe_edit(q, rtl("دستور ناشناخته."))
    return ConversationHandler.END

async def cat_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await render(update, context, rtl("نام خالی است. دوباره وارد کنید:"))
        return CAT_ADD_NAME

    grp = context.user_data.get("cat_grp")
    if grp not in ("work_in", "work_out", "personal_in", "personal_out"):
        await render(update, context, rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)

    ok, why = within_quota(scope, owner, "cat")
    if not ok:
        await render(update, context, rtl(f"⛔ {why}"))
        context.user_data.clear()
        return ConversationHandler.END

    ensure_installment(scope, owner)

    async with DB_LOCK:
        with db() as conn:
            try:
                conn.execute(
                    "INSERT INTO categories(scope, owner_user_id, grp, name, is_locked) VALUES(?,?,?,?,0)",
                    (scope, owner, grp, name),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass

    await render(update, context, 
        rtl(f"✅ اضافه شد.\n\n🧩 {grp_label(grp)}"),
        reply_markup=build_cat_kb(scope, owner, grp),
    )
    context.user_data.clear()
    return ConversationHandler.END
