"""Backup delivery to Telegram and the database menu."""

import io
from telegram import InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

from .config import ADMIN_CHAT_ID, CB_DB, CB_M, CB_ST, DB_LOCK, JOB_BACKUP, logger
from .store import backup_filename, get_setting, make_backup_bytes
from .text import ikb, rtl

# =========================
# Database / Backup / Restore
# =========================
def db_menu_text() -> str:
    enabled = get_setting("backup_enabled") == "1"
    ttype = get_setting("backup_target_type")
    tid = get_setting("backup_target_id")
    try:
        hours = int(get_setting("backup_interval_hours"))
    except Exception:
        hours = 1

    dest = "آیدی" if ttype == "chat" else "کانال"
    onoff = "روشن ✅" if enabled else "خاموش ❌"
    return (
        "🗄 دیتابیس\n\n"
        f"🕒 بکاپ خودکار: {onoff}\n"
        f"📍 مقصد بکاپ: {dest}\n"
        f"🆔 مقصد فعلی: {tid}\n"
        f"⏱ هر چند ساعت: {hours}\n"
    )

def db_menu_kb() -> InlineKeyboardMarkup:
    enabled = get_setting("backup_enabled") == "1"
    onoff = "روشن ✅" if enabled else "خاموش ❌"
    return ikb(
        [
            [("📥 گرفتن بکاپ (الان)", f"{CB_DB}:backup_now")],
            [("📤 وارد کردن بکاپ", f"{CB_DB}:restore")],
            [(f"🕒 بکاپ خودکار: {onoff}", f"{CB_DB}:toggle")],
            [("📍 مقصد بکاپ", f"{CB_DB}:target")],
            [("⏱ هر چند ساعت", f"{CB_DB}:interval")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )

def db_target_kb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("👤 ارسال بکاپ به یک آیدی", f"{CB_DB}:target:chat")],
            [("📣 ارسال بکاپ به کانال", f"{CB_DB}:target:channel")],
            [("⬅️ بازگشت", f"{CB_ST}:db")],
        ]
    )

async def send_backup_file(context: ContextTypes.DEFAULT_TYPE) -> None:
    enabled = get_setting("backup_enabled") == "1"
    if not enabled:
        return

    tid = get_setting("backup_target_id")
    try:
        target_id = int(tid)
    except Exception:
        target_id = ADMIN_CHAT_ID

    fname = backup_filename()

    async with DB_LOCK:
        data = make_backup_bytes()

    bio = io.BytesIO(data)
    bio.name = fname

    caption = rtl(f"🗄 بکاپ دیتابیس\n\n📦 {fname}")
    try:
        await context.bot.send_document(
            chat_id=target_id,
            document=bio,
            filename=fname,
            caption=caption,
        )
    except Exception as e:
        logger.warning("Auto-backup send failed: %s", e)

async def backup_job(ctx):
    await send_backup_file(ctx)

def schedule_backup_job(app: Application) -> None:
    try:
        for j in app.job_queue.get_jobs_by_name(JOB_BACKUP):
            j.schedule_removal()
    except Exception:
        pass

    if get_setting("backup_enabled") != "1":
        return

    try:
        hours = int(get_setting("backup_interval_hours"))
        if hours <= 0:
            hours = 1
    except Exception:
        hours = 1

    seconds = hours * 3600
    app.job_queue.run_repeating(
        callback=backup_job,
        interval=seconds,
        first=seconds,
        name=JOB_BACKUP,
    )
