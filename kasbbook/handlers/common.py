"""Start, cancel, top-level menus and the global error handler."""

import traceback
from telegram import BotCommand, Update
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import Application, ContextTypes, ConversationHandler
from typing import List

from ..access import access_allowed, deny, is_primary_admin
from ..backups import db_menu_kb, db_menu_text
from ..config import ACCESS_ADMIN_ONLY, ACCESS_PUBLIC, PRIMARY_ADMIN_USER_ID, logger
from .reports import report_root
from ..menus import access_menu, cats_root_menu, main_menu, settings_menu, start_text, tx_menu
from ..money import currency, currency_kb
from ..store import get_setting, set_setting
from ..text import rtl, safe_edit
from ..screen import clear_reply_keyboard, render, reset_screen, single_message_on

# =========================
# Commands setup
# =========================
async def setup_commands(app: Application) -> None:
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "شروع ربات"),
                BotCommand("cancel", "لغو عملیات جاری"),
            ]
        )
    except Exception as e:
        logger.warning("Failed to set bot commands: %s", e)

# =========================
# /start
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await clear_reply_keyboard(update, context)

    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return

    # /start is the reset button: retire the old panel and open a fresh one.
    await reset_screen(update, context)
    await render(update, context, rtl(start_text()), reply_markup=main_menu())

# =========================
# Main callbacks
# =========================
async def main_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    action = (q.data or "").split(":")[1]
    if action == "noop":
        # Inert label button (page counters, section headers).
        return
    if action == "home":
        await safe_edit(q, rtl(start_text()), reply_markup=main_menu())
        return
    if action == "tx":
        await safe_edit(q, rtl("📌 تراکنش‌ها:"), reply_markup=tx_menu())
        return
    if action == "st":
        await safe_edit(q, rtl("⚙️ تنظیمات:"), reply_markup=settings_menu(user.id))
        return
    if action == "report":
        await report_root(update, context, edit=True)
        return

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=main_menu())

# =========================
# Settings callbacks
# =========================
async def settings_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    action = (q.data or "").split(":")[1]
    if action == "cats":
        await safe_edit(q, rtl("🧩 مدیریت دسته‌ها:"), reply_markup=cats_root_menu())
        return
    if action == "access":
        if not is_primary_admin(user.id):
            await safe_edit(q, rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
            return
        await safe_edit(q, rtl("🔐 دسترسی ربات:"), reply_markup=access_menu(user.id))
        return
    if action == "single":
        set_setting("single_message", "0" if single_message_on() else "1")
        await render(update, context, rtl("⚙️ تنظیمات:"), reply_markup=settings_menu(user.id))
        return

    if action == "cur":
        await safe_edit(q, rtl(f"💱 واحد پول\n\nواحد فعلی: {currency()}"), reply_markup=currency_kb())
        return
    if action == "db":
        if not is_primary_admin(user.id):
            await safe_edit(q, rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
            return
        await safe_edit(q, rtl(db_menu_text()), reply_markup=db_menu_kb())
        return

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=settings_menu(user.id))

async def access_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    if not is_primary_admin(user.id):
        await safe_edit(q, rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return

    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "mode":
        mode = parts[2]
        if mode not in (ACCESS_ADMIN_ONLY, ACCESS_PUBLIC):
            await safe_edit(q, rtl("حالت نامعتبر."), reply_markup=access_menu(user.id))
            return
        set_setting("access_mode", mode)
        await safe_edit(q, rtl("✅ انجام شد."), reply_markup=access_menu(user.id))
        return

    if act == "share":
        if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
            await safe_edit(q, rtl("این گزینه فقط در حالت ادمین فعال است."), reply_markup=access_menu(user.id))
            return
        cur = get_setting("share_enabled")
        set_setting("share_enabled", "0" if cur == "1" else "1")
        await safe_edit(q, rtl("✅ انجام شد."), reply_markup=access_menu(user.id))
        return

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=access_menu(user.id))

# =========================
# Cancel / error handling
# =========================
async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Escape hatch out of any conversation."""
    context.user_data.clear()
    if not access_allowed(update.effective_user.id):
        await deny(update)
        return ConversationHandler.END

    await render(update, context, rtl("↩️ لغو شد."), reply_markup=main_menu())
    return ConversationHandler.END

# Repeated identical failures should not spam the admin's chat.
_LAST_ERROR_SIG: List[str] = []

# A long-polling bot loses its connection now and then: the peer resets, the
# network blips, a read times out. PTB retries on its own, so these are noise,
# not incidents — they get logged but never paged to the admin.
_TRANSIENT_BY_NAME = {
    "ReadError", "WriteError", "ConnectError", "ConnectTimeout",
    "ReadTimeout", "WriteTimeout", "PoolTimeout", "RemoteProtocolError",
}

def is_transient_network_error(err: object) -> bool:
    # BadRequest and TimedOut both subclass NetworkError in PTB, so an isinstance
    # check against NetworkError would swallow real API rejections too. Only a
    # bare NetworkError means "the connection misbehaved".
    if type(err) is NetworkError or isinstance(err, TimedOut):
        return True
    # httpx/httpcore failures share no base class with telegram's, so the
    # class name is the only thing they reliably have in common.
    seen = set()
    while err is not None and id(err) not in seen:
        seen.add(id(err))
        if type(err).__name__ in _TRANSIENT_BY_NAME:
            return True
        err = getattr(err, "__cause__", None) or getattr(err, "__context__", None)
    return False

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error

    # Re-pressing a button that produces the same screen is not an error.
    if isinstance(err, BadRequest) and "not modified" in str(err).lower():
        return

    # Connection hiccups are expected and self-healing; log and move on.
    if is_transient_network_error(err):
        logger.warning("Transient network error: %s: %s", type(err).__name__, err)
        return

    logger.error("Unhandled error while processing update", exc_info=err)

    if isinstance(update, Update):
        try:
            if update.callback_query:
                await update.callback_query.answer("خطایی رخ داد. دوباره تلاش کنید.", show_alert=True)
            elif update.effective_chat:
                await render(update, context, 
                    rtl("❌ خطایی رخ داد. با /start دوباره شروع کنید.")
                )
        except Exception:
            pass

    sig = f"{type(err).__name__}: {err}"
    if _LAST_ERROR_SIG and _LAST_ERROR_SIG[0] == sig:
        return
    _LAST_ERROR_SIG[:] = [sig]

    try:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        await context.bot.send_message(
            chat_id=PRIMARY_ADMIN_USER_ID,
            text=rtl(f"⚠️ خطای ربات\n\n{tb[-1200:]}"),
        )
    except Exception:
        pass

# =========================
# Unknown callback
# =========================
async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    try:
        await q.answer("دکمه نامعتبر/قدیمی است.", show_alert=False)
    except Exception:
        pass
