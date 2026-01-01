#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# --- Optional Jalali support ---
try:
    import jdatetime  # pip install jdatetime
except Exception:
    jdatetime = None

# بارگذاری متغیرهای محیطی
load_dotenv()

# تنظیم لاگینگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن ربات و آیدی ادمین
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0").strip() or "0")

# نام دیتابیس
DB_NAME = "KasbBook.db"

# States
(
    SELECT_DATE,
    SELECT_CATEGORY,
    ENTER_AMOUNT,
    ENTER_DESCRIPTION,
    ADD_CATEGORY_NAME,

    ADD_ADMIN_ID,
    ADD_ADMIN_NAME,

    BACKUP_INTERVAL,
    BACKUP_DEST,
    UPLOAD_BACKUP_FILE,

    EDIT_AMOUNT,
    EDIT_DESC,
    EDIT_CATEGORY,
) = range(13)


# ---------------- DB Helpers ----------------
def db_connect():
    return sqlite3.connect(DB_NAME)


def init_db():
    """ساخت جداول دیتابیس و رکورد تنظیمات اولیه ادمین"""
    conn = db_connect()
    c = conn.cursor()

    # جدول تراکنش‌ها
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL,
            description TEXT,
            date TEXT NOT NULL,               -- YYYY-MM-DD (Gregorian)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # جدول دسته‌ها
    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_group TEXT NOT NULL,     -- income | expense | personal_expense
            category_name TEXT NOT NULL,
            is_locked INTEGER DEFAULT 0,
            UNIQUE(user_id, category_group, category_name)
        )
    """)

    # جدول تنظیمات
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER PRIMARY KEY,
            access_mode TEXT DEFAULT 'private',   -- private | admins | public
            shared_data INTEGER DEFAULT 0,
            auto_backup INTEGER DEFAULT 0,
            backup_interval INTEGER DEFAULT 24,
            backup_destination INTEGER
        )
    """)

    # جدول ادمین‌ها
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL UNIQUE,
            admin_name TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

    # رکورد تنظیمات برای ادمین اصلی
    if ADMIN_CHAT_ID:
        conn = db_connect()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO settings (user_id, backup_destination)
            VALUES (?, ?)
        """, (ADMIN_CHAT_ID, ADMIN_CHAT_ID))
        conn.commit()
        conn.close()

        # افزودن دسته قسط (قفل شده)
        add_default_installment_category()


def add_default_installment_category():
    """افزودن دسته قسط به خروجی شخصی ادمین (قفل شده)"""
    conn = db_connect()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO categories (user_id, category_group, category_name, is_locked)
            VALUES (?, ?, ?, ?)
        """, (ADMIN_CHAT_ID, "personal_expense", "قسط", 1))
        conn.commit()
    finally:
        conn.close()


def format_amount(amount: int) -> str:
    return f"{amount:,} تومان"


# ---------------- Access & Scope ----------------
def get_user_scope(user_id: int) -> int:
    """اگر shared روشن و کاربر ادمین باشد، داده‌ها در اسکوپ ادمین اصلی ذخیره/خوانده شوند"""
    if user_id == ADMIN_CHAT_ID:
        return ADMIN_CHAT_ID

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT access_mode, shared_data FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
    row = c.fetchone()
    conn.close()

    if not row:
        return user_id

    access_mode, shared_data = row

    if access_mode == "admins" and shared_data == 1:
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins WHERE admin_id = ?", (user_id,))
        is_admin = c.fetchone()
        conn.close()
        if is_admin:
            return ADMIN_CHAT_ID

    return user_id


def check_access(user_id: int) -> bool:
    if user_id == ADMIN_CHAT_ID:
        return True

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT access_mode FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False

    access_mode = row[0]

    if access_mode == "public":
        conn.close()
        return True

    if access_mode == "admins":
        c.execute("SELECT admin_id FROM admins WHERE admin_id = ?", (user_id,))
        is_admin = c.fetchone()
        conn.close()
        return is_admin is not None

    conn.close()
    return False


# ---------------- Date helpers ----------------
def today_gregorian() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def validate_gregorian(date_text: str) -> bool:
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def jalali_to_gregorian(date_text: str) -> str | None:
    """1403-02-25 -> 2024-05-14"""
    if not jdatetime:
        return None
    try:
        jy, jm, jd = map(int, date_text.split("-"))
        g = jdatetime.date(jy, jm, jd).togregorian()
        return g.strftime("%Y-%m-%d")
    except Exception:
        return None


# ---------------- UI Menus ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not check_access(user_id):
        await update.message.reply_text(
            "⛔️ متأسفانه شما به این ربات دسترسی ندارید.\n"
            "لطفاً با مدیر ربات تماس بگیرید. 🙏"
        )
        return

    # ساخت تنظیمات پیش‌فرض برای کاربر
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO settings (user_id, backup_destination) VALUES (?, ?)", (user_id, user_id))
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("📌 تراکنش‌ها", callback_data="menu_transactions")],
        [InlineKeyboardButton("📊 گزارش‌ها", callback_data="menu_reports")],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu_settings")]
    ]
    await update.message.reply_text(
        "✨ به ربات KasbBook خوش آمدید! ✨\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📌 تراکنش‌ها", callback_data="menu_transactions")],
        [InlineKeyboardButton("📊 گزارش‌ها", callback_data="menu_reports")],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu_settings")]
    ]
    await query.edit_message_text(
        "🏠 منوی اصلی\n\nلطفاً یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def menu_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📅 امروز", callback_data="date_today")],
        [InlineKeyboardButton("📆 تاریخ میلادی", callback_data="date_gregorian")],
        [InlineKeyboardButton("🗓 تاریخ شمسی", callback_data="date_jalali")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]
    ]
    await query.edit_message_text(
        "📌 تراکنش‌ها\n\nلطفاً تاریخ مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------- Date selection conversation ----------------
async def select_date_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["selected_date"] = today_gregorian()
    await show_day_page(update, context)


async def request_gregorian_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📆 لطفاً تاریخ میلادی را به فرمت YYYY-MM-DD وارد کنید:\n"
        "مثال: 2024-03-15\n\n"
        "برای لغو /cancel را بزنید."
    )
    context.user_data["date_mode"] = "gregorian"
    return SELECT_DATE


async def request_jalali_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not jdatetime:
        await query.edit_message_text(
            "🗓 قابلیت تاریخ شمسی فعال نیست چون کتابخانه jdatetime نصب نیست.\n\n"
            "روی سرور این دستور را بزن:\n"
            "pip install jdatetime\n\n"
            "بعد دوباره /start"
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "🗓 لطفاً تاریخ شمسی را به فرمت YYYY-MM-DD وارد کنید:\n"
        "مثال: 1403-02-25\n\n"
        "برای لغو /cancel را بزنید."
    )
    context.user_data["date_mode"] = "jalali"
    return SELECT_DATE


async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    mode = context.user_data.get("date_mode", "gregorian")

    if mode == "gregorian":
        if not validate_gregorian(date_text):
            await update.message.reply_text("❌ فرمت تاریخ نادرست است! مثال: 2024-03-15")
            return SELECT_DATE
        context.user_data["selected_date"] = date_text
        await show_day_page(update, context)
        return ConversationHandler.END

    # jalali
    g = jalali_to_gregorian(date_text)
    if not g:
        await update.message.reply_text("❌ تاریخ شمسی نامعتبر است! مثال: 1403-02-25")
        return SELECT_DATE

    context.user_data["selected_date"] = g
    await show_day_page(update, context)
    return ConversationHandler.END


# ---------------- Day page & transactions ----------------
async def show_day_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    selected_date = context.user_data.get("selected_date") or today_gregorian()

    conn = db_connect()
    c = conn.cursor()
    c.execute("""
        SELECT id, transaction_type, category, amount
        FROM transactions
        WHERE user_id = ? AND date = ?
        ORDER BY created_at
    """, (user_scope, selected_date))
    transactions = c.fetchall()
    conn.close()

    income_trans = [t for t in transactions if t[1] == "income"]
    expense_trans = [t for t in transactions if t[1] == "expense"]
    personal_trans = [t for t in transactions if t[1] == "personal_expense"]

    keyboard = []
    keyboard.append([InlineKeyboardButton("— 💼 ورودی —", callback_data="header_income")])
    for tid, _, cat, amt in income_trans:
        keyboard.append([
            InlineKeyboardButton(f"{cat}", callback_data=f"view_trans_{tid}"),
            InlineKeyboardButton(f"{amt:,}", callback_data=f"view_trans_{tid}")
        ])

    keyboard.append([InlineKeyboardButton("— 🧾 خروجی —", callback_data="header_expense")])
    for tid, _, cat, amt in expense_trans:
        keyboard.append([
            InlineKeyboardButton(f"{cat}", callback_data=f"view_trans_{tid}"),
            InlineKeyboardButton(f"{amt:,}", callback_data=f"view_trans_{tid}")
        ])

    keyboard.append([InlineKeyboardButton("— 👤 خروجی شخصی —", callback_data="header_personal")])
    for tid, _, cat, amt in personal_trans:
        keyboard.append([
            InlineKeyboardButton(f"{cat}", callback_data=f"view_trans_{tid}"),
            InlineKeyboardButton(f"{amt:,}", callback_data=f"view_trans_{tid}")
        ])

    keyboard.append([
        InlineKeyboardButton("➕ ورودی", callback_data="add_income"),
        InlineKeyboardButton("➖ خروجی", callback_data="add_expense"),
    ])
    keyboard.append([InlineKeyboardButton("👤 شخصی", callback_data="add_personal")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_transactions")])

    text = f"📅 تراکنش‌های روز {selected_date}\n\n"
    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


async def view_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    trans_id = int(query.data.split("_")[2])

    conn = db_connect()
    c = conn.cursor()
    c.execute("""
        SELECT transaction_type, category, amount, description, date
        FROM transactions WHERE id = ?
    """, (trans_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        await query.edit_message_text("❌ تراکنش یافت نشد!")
        return

    ttype, category, amount, desc, date = row

    type_emoji = "💼" if ttype == "income" else "🧾" if ttype == "expense" else "👤"
    type_name = "ورودی" if ttype == "income" else "خروجی" if ttype == "expense" else "خروجی شخصی"

    text = (
        f"{type_emoji} جزئیات تراکنش\n\n"
        f"📋 نوع: {type_name}\n"
        f"🏷 دسته: {category}\n"
        f"💰 مبلغ: {format_amount(amount)}\n"
        f"📝 توضیحات: {desc or 'ندارد'}\n"
        f"📅 تاریخ: {date}"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ تغییر دسته", callback_data=f"edit_category_{trans_id}")],
        [InlineKeyboardButton("✏️ ویرایش مبلغ", callback_data=f"edit_amount_{trans_id}")],
        [InlineKeyboardButton("✏️ ویرایش توضیحات", callback_data=f"edit_desc_{trans_id}")],
        [InlineKeyboardButton("🗑 حذف", callback_data=f"delete_trans_{trans_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_day")]
    ]

    context.user_data["current_trans_id"] = trans_id
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ---------------- Add transaction conversation ----------------
async def start_add_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    trans_type = query.data.split("_")[1]  # income | expense | personal
    context.user_data["new_trans_type"] = trans_type
    await show_categories_selection(update, context, trans_type)
    return SELECT_CATEGORY


async def show_categories_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, trans_type: str):
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)

    if trans_type == "income":
        group = "income"
        type_name = "ورودی 💼"
    elif trans_type == "expense":
        group = "expense"
        type_name = "خروجی 🧾"
    else:
        group = "personal_expense"
        type_name = "خروجی شخصی 👤"

    conn = db_connect()
    c = conn.cursor()
    c.execute("""
        SELECT category_name FROM categories
        WHERE user_id = ? AND category_group = ?
        ORDER BY category_name
    """, (user_scope, group))
    cats = [r[0] for r in c.fetchall()]
    conn.close()

    keyboard = [[InlineKeyboardButton(cat, callback_data=f"selcat_{cat}")] for cat in cats]
    keyboard.append([InlineKeyboardButton("➕ افزودن نوع جدید", callback_data="add_new_category")])
    keyboard.append([InlineKeyboardButton("🔙 لغو", callback_data="back_day")])

    text = f"🏷 انتخاب دسته برای {type_name}\n\nیک دسته را انتخاب کنید:"
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category = query.data.split("_", 1)[1]
    context.user_data["new_trans_category"] = category

    await query.edit_message_text(
        "💰 مبلغ را به تومان وارد کنید:\n\n"
        "فقط عدد (بدون جداکننده)\n"
        "برای لغو /cancel"
    )
    return ENTER_AMOUNT


async def add_new_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "➕ افزودن دسته جدید\n\n"
        "نام دسته را وارد کنید:\n"
        "برای لغو /cancel"
    )
    return ADD_CATEGORY_NAME


async def receive_new_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category_name = update.message.text.strip()
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)

    trans_type = context.user_data.get("new_trans_type")
    group = "income" if trans_type == "income" else "expense" if trans_type == "expense" else "personal_expense"

    conn = db_connect()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO categories (user_id, category_group, category_name)
            VALUES (?, ?, ?)
        """, (user_scope, group, category_name))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        await update.message.reply_text("❌ این دسته قبلاً وجود دارد!")
        return ADD_CATEGORY_NAME
    conn.close()

    context.user_data["new_trans_category"] = category_name
    await update.message.reply_text("✅ دسته اضافه شد.\n\n💰 مبلغ را وارد کنید:")
    return ENTER_AMOUNT


async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError
        context.user_data["new_trans_amount"] = amount

        keyboard = [[InlineKeyboardButton("رد کردن توضیحات", callback_data="skip_desc")]]
        await update.message.reply_text(
            "📝 توضیحات (اختیاری):\n\n"
            "توضیحات را بنویس یا دکمه زیر را بزن:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ENTER_DESCRIPTION
    except ValueError:
        await update.message.reply_text("❌ مبلغ نامعتبر است. مثال: 50000")
        return ENTER_AMOUNT


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_trans_description"] = None
    await save_transaction(update, context)
    return ConversationHandler.END


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_trans_description"] = update.message.text.strip()
    await save_transaction(update, context)
    return ConversationHandler.END


async def save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)

    trans_type = context.user_data.get("new_trans_type")
    category = context.user_data.get("new_trans_category")
    amount = context.user_data.get("new_trans_amount")
    desc = context.user_data.get("new_trans_description")
    date = context.user_data.get("selected_date") or today_gregorian()

    # map personal -> personal_expense
    if trans_type == "personal":
        trans_type = "personal_expense"

    conn = db_connect()
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions (user_id, transaction_type, category, amount, description, date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_scope, trans_type, category, amount, desc, date))
    conn.commit()
    conn.close()

    emoji = "💼" if trans_type == "income" else "🧾" if trans_type == "expense" else "👤"
    msg = (
        f"✅ تراکنش ثبت شد {emoji}\n\n"
        f"🏷 دسته: {category}\n"
        f"💰 مبلغ: {format_amount(amount)}\n"
        f"📝 توضیحات: {desc or 'ندارد'}"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)

    await show_day_page(update, context)


async def delete_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    trans_id = int(query.data.split("_")[2])

    conn = db_connect()
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE id = ?", (trans_id,))
    conn.commit()
    conn.close()

    await query.edit_message_text("✅ تراکنش حذف شد.")
    await show_day_page(update, context)


# ---------------- Edit transaction conversations ----------------
async def edit_amount_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trans_id = int(query.data.split("_")[2])
    context.user_data["edit_trans_id"] = trans_id

    await query.edit_message_text("✏️ مبلغ جدید را فقط به صورت عدد وارد کنید:\nبرای لغو /cancel")
    return EDIT_AMOUNT


async def edit_amount_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مبلغ نامعتبر است. مثال: 50000")
        return EDIT_AMOUNT

    trans_id = context.user_data.get("edit_trans_id")
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE transactions SET amount = ? WHERE id = ?", (amount, trans_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ مبلغ ویرایش شد.")
    # برگشت به صفحه روز
    await show_day_page(update, context)
    return ConversationHandler.END


async def edit_desc_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trans_id = int(query.data.split("_")[2])
    context.user_data["edit_trans_id"] = trans_id

    await query.edit_message_text("✏️ توضیحات جدید را وارد کنید:\nبرای لغو /cancel")
    return EDIT_DESC


async def edit_desc_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    trans_id = context.user_data.get("edit_trans_id")

    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE transactions SET description = ? WHERE id = ?", (desc, trans_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ توضیحات ویرایش شد.")
    await show_day_page(update, context)
    return ConversationHandler.END


async def edit_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trans_id = int(query.data.split("_")[2])
    context.user_data["edit_trans_id"] = trans_id

    # نوع تراکنش را دربیاریم تا دسته‌های همان گروه را نشان دهیم
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT transaction_type FROM transactions WHERE id = ?", (trans_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ تراکنش یافت نشد.")
        return ConversationHandler.END

    ttype = row[0]
    group = "income" if ttype == "income" else "expense" if ttype == "expense" else "personal_expense"

    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)

    conn = db_connect()
    c = conn.cursor()
    c.execute("""
        SELECT category_name FROM categories
        WHERE user_id = ? AND category_group = ?
        ORDER BY category_name
    """, (user_scope, group))
    cats = [r[0] for r in c.fetchall()]
    conn.close()

    keyboard = [[InlineKeyboardButton(cat, callback_data=f"setcat_{cat}")] for cat in cats]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_day")])

    await query.edit_message_text(
        "✏️ دسته جدید را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EDIT_CATEGORY


async def edit_category_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split("_", 1)[1]
    trans_id = context.user_data.get("edit_trans_id")

    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE transactions SET category = ? WHERE id = ?", (cat, trans_id))
    conn.commit()
    conn.close()

    await query.edit_message_text("✅ دسته ویرایش شد.")
    await show_day_page(update, context)
    return ConversationHandler.END


# ---------------- Reports ----------------
async def menu_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 گزارش ماهانه", callback_data="report_monthly")],
        [InlineKeyboardButton("📋 گزارش تفکیکی", callback_data="report_detailed")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]
    ]
    await query.edit_message_text("📊 گزارش‌ها\n\nنوع گزارش را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))


async def report_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)

    now = datetime.now()
    month_start = now.replace(day=1).strftime("%Y-%m-%d")

    conn = db_connect()
    c = conn.cursor()

    c.execute("""SELECT SUM(amount) FROM transactions
                 WHERE user_id = ? AND transaction_type = 'income' AND date >= ?""",
              (user_scope, month_start))
    total_income = c.fetchone()[0] or 0

    c.execute("""SELECT SUM(amount) FROM transactions
                 WHERE user_id = ? AND transaction_type = 'expense' AND date >= ?""",
              (user_scope, month_start))
    total_expense = c.fetchone()[0] or 0

    c.execute("""SELECT SUM(amount) FROM transactions
                 WHERE user_id = ? AND transaction_type = 'personal_expense'
                 AND category != 'قسط' AND date >= ?""",
              (user_scope, month_start))
    total_personal = c.fetchone()[0] or 0

    c.execute("""SELECT SUM(amount) FROM transactions
                 WHERE user_id = ? AND transaction_type = 'personal_expense'
                 AND category = 'قسط' AND date >= ?""",
              (user_scope, month_start))
    total_installment = c.fetchone()[0] or 0

    conn.close()

    net_income = total_income - total_expense
    savings = net_income - total_personal

    text = (
        f"📊 گزارش ماهانه ({now.strftime('%Y-%m')})\n\n"
        f"💼 مجموع ورودی‌ها: {format_amount(total_income)}\n"
        f"🧾 مجموع خروجی‌ها: {format_amount(total_expense)}\n"
        f"💰 درآمد ماه: {format_amount(net_income)}\n\n"
        f"👤 خروجی شخصی (بدون قسط): {format_amount(total_personal)}\n"
        f"💎 پس‌انداز: {format_amount(savings)}\n"
        f"📦 جمع قسط ماه: {format_amount(total_installment)}"
    )

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_reports")]]))


async def report_detailed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)

    now = datetime.now()
    month_start = now.replace(day=1).strftime("%Y-%m-%d")

    conn = db_connect()
    c = conn.cursor()

    report = f"📋 گزارش تفکیکی ({now.strftime('%Y-%m')})\n\n"

    c.execute("""SELECT category, SUM(amount) FROM transactions
                 WHERE user_id = ? AND transaction_type = 'income' AND date >= ?
                 GROUP BY category ORDER BY SUM(amount) DESC""",
              (user_scope, month_start))
    rows = c.fetchall()
    report += "💼 ریز ورودی‌ها:\n" + ("\n".join([f"  • {cat}: {format_amount(amt)}" for cat, amt in rows]) or "  • ندارد") + "\n\n"

    c.execute("""SELECT category, SUM(amount) FROM transactions
                 WHERE user_id = ? AND transaction_type = 'expense' AND date >= ?
                 GROUP BY category ORDER BY SUM(amount) DESC""",
              (user_scope, month_start))
    rows = c.fetchall()
    report += "🧾 ریز خروجی‌ها:\n" + ("\n".join([f"  • {cat}: {format_amount(amt)}" for cat, amt in rows]) or "  • ندارد") + "\n\n"

    c.execute("""SELECT category, SUM(amount) FROM transactions
                 WHERE user_id = ? AND transaction_type = 'personal_expense' AND date >= ?
                 GROUP BY category ORDER BY SUM(amount) DESC""",
              (user_scope, month_start))
    rows = c.fetchall()
    report += "👤 ریز خروجی شخصی:\n" + ("\n".join([f"  • {cat}: {format_amount(amt)}" for cat, amt in rows]) or "  • ندارد")

    conn.close()

    await query.edit_message_text(report, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_reports")]]))


# ---------------- Settings ----------------
async def menu_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton("🏷 مدیریت نوع‌ها", callback_data="settings_categories")]]

    if user_id == ADMIN_CHAT_ID:
        keyboard.append([InlineKeyboardButton("🔐 دسترسی‌ها", callback_data="settings_access")])
        keyboard.append([InlineKeyboardButton("💾 دیتابیس", callback_data="settings_database")])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])

    await query.edit_message_text("⚙️ تنظیمات\n\nگزینه مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))


async def settings_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("💼 ورودی کار", callback_data="manage_cat_income")],
        [InlineKeyboardButton("🧾 خروجی کار", callback_data="manage_cat_expense")],
        [InlineKeyboardButton("👤 خروجی شخصی", callback_data="manage_cat_personal")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_settings")]
    ]
    await query.edit_message_text("🏷 مدیریت نوع‌ها\n\nگروه مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))


async def manage_category_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)

    key = query.data.split("_")[2]  # income | expense | personal
    db_group = "income" if key == "income" else "expense" if key == "expense" else "personal_expense"
    group_name = "ورودی کار 💼" if db_group == "income" else "خروجی کار 🧾" if db_group == "expense" else "خروجی شخصی 👤"

    context.user_data["manage_cat_group"] = db_group

    conn = db_connect()
    c = conn.cursor()
    c.execute("""SELECT category_name, is_locked FROM categories
                 WHERE user_id = ? AND category_group = ?
                 ORDER BY category_name""", (user_scope, db_group))
    cats = c.fetchall()
    conn.close()

    keyboard = [[InlineKeyboardButton("➕ اضافه کردن نوع", callback_data="add_cat_to_group")]]
    for cat_name, is_locked in cats:
        if is_locked:
            keyboard.append([InlineKeyboardButton(f"🔒 {cat_name}", callback_data="locked")])
        else:
            keyboard.append([
                InlineKeyboardButton(cat_name, callback_data="noop"),
                InlineKeyboardButton("🗑", callback_data=f"delcat_{cat_name}")
            ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_categories")])

    await query.edit_message_text(
        f"🏷 مدیریت نوع‌های {group_name}\n\nتعداد نوع‌ها: {len(cats)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def add_category_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("➕ نام نوع جدید را وارد کنید:\nبرای لغو /cancel")
    return ADD_CATEGORY_NAME


async def receive_category_name_for_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)

    db_group = context.user_data.get("manage_cat_group")
    if not db_group:
        await update.message.reply_text("❌ گروه دسته مشخص نیست. دوباره از تنظیمات وارد شوید.")
        return ConversationHandler.END

    conn = db_connect()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO categories (user_id, category_group, category_name)
                     VALUES (?, ?, ?)""", (user_scope, db_group, name))
        conn.commit()
        await update.message.reply_text("✅ نوع اضافه شد.")
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ این نوع قبلاً وجود دارد!")
    finally:
        conn.close()

    return ConversationHandler.END


async def delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    db_group = context.user_data.get("manage_cat_group")
    cat_name = query.data.split("_", 1)[1]

    conn = db_connect()
    c = conn.cursor()
    c.execute("""SELECT is_locked FROM categories
                 WHERE user_id = ? AND category_group = ? AND category_name = ?""",
              (user_scope, db_group, cat_name))
    row = c.fetchone()
    if row and row[0] == 1:
        conn.close()
        await query.answer("⛔️ این نوع قفل است و قابل حذف نیست!", show_alert=True)
        return

    c.execute("""DELETE FROM categories
                 WHERE user_id = ? AND category_group = ? AND category_name = ?""",
              (user_scope, db_group, cat_name))
    conn.commit()
    conn.close()

    await query.answer("✅ نوع حذف شد!")
    await manage_category_group(update, context)


# ---------------- Access Settings (Admin only) ----------------
async def settings_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_CHAT_ID:
        await query.answer("⛔️ فقط ادمین اصلی!", show_alert=True)
        return

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT access_mode, shared_data FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
    row = c.fetchone()
    conn.close()

    access_mode = row[0] if row else "private"
    shared_data = row[1] if row else 0

    keyboard = [
        [InlineKeyboardButton("✅ فقط شما" if access_mode == "private" else "فقط شما", callback_data="access_private")],
        [InlineKeyboardButton("✅ ادمین‌های مجاز" if access_mode == "admins" else "ادمین‌های مجاز", callback_data="access_admins")],
        [InlineKeyboardButton("✅ عمومی" if access_mode == "public" else "عمومی", callback_data="access_public")],
    ]

    if access_mode == "admins":
        shared_text = "روشن ✅" if shared_data == 1 else "خاموش"
        keyboard.append([InlineKeyboardButton(f"🔁 اطلاعات مشترک: {shared_text}", callback_data="toggle_shared")])
        keyboard.append([InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="manage_admins")])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_settings")])

    await query.edit_message_text(
        f"🔐 تنظیمات دسترسی\n\nحالت فعلی: {access_mode}\n",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def set_access_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data.split("_")[1]  # private | admins | public

    conn = db_connect()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO settings (user_id, access_mode, shared_data, auto_backup, backup_interval, backup_destination)
        VALUES (
            ?,
            ?,
            COALESCE((SELECT shared_data FROM settings WHERE user_id=?), 0),
            COALESCE((SELECT auto_backup FROM settings WHERE user_id=?), 0),
            COALESCE((SELECT backup_interval FROM settings WHERE user_id=?), 24),
            COALESCE((SELECT backup_destination FROM settings WHERE user_id=?), ?)
        )
    """, (ADMIN_CHAT_ID, mode, ADMIN_CHAT_ID, ADMIN_CHAT_ID, ADMIN_CHAT_ID, ADMIN_CHAT_ID, ADMIN_CHAT_ID))
    conn.commit()
    conn.close()

    await settings_access(update, context)


async def toggle_shared_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT shared_data FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
    row = c.fetchone()
    new_value = 0 if (row and row[0] == 1) else 1
    c.execute("UPDATE settings SET shared_data = ? WHERE user_id = ?", (new_value, ADMIN_CHAT_ID))
    conn.commit()
    conn.close()

    await settings_access(update, context)


# ---------------- Admin management ----------------
async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT admin_id, admin_name FROM admins ORDER BY admin_name")
    admins = c.fetchall()
    conn.close()

    keyboard = [[InlineKeyboardButton("➕ اضافه کردن ادمین", callback_data="add_admin")]]
    for aid, aname in admins:
        keyboard.append([
            InlineKeyboardButton(f"{aname} ({aid})", callback_data="noop"),
            InlineKeyboardButton("🗑", callback_data=f"deladmin_{aid}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_access")])

    await query.edit_message_text(
        f"👥 مدیریت ادمین‌ها\n\nتعداد: {len(admins)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("➕ آیدی عددی ادمین را وارد کنید:\nبرای لغو /cancel")
    return ADD_ADMIN_ID


async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        admin_id = int(update.message.text.strip())
        context.user_data["new_admin_id"] = admin_id
        await update.message.reply_text("👤 نام ادمین را وارد کنید:")
        return ADD_ADMIN_NAME
    except ValueError:
        await update.message.reply_text("❌ لطفاً فقط عدد صحیح وارد کنید.")
        return ADD_ADMIN_ID


async def receive_admin_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_name = update.message.text.strip()
    admin_id = context.user_data.get("new_admin_id")

    conn = db_connect()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO admins (admin_id, admin_name) VALUES (?, ?)", (admin_id, admin_name))
        conn.commit()
        await update.message.reply_text("✅ ادمین اضافه شد.")
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ این آیدی قبلاً ثبت شده است.")
    finally:
        conn.close()

    return ConversationHandler.END


async def delete_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    admin_id = int(query.data.split("_")[1])

    conn = db_connect()
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
    conn.commit()
    conn.close()

    await query.answer("✅ حذف شد.")
    await manage_admins(update, context)


# ---------------- Database / backup settings (Admin only) ----------------
async def settings_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_CHAT_ID:
        await query.answer("⛔️ فقط ادمین اصلی!", show_alert=True)
        return

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT auto_backup, backup_interval FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
    row = c.fetchone()
    conn.close()

    auto_backup = row[0] if row else 0
    backup_interval = row[1] if row else 24
    auto_text = "روشن ✅" if auto_backup == 1 else "خاموش"

    keyboard = [
        [InlineKeyboardButton("📤 گرفتن بکاپ", callback_data="backup_export")],
        [InlineKeyboardButton("📥 وارد کردن بکاپ", callback_data="backup_import")],
        [InlineKeyboardButton(f"⏱️ بکاپ خودکار: {auto_text}", callback_data="toggle_auto_backup")],
        [InlineKeyboardButton("⚙️ تنظیم بکاپ خودکار", callback_data="config_auto_backup")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_settings")]
    ]
    await query.edit_message_text(
        f"💾 مدیریت دیتابیس\n\nبکاپ خودکار: {auto_text}\nفاصله: هر {backup_interval} ساعت",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def export_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("در حال ارسال بکاپ...")

    now = datetime.now()
    backup_filename = f"KasbBook_backup_{now.strftime('%Y-%m-%d_%H-%M')}.db"

    with open(DB_NAME, "rb") as f:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=f,
            filename=backup_filename
        )

    await query.edit_message_text("✅ بکاپ ارسال شد.\nبرای بازگشت /start")


async def import_backup_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📥 فایل بکاپ (.db) را ارسال کنید:\nبرای لغو /cancel")
    return UPLOAD_BACKUP_FILE


async def receive_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith(".db"):
        await update.message.reply_text("❌ فقط فایل .db مجاز است!")
        return UPLOAD_BACKUP_FILE

    file = await context.bot.get_file(doc.file_id)
    temp_path = f"temp_backup_{datetime.now().timestamp()}.db"
    await file.download_to_drive(temp_path)

    # validate
    try:
        conn = sqlite3.connect(temp_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in c.fetchall()}
        conn.close()

        required = {"transactions", "categories", "settings", "admins"}
        if not required.issubset(tables):
            os.remove(temp_path)
            await update.message.reply_text("❌ بکاپ معتبر نیست.")
            return UPLOAD_BACKUP_FILE

        old = f"KasbBook_old_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db"
        if os.path.exists(DB_NAME):
            os.rename(DB_NAME, old)
        os.rename(temp_path, DB_NAME)

        await update.message.reply_text(f"✅ بکاپ بازیابی شد.\nبکاپ قبلی: {old}\n\n/start")
        return ConversationHandler.END

    except Exception as e:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        await update.message.reply_text(f"❌ خطا در بازیابی: {e}")
        return UPLOAD_BACKUP_FILE


async def toggle_auto_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT auto_backup, backup_interval FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
    row = c.fetchone()
    current = row[0] if row else 0
    interval_hours = row[1] if row else 24

    new_val = 0 if current == 1 else 1
    c.execute("UPDATE settings SET auto_backup = ? WHERE user_id = ?", (new_val, ADMIN_CHAT_ID))
    conn.commit()
    conn.close()

    # remove old jobs
    for job in context.job_queue.get_jobs_by_name(f"auto_backup_{ADMIN_CHAT_ID}"):
        job.schedule_removal()

    # add if enabled
    if new_val == 1:
        context.job_queue.run_repeating(
            auto_backup_job,
            interval=max(1, interval_hours) * 3600,
            first=10,
            name=f"auto_backup_{ADMIN_CHAT_ID}"
        )

    await settings_database(update, context)


async def config_auto_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏱ هر چند ساعت بکاپ گرفته شود؟ (عدد)\nبرای لغو /cancel")
    return BACKUP_INTERVAL


async def receive_backup_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        interval = int(update.message.text.strip())
        if interval < 1:
            raise ValueError
        context.user_data["backup_interval"] = interval
        await update.message.reply_text(
            f"📬 آیدی مقصد ارسال بکاپ را وارد کنید (عدد)\n"
            f"(پیش‌فرض: {ADMIN_CHAT_ID})\n"
            "برای لغو /cancel"
        )
        return BACKUP_DEST
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح بزرگتر از 0 وارد کنید.")
        return BACKUP_INTERVAL


async def receive_backup_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        destination = int(update.message.text.strip())
        interval = context.user_data.get("backup_interval", 24)

        conn = db_connect()
        c = conn.cursor()
        c.execute("""
            UPDATE settings SET backup_interval = ?, backup_destination = ?
            WHERE user_id = ?
        """, (interval, destination, ADMIN_CHAT_ID))
        conn.commit()
        conn.close()

        # reschedule if auto enabled
        for job in context.job_queue.get_jobs_by_name(f"auto_backup_{ADMIN_CHAT_ID}"):
            job.schedule_removal()

        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT auto_backup FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
        row = c.fetchone()
        conn.close()
        if row and row[0] == 1:
            context.job_queue.run_repeating(
                auto_backup_job,
                interval=interval * 3600,
                first=10,
                name=f"auto_backup_{ADMIN_CHAT_ID}"
            )

        await update.message.reply_text(
            f"✅ ذخیره شد.\nفاصله: هر {interval} ساعت\nمقصد: {destination}\n\n/start"
        )
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ آیدی عددی معتبر وارد کنید.")
        return BACKUP_DEST


async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT auto_backup, backup_destination FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
    row = c.fetchone()
    conn.close()

    if not row or row[0] != 1:
        return

    destination = row[1] or ADMIN_CHAT_ID
    now = datetime.now()
    backup_filename = f"KasbBook_backup_{now.strftime('%Y-%m-%d_%H-%M')}.db"

    try:
        with open(DB_NAME, "rb") as f:
            await context.bot.send_document(
                chat_id=destination,
                document=f,
                filename=backup_filename,
                caption="🔄 بکاپ خودکار"
            )
    except Exception as e:
        logger.error(f"Auto backup error: {e}")


# ---------------- Common ----------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("❌ عملیات لغو شد.\nبرای بازگشت /start")
    return ConversationHandler.END


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "back_main":
        await show_main_menu(update, context)
    elif data == "back_day":
        await query.answer()
        await show_day_page(update, context)
    elif data.startswith("header_"):
        await query.answer()
    elif data == "locked":
        await query.answer("🔒 این نوع قفل است و قابل حذف نیست!", show_alert=True)
    elif data == "noop":
        await query.answer()


# ---------------- main ----------------
def main():
    init_db()

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN در فایل .env تنظیم نشده است")
    if not ADMIN_CHAT_ID:
        raise RuntimeError("ADMIN_CHAT_ID در فایل .env تنظیم نشده است")

    application = Application.builder().token(BOT_TOKEN).build()

    # Date conversation
    date_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(request_gregorian_date, pattern=r"^date_gregorian$"),
            CallbackQueryHandler(request_jalali_date, pattern=r"^date_jalali$"),
        ],
        states={SELECT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Add transaction conversation
    add_trans_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_transaction, pattern=r"^add_(income|expense|personal)$")],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(select_category, pattern=r"^selcat_"),
                CallbackQueryHandler(add_new_category_start, pattern=r"^add_new_category$"),
            ],
            ADD_CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_category_name)],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
            ENTER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description),
                CallbackQueryHandler(skip_description, pattern=r"^skip_desc$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Edit amount conversation
    edit_amount_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_amount_start, pattern=r"^edit_amount_\d+$")],
        states={EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_amount_receive)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Edit desc conversation
    edit_desc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_desc_start, pattern=r"^edit_desc_\d+$")],
        states={EDIT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_desc_receive)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Edit category conversation
    edit_cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_category_start, pattern=r"^edit_category_\d+$")],
        states={EDIT_CATEGORY: [CallbackQueryHandler(edit_category_set, pattern=r"^setcat_")]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Manage categories conversation
    manage_cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_category_to_group, pattern=r"^add_cat_to_group$")],
        states={ADD_CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name_for_group)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Admin conversation
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern=r"^add_admin$")],
        states={
            ADD_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_id)],
            ADD_ADMIN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Backup import conversation
    backup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(import_backup_request, pattern=r"^backup_import$")],
        states={UPLOAD_BACKUP_FILE: [MessageHandler(filters.Document.ALL, receive_backup_file)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Config auto backup conversation
    config_backup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(config_auto_backup_start, pattern=r"^config_auto_backup$")],
        states={
            BACKUP_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_backup_interval)],
            BACKUP_DEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_backup_destination)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Handlers
    application.add_handler(CommandHandler("start", start))

    application.add_handler(date_conv)
    application.add_handler(add_trans_conv)
    application.add_handler(edit_amount_conv)
    application.add_handler(edit_desc_conv)
    application.add_handler(edit_cat_conv)

    application.add_handler(manage_cat_conv)
    application.add_handler(admin_conv)
    application.add_handler(backup_conv)
    application.add_handler(config_backup_conv)

    # menus
    application.add_handler(CallbackQueryHandler(menu_transactions, pattern=r"^menu_transactions$"))
    application.add_handler(CallbackQueryHandler(menu_reports, pattern=r"^menu_reports$"))
    application.add_handler(CallbackQueryHandler(menu_settings, pattern=r"^menu_settings$"))
    application.add_handler(CallbackQueryHandler(select_date_today, pattern=r"^date_today$"))

    # transaction view/delete
    application.add_handler(CallbackQueryHandler(view_transaction, pattern=r"^view_trans_\d+$"))
    application.add_handler(CallbackQueryHandler(delete_transaction, pattern=r"^delete_trans_\d+$"))

    # reports
    application.add_handler(CallbackQueryHandler(report_monthly, pattern=r"^report_monthly$"))
    application.add_handler(CallbackQueryHandler(report_detailed, pattern=r"^report_detailed$"))

    # settings
    application.add_handler(CallbackQueryHandler(settings_categories, pattern=r"^settings_categories$"))
    application.add_handler(CallbackQueryHandler(manage_category_group, pattern=r"^manage_cat_"))
    application.add_handler(CallbackQueryHandler(delete_category, pattern=r"^delcat_"))
    application.add_handler(CallbackQueryHandler(settings_access, pattern=r"^settings_access$"))
    application.add_handler(CallbackQueryHandler(set_access_mode, pattern=r"^access_(private|admins|public)$"))
    application.add_handler(CallbackQueryHandler(toggle_shared_data, pattern=r"^toggle_shared$"))
    application.add_handler(CallbackQueryHandler(manage_admins, pattern=r"^manage_admins$"))
    application.add_handler(CallbackQueryHandler(delete_admin, pattern=r"^deladmin_"))
    application.add_handler(CallbackQueryHandler(settings_database, pattern=r"^settings_database$"))
    application.add_handler(CallbackQueryHandler(export_backup, pattern=r"^backup_export$"))
    application.add_handler(CallbackQueryHandler(toggle_auto_backup, pattern=r"^toggle_auto_backup$"))

    # آخرین handler عمومی
    application.add_handler(CallbackQueryHandler(button_callback))

    # اگر auto_backup روشن بود، هنگام استارت سرویس job را فعال کن
    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute("SELECT auto_backup, backup_interval FROM settings WHERE user_id = ?", (ADMIN_CHAT_ID,))
        row = c.fetchone()
        conn.close()
        if row and row[0] == 1:
            interval_hours = max(1, int(row[1] or 24))
            application.job_queue.run_repeating(
                auto_backup_job,
                interval=interval_hours * 3600,
                first=10,
                name=f"auto_backup_{ADMIN_CHAT_ID}"
            )
    except Exception as e:
        logger.error(f"Could not restore auto-backup schedule: {e}")

    logger.info("🚀 KasbBook bot started!")
    application.run_polling()   # ✅ بدون Update.ALL_TYPES


if __name__ == "__main__":
    main()
