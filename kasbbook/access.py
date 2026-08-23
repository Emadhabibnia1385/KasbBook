"""Who may use the bot, whose books they see, and public-mode quotas."""

from telegram import Update
from typing import Optional, Tuple

from .config import ACCESS_PUBLIC, ADMIN_USERNAME, PRIMARY_ADMIN_USER_ID, PUBLIC_MAX_CATEGORIES, PUBLIC_MAX_TX_PER_DAY
from .store import db, get_setting
from .text import rtl, safe_edit
from .timeutil import today_g

def is_primary_admin(user_id: int) -> bool:
    return user_id == PRIMARY_ADMIN_USER_ID

def is_admin(user_id: int) -> bool:
    if user_id == PRIMARY_ADMIN_USER_ID:
        return True
    with db() as conn:
        return conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone() is not None

def access_allowed(user_id: int) -> bool:
    mode = get_setting("access_mode")
    if mode == ACCESS_PUBLIC:
        return True
    return is_admin(user_id)

def resolve_scope_owner(user_id: int) -> Tuple[str, int]:
    mode = get_setting("access_mode")
    if mode == ACCESS_PUBLIC:
        return ("private", user_id)

    # admin_only
    share_enabled = get_setting("share_enabled")
    if share_enabled == "1":
        return ("shared", PRIMARY_ADMIN_USER_ID)
    return ("private", user_id)

def within_quota(scope: str, owner: int, kind: str) -> Tuple[bool, str]:
    """
    Guard rails for public mode, where anyone who finds the bot can write to it.

    Admin-only mode is unrestricted: those users were added on purpose.
    """
    try:
        if get_setting("access_mode") != ACCESS_PUBLIC:
            return (True, "")
    except Exception:
        return (True, "")

    with db() as conn:
        if kind == "tx":
            used = int(conn.execute(
                "SELECT COUNT(*) AS c FROM transactions "
                "WHERE scope=? AND owner_user_id=? AND date_g=?",
                (scope, owner, today_g()),
            ).fetchone()["c"])
            if used >= PUBLIC_MAX_TX_PER_DAY:
                return (False, f"سقف روزانه {PUBLIC_MAX_TX_PER_DAY} تراکنش پر شده است.")

        elif kind == "cat":
            used = int(conn.execute(
                "SELECT COUNT(*) AS c FROM categories WHERE scope=? AND owner_user_id=?",
                (scope, owner),
            ).fetchone()["c"])
            if used >= PUBLIC_MAX_CATEGORIES:
                return (False, f"سقف {PUBLIC_MAX_CATEGORIES} دسته پر شده است.")

    return (True, "")

# =========================
# Access denied
# =========================
def denied_text(user_id: int, username: Optional[str]) -> str:
    u = (username or "").strip()
    shown = u if u else "ندارد"
    return (
        "❌ شما هنوز به عنوان فروشنده/ادمین ثبت نشده‌اید.\n\n"
        f"🆔 آیدی عددی شما: {user_id}\n"
        f"👤 یوزرنیم شما: @{shown}\n\n"
        "این پیام را برای ادمین اصلی ارسال کنید تا شما را اضافه کند.\n"
        f"ادمین اصلی: @{ADMIN_USERNAME}"
    )

async def deny(update: Update) -> None:
    user = update.effective_user
    text = denied_text(user.id, user.username)

    if update.callback_query:
        q = update.callback_query
        try:
            await q.answer()
        except Exception:
            pass
        try:
            await safe_edit(q, rtl(text))
        except Exception:
            await update.effective_chat.send_message(rtl(text))
    else:
        await update.effective_chat.send_message(rtl(text))
