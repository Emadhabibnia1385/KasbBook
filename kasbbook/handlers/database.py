"""Backup, restore, currency and reminder settings."""

import io
import os
import re
import shutil
import tempfile
from datetime import datetime
from telegram import Document, Update
from telegram.ext import ContextTypes, ConversationHandler
from typing import Optional

from ..access import access_allowed, deny, guarded, is_primary_admin
from ..backups import db_menu_kb, db_menu_text, db_target_kb, schedule_backup_job
from ..config import ADMIN_CHAT_ID, DB_LOCK, DB_PATH, TZ, logger
from ..menus import settings_menu
from ..money import currency, currency_kb
from ..parsing import to_ascii_digits
from ..reminders import reminders_kb, reminders_text
from ..states import CU_CUSTOM, DB_RESTORE_WAIT_DOC, DB_SET_INTERVAL, DB_SET_TARGET_ID, RM_DAYS, RM_HOUR
from ..store import backup_filename, drop_sidecars, get_setting, init_db, make_backup_bytes, save_disk_backup, set_setting, validate_backup_file
from ..text import rtl, safe_edit
from ..screen import render

async def db_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    این handler فقط:
    open / backup_now / toggle / target (منو) را هندل می‌کند.
    interval/restore/target:chat|channel داخل Conversation های جدا هستند (بدون تداخل).
    """
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    if not is_primary_admin(user.id):
        await safe_edit(q, rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    act = parts[1] if len(parts) > 1 else ""

    if act == "open":
        await safe_edit(q, rtl(db_menu_text()), reply_markup=db_menu_kb())
        return ConversationHandler.END

    if act == "backup_now":
        fname = backup_filename()
        await safe_edit(q, rtl("در حال ارسال بکاپ..."), reply_markup=db_menu_kb())

        async with DB_LOCK:
            data = make_backup_bytes()

        bio = io.BytesIO(data)
        bio.name = fname

        await context.bot.send_document(
            chat_id=user.id,
            document=bio,
            filename=fname,
            caption=rtl(f"🗄 بکاپ دیتابیس\n\n📦 {fname}"),
        )
        await safe_edit(q, rtl(db_menu_text()), reply_markup=db_menu_kb())
        return ConversationHandler.END

    if act == "toggle":
        cur = get_setting("backup_enabled")
        set_setting("backup_enabled", "0" if cur == "1" else "1")
        schedule_backup_job(context.application)
        await safe_edit(q, rtl(db_menu_text()), reply_markup=db_menu_kb())
        return ConversationHandler.END

    if act == "target":
        await safe_edit(q,
            rtl(
                "📍 مقصد بکاپ\n\n"
                "یکی از گزینه‌ها را انتخاب کنید:\n"
                "• ارسال به آیدی: آیدی عددی چت/گروه\n"
                "• ارسال به کانال: آیدی عددی کانال (مثل -100...)\n\n"
                "ℹ️ اگر کانال انتخاب می‌کنی، ربات باید داخل کانال ادمین/دارای اجازه ارسال باشد."
            ),
            reply_markup=db_target_kb(),
        )
        return ConversationHandler.END

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=db_menu_kb())
    return ConversationHandler.END

async def db_target_choice_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    if not is_primary_admin(user.id):
        await safe_edit(q, rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    target_type = parts[2]  # chat/channel

    if target_type == "chat":
        set_setting("backup_target_type", "chat")
        context.user_data.clear()
        context.user_data["db_target_type"] = "chat"
        await safe_edit(q,
            rtl(
                "👤 ارسال بکاپ به آیدی\n\n"
                f"آیدی عددی مقصد را وارد کنید.\n"
                f"اگر /skip بزنید → پیش‌فرض: {ADMIN_CHAT_ID}"
            )
        )
        return DB_SET_TARGET_ID

    if target_type == "channel":
        set_setting("backup_target_type", "channel")
        context.user_data.clear()
        context.user_data["db_target_type"] = "channel"
        await safe_edit(q,
            rtl(
                "📣 ارسال بکاپ به کانال\n\n"
                "آیدی عددی کانال را وارد کنید (مثل -1001234567890).\n\n"
                "⚠️ ربات باید در کانال اجازه ارسال داشته باشد."
            )
        )
        return DB_SET_TARGET_ID

    await safe_edit(q, rtl("گزینه نامعتبر."), reply_markup=db_menu_kb())
    return ConversationHandler.END

async def db_set_target_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    if not is_primary_admin(user.id):
        await render(update, context, rtl("⛔ فقط ادمین اصلی."))
        context.user_data.clear()
        return ConversationHandler.END

    text = (update.message.text or "").strip()

    if text.startswith("/skip"):
        set_setting("backup_target_id", str(ADMIN_CHAT_ID))
        await render(update, context, rtl("✅ مقصد روی آیدی پیش‌فرض ادمین اصلی تنظیم شد."))
    else:
        if not re.fullmatch(r"-?\d+", text):
            await render(update, context, rtl("❌ فقط آیدی عددی وارد کنید (مثلاً 123 یا -100...)."))
            return DB_SET_TARGET_ID
        set_setting("backup_target_id", text)
        await render(update, context, rtl("✅ مقصد بکاپ ثبت شد."))

    schedule_backup_job(context.application)
    await render(update, context, rtl(db_menu_text()), reply_markup=db_menu_kb())
    context.user_data.clear()
    return ConversationHandler.END

async def db_interval_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    if not is_primary_admin(user.id):
        await safe_edit(q, rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return ConversationHandler.END

    context.user_data.clear()
    await safe_edit(q, rtl("⏱ عدد فاصله بکاپ خودکار را به ساعت وارد کنید (مثلاً 1):"))
    return DB_SET_INTERVAL

async def db_set_interval_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    if not is_primary_admin(user.id):
        await render(update, context, rtl("⛔ فقط ادمین اصلی."))
        context.user_data.clear()
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if not re.fullmatch(r"\d+", t):
        await render(update, context, rtl("❌ فقط عدد وارد کنید (ساعت):"))
        return DB_SET_INTERVAL

    hours = max(1, int(t))
    set_setting("backup_interval_hours", str(hours))
    schedule_backup_job(context.application)
    await render(update, context,
        rtl("✅ فاصله بکاپ خودکار ثبت شد.\n\n" + db_menu_text()),
        reply_markup=db_menu_kb(),
    )
    context.user_data.clear()
    return ConversationHandler.END

async def db_restore_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    if not is_primary_admin(user.id):
        await safe_edit(q, rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return ConversationHandler.END

    context.user_data.clear()
    await safe_edit(q,
        rtl(
            "📤 فایل بکاپ با پسوند .db را ارسال کنید.\n\n"
            "ℹ️ فایل قبل از جایگزینی بررسی می‌شود و از دیتابیس فعلی بکاپ اضطراری گرفته می‌شود.\n"
            "برای انصراف /cancel بزنید."
        )
    )
    return DB_RESTORE_WAIT_DOC

async def db_restore_wait_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    if not is_primary_admin(user.id):
        await render(update, context, rtl("⛔ فقط ادمین اصلی."))
        return ConversationHandler.END

    msg = update.message
    if not msg or not msg.document:
        await render(update, context, rtl("❌ لطفاً یک فایل .db ارسال کنید."))
        return DB_RESTORE_WAIT_DOC

    doc: Document = msg.document
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".db"):
        await render(update, context, rtl("❌ فقط فایل با پسوند .db قابل قبول است."))
        return DB_RESTORE_WAIT_DOC

    file = await context.bot.get_file(doc.file_id)
    fd, tmp_in = tempfile.mkstemp(prefix="kasbbook_restore_", suffix=".db")
    os.close(fd)
    await file.download_to_drive(custom_path=tmp_in)

    # 1) Validate BEFORE touching the live database.
    ok, why = validate_backup_file(tmp_in)
    if not ok:
        try:
            os.remove(tmp_in)
        except OSError:
            pass
        await render(update, context, 
            rtl(f"❌ این فایل پذیرفته نشد.\n\n{why}\n\nیک فایل بکاپ معتبر بفرستید یا /cancel بزنید.")
        )
        return DB_RESTORE_WAIT_DOC

    # 2) Snapshot the current DB, on disk *and* to Telegram.
    stamp = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
    emergency_name = f"kasbbook_emergency_{stamp}.db"
    rollback_path: Optional[str] = None
    try:
        async with DB_LOCK:
            data = make_backup_bytes()
        rollback_path = save_disk_backup(emergency_name, data)

        bio = io.BytesIO(data)
        bio.name = emergency_name
        await context.bot.send_document(
            chat_id=user.id,
            document=bio,
            filename=emergency_name,
            caption=rtl(f"🧯 بکاپ اضطراری قبل از ریستور\n\n📦 {emergency_name}"),
        )
    except Exception as e:
        logger.warning("Failed to take emergency backup: %s", e)

    if not rollback_path:
        await render(update, context, 
            rtl("⚠️ نتوانستم بکاپ اضطراری روی دیسک بگیرم. ریستور انجام نشد.")
        )
        try:
            os.remove(tmp_in)
        except OSError:
            pass
        return ConversationHandler.END

    # 3) Swap the file. Stale -wal/-shm belong to the OLD database and must go.
    restored = False
    rolled_back = False
    async with DB_LOCK:
        try:
            drop_sidecars()
            shutil.move(tmp_in, DB_PATH)
            init_db()
            restored = True
        except Exception as e:
            logger.exception("Restore failed, rolling back: %s", e)
            try:
                drop_sidecars()
                shutil.copyfile(rollback_path, DB_PATH)
                init_db()
                rolled_back = True
            except Exception as e2:
                logger.exception("Rollback failed too: %s", e2)
                rolled_back = False

    if not restored:
        msg = "❌ ریستور ناموفق بود."
        if rolled_back:
            msg += "\n\n✅ دیتابیس قبلی برگردانده شد؛ اطلاعاتت سر جایش است."
        else:
            msg += (
                f"\n\n⚠️ بازگردانی خودکار هم شکست خورد."
                f"\nنسخه سالم اینجاست: {rollback_path}"
            )
        await render(update, context, rtl(msg))
        return ConversationHandler.END

    await render(update, context, 
        rtl(f"✅ بکاپ با موفقیت وارد شد.\n\n🧯 نسخه قبلی: {rollback_path}")
    )

    schedule_backup_job(context.application)
    await render(update, context, rtl(db_menu_text()), reply_markup=db_menu_kb())
    return ConversationHandler.END

# =========================
# Currency handlers
# =========================
async def currency_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")

    if parts[1] == "custom":
        context.user_data.clear()
        await safe_edit(q, rtl("✏️ واحد پول دلخواه را بنویس (مثلاً: درهم):"))
        return CU_CUSTOM

    if parts[1] == "set":
        set_setting("currency", parts[2])
        await safe_edit(q, rtl(f"💱 واحد پول\n\nواحد فعلی: {currency()}"), reply_markup=currency_kb())
        return ConversationHandler.END

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=currency_kb())
    return ConversationHandler.END

async def currency_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name or len(name) > 12:
        await render(update, context, rtl("❌ یک واحد کوتاه بنویس (حداکثر ۱۲ نویسه):"))
        return CU_CUSTOM

    set_setting("currency", name)
    context.user_data.clear()
    await render(update, context, 
        rtl(f"💱 واحد پول\n\nواحد فعلی: {currency()}"), reply_markup=currency_kb()
    )
    return ConversationHandler.END

# =========================
# Reminder handlers
# =========================
async def reminders_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "tog":
        key = "digest_enabled" if parts[2] == "digest" else "loan_reminder_enabled"
        set_setting(key, "0" if get_setting(key) == "1" else "1")
        await safe_edit(q, rtl(reminders_text()), reply_markup=reminders_kb())
        return ConversationHandler.END

    if act == "hour":
        await safe_edit(q, rtl("🕘 ساعت ارسال خلاصهٔ روزانه را بنویس (۰ تا ۲۳):"))
        return RM_HOUR

    if act == "days":
        await safe_edit(q, rtl("⏳ چند روز قبل از سررسید قسط خبر بدهم؟"))
        return RM_DAYS

    await safe_edit(q, rtl(reminders_text()), reply_markup=reminders_kb())
    return ConversationHandler.END

@guarded
async def reminder_hour_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = to_ascii_digits(update.message.text or "").strip()
    if not re.fullmatch(r"\d{1,2}", raw) or int(raw) > 23:
        await render(update, context, rtl("❌ عددی بین ۰ تا ۲۳ بنویس:"))
        return RM_HOUR

    set_setting("digest_hour", str(int(raw)))
    await render(update, context, rtl(reminders_text()), reply_markup=reminders_kb())
    return ConversationHandler.END

@guarded
async def reminder_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = to_ascii_digits(update.message.text or "").strip()
    if not re.fullmatch(r"\d{1,2}", raw):
        await render(update, context, rtl("❌ فقط عدد بنویس:"))
        return RM_DAYS

    set_setting("loan_reminder_days", str(int(raw)))
    await render(update, context, rtl(reminders_text()), reply_markup=reminders_kb())
    return ConversationHandler.END
