#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio
from dotenv import load_dotenv

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# بارگذاری متغیرهای محیطی
load_dotenv()

# تنظیم لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن ربات و آیدی ادمین
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID'))

# States برای ConversationHandler
(SELECT_DATE, SELECT_TRANSACTION_TYPE, SELECT_CATEGORY, 
 ENTER_AMOUNT, ENTER_DESCRIPTION, 
 ADD_CATEGORY_NAME, DELETE_CATEGORY_CONFIRM,
 EDIT_FIELD, EDIT_VALUE,
 ADD_ADMIN_ID, ADD_ADMIN_NAME,
 BACKUP_INTERVAL, BACKUP_DEST,
 UPLOAD_BACKUP_FILE) = range(14)

# نام دیتابیس
DB_NAME = 'KasbBook.db'


def init_db():
    """ساخت جداول دیتابیس"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # جدول تراکنش‌ها
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول نوع‌ها (دسته‌ها)
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_group TEXT NOT NULL,
            category_name TEXT NOT NULL,
            is_locked INTEGER DEFAULT 0,
            UNIQUE(user_id, category_group, category_name)
        )
    ''')
    
    # جدول تنظیمات
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER PRIMARY KEY,
            access_mode TEXT DEFAULT 'private',
            shared_data INTEGER DEFAULT 0,
            auto_backup INTEGER DEFAULT 0,
            backup_interval INTEGER DEFAULT 24,
            backup_destination INTEGER
        )
    ''')
    
    # جدول ادمین‌ها
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL UNIQUE,
            admin_name TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    
    # افزودن دسته قسط به صورت پیش‌فرض
    add_default_installment_category()


def add_default_installment_category():
    """افزودن دسته قسط به خروجی شخصی"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR IGNORE INTO categories (user_id, category_group, category_name, is_locked)
            VALUES (?, ?, ?, ?)
        ''', (ADMIN_CHAT_ID, 'personal_expense', 'قسط', 1))
        conn.commit()
    except:
        pass
    finally:
        conn.close()


def format_amount(amount: int) -> str:
    """فرمت‌دهی مبلغ با جداکننده سه‌رقمی"""
    return f"{amount:,} تومان"


def get_user_scope(user_id: int) -> int:
    """تعیین scope کاربر بر اساس تنظیمات"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # دریافت تنظیمات ادمین اصلی
    c.execute('SELECT access_mode, shared_data FROM settings WHERE user_id = ?', (ADMIN_CHAT_ID,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return user_id
    
    access_mode, shared_data = result
    
    # اگر کاربر ادمین اصلی است
    if user_id == ADMIN_CHAT_ID:
        return ADMIN_CHAT_ID
    
    # اگر حالت ادمین‌های مجاز و اطلاعات مشترک فعال است
    if access_mode == 'admins' and shared_data == 1:
        # بررسی اینکه کاربر ادمین است یا نه
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,))
        is_admin = c.fetchone()
        conn.close()
        
        if is_admin:
            return ADMIN_CHAT_ID  # داده‌ها در scope ادمین اصلی
    
    return user_id  # scope خود کاربر


def check_access(user_id: int) -> bool:
    """بررسی دسترسی کاربر"""
    if user_id == ADMIN_CHAT_ID:
        return True
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # دریافت حالت دسترسی
    c.execute('SELECT access_mode FROM settings WHERE user_id = ?', (ADMIN_CHAT_ID,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return False
    
    access_mode = result[0]
    
    if access_mode == 'public':
        conn.close()
        return True
    elif access_mode == 'admins':
        c.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,))
        is_admin = c.fetchone()
        conn.close()
        return is_admin is not None
    
    conn.close()
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ربات و نمایش منوی اصلی"""
    user_id = update.effective_user.id
    
    if not check_access(user_id):
        await update.message.reply_text(
            "⛔️ متأسفانه شما به این ربات دسترسی ندارید.\n"
            "لطفاً با مدیر ربات تماس بگیرید. 🙏"
        )
        return
    
    # ایجاد تنظیمات پیش‌فرض برای کاربر
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO settings (user_id, backup_destination)
        VALUES (?, ?)
    ''', (user_id, user_id))
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📌 تراکنش‌ها", callback_data="menu_transactions")],
        [InlineKeyboardButton("📊 گزارش‌ها", callback_data="menu_reports")],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "✨ به ربات KasbBook خوش آمدید! ✨\n\n"
        "🎯 با این ربات می‌توانید دخل و خرج خود را به راحتی مدیریت کنید.\n"
        "📝 تراکنش‌های خود را ثبت کنید\n"
        "📊 گزارش‌های دقیق دریافت کنید\n"
        "⚙️ تنظیمات را شخصی‌سازی کنید\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی اصلی"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📌 تراکنش‌ها", callback_data="menu_transactions")],
        [InlineKeyboardButton("📊 گزارش‌ها", callback_data="menu_reports")],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🏠 منوی اصلی\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید: 👇"
    )
    
    await query.edit_message_text(text, reply_markup=reply_markup)


async def menu_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی تراکنش‌ها - انتخاب تاریخ"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📅 امروز", callback_data="date_today")],
        [InlineKeyboardButton("📆 تاریخ میلادی", callback_data="date_gregorian")],
        [InlineKeyboardButton("🗓 تاریخ شمسی", callback_data="date_jalali")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📌 تراکنش‌ها\n\n"
        "لطفاً تاریخ مورد نظر را انتخاب کنید: 📅"
    )
    
    await query.edit_message_text(text, reply_markup=reply_markup)


async def select_date_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب تاریخ امروز"""
    query = update.callback_query
    await query.answer()
    
    today = datetime.now().strftime('%Y-%m-%d')
    context.user_data['selected_date'] = today
    
    await show_day_page(update, context)


async def request_gregorian_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """درخواست تاریخ میلادی"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📆 لطفاً تاریخ میلادی را به فرمت YYYY-MM-DD وارد کنید:\n"
        "مثال: 2024-03-15\n\n"
        "برای لغو /cancel را بزنید."
    )
    
    return SELECT_DATE


async def request_jalali_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """درخواست تاریخ شمسی"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🗓 لطفاً تاریخ شمسی را به فرمت YYYY-MM-DD وارد کنید:\n"
        "مثال: 1403-02-25\n\n"
        "برای لغو /cancel را بزنید."
    )
    
    return SELECT_DATE


async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت تاریخ از کاربر"""
    date_text = update.message.text.strip()
    
    # اعتبارسنجی ساده تاریخ
    try:
        datetime.strptime(date_text, '%Y-%m-%d')
        context.user_data['selected_date'] = date_text
        await show_day_page(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ فرمت تاریخ نادرست است!\n"
            "لطفاً به فرمت YYYY-MM-DD وارد کنید.\n"
            "مثال: 2024-03-15"
        )
        return SELECT_DATE


async def show_day_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش صفحه روز با تراکنش‌ها"""
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    selected_date = context.user_data.get('selected_date')
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # دریافت تراکنش‌های روز
    c.execute('''
        SELECT id, transaction_type, category, amount
        FROM transactions
        WHERE user_id = ? AND date = ?
        ORDER BY created_at
    ''', (user_scope, selected_date))
    
    transactions = c.fetchall()
    conn.close()
    
    # دسته‌بندی تراکنش‌ها
    income_trans = [t for t in transactions if t[1] == 'income']
    expense_trans = [t for t in transactions if t[1] == 'expense']
    personal_trans = [t for t in transactions if t[1] == 'personal_expense']
    
    # ساخت کیبورد
    keyboard = []
    
    # بخش ورودی
    keyboard.append([InlineKeyboardButton("— 💼 ورودی —", callback_data="header_income")])
    for trans in income_trans:
        keyboard.append([
            InlineKeyboardButton(f"{trans[2]}", callback_data=f"view_trans_{trans[0]}"),
            InlineKeyboardButton(f"{trans[3]:,}", callback_data=f"view_trans_{trans[0]}")
        ])
    
    # بخش خروجی
    keyboard.append([InlineKeyboardButton("— 🧾 خروجی —", callback_data="header_expense")])
    for trans in expense_trans:
        keyboard.append([
            InlineKeyboardButton(f"{trans[2]}", callback_data=f"view_trans_{trans[0]}"),
            InlineKeyboardButton(f"{trans[3]:,}", callback_data=f"view_trans_{trans[0]}")
        ])
    
    # بخش خروجی شخصی
    keyboard.append([InlineKeyboardButton("— 👤 خروجی شخصی —", callback_data="header_personal")])
    for trans in personal_trans:
        keyboard.append([
            InlineKeyboardButton(f"{trans[2]}", callback_data=f"view_trans_{trans[0]}"),
            InlineKeyboardButton(f"{trans[3]:,}", callback_data=f"view_trans_{trans[0]}")
        ])
    
    # دکمه‌های افزودن
    keyboard.append([
        InlineKeyboardButton("➕ ورودی", callback_data="add_income"),
        InlineKeyboardButton("➖ خروجی", callback_data="add_expense")
    ])
    keyboard.append([InlineKeyboardButton("👤 شخصی", callback_data="add_personal")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_transactions")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"📅 تراکنش‌های روز {selected_date}\n\n"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def view_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات تراکنش"""
    query = update.callback_query
    await query.answer()
    
    trans_id = int(query.data.split('_')[2])
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT transaction_type, category, amount, description, date
        FROM transactions
        WHERE id = ?
    ''', (trans_id,))
    
    trans = c.fetchone()
    conn.close()
    
    if not trans:
        await query.edit_message_text("❌ تراکنش یافت نشد!")
        return
    
    trans_type, category, amount, description, date = trans
    
    type_emoji = "💼" if trans_type == "income" else "🧾" if trans_type == "expense" else "👤"
    type_name = "ورودی" if trans_type == "income" else "خروجی" if trans_type == "expense" else "خروجی شخصی"
    
    text = (
        f"{type_emoji} جزئیات تراکنش\n\n"
        f"📋 نوع: {type_name}\n"
        f"🏷 دسته: {category}\n"
        f"💰 مبلغ: {format_amount(amount)}\n"
        f"📝 توضیحات: {description or 'ندارد'}\n"
        f"📅 تاریخ: {date}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ ویرایش نوع", callback_data=f"edit_category_{trans_id}")],
        [InlineKeyboardButton("✏️ ویرایش مبلغ", callback_data=f"edit_amount_{trans_id}")],
        [InlineKeyboardButton("✏️ ویرایش توضیحات", callback_data=f"edit_desc_{trans_id}")],
        [InlineKeyboardButton("🗑 حذف", callback_data=f"delete_trans_{trans_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_day")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.user_data['current_trans_id'] = trans_id
    
    await query.edit_message_text(text, reply_markup=reply_markup)


async def start_add_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع فرآیند افزودن تراکنش"""
    query = update.callback_query
    await query.answer()
    
    trans_type = query.data.split('_')[1]
    context.user_data['new_trans_type'] = trans_type
    
    # نمایش دسته‌ها
    await show_categories_selection(update, context, trans_type)
    
    return SELECT_CATEGORY


async def show_categories_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, trans_type: str):
    """نمایش دسته‌ها برای انتخاب"""
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    
    # تعیین گروه دسته
    if trans_type == 'income':
        category_group = 'income'
        type_name = "ورودی 💼"
    elif trans_type == 'expense':
        category_group = 'expense'
        type_name = "خروجی 🧾"
    else:
        category_group = 'personal_expense'
        type_name = "خروجی شخصی 👤"
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT category_name FROM categories
        WHERE user_id = ? AND category_group = ?
        ORDER BY category_name
    ''', (user_scope, category_group))
    
    categories = c.fetchall()
    conn.close()
    
    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(cat[0], callback_data=f"selcat_{cat[0]}")])
    
    keyboard.append([InlineKeyboardButton("➕ افزودن نوع جدید", callback_data="add_new_category")])
    keyboard.append([InlineKeyboardButton("🔙 لغو", callback_data="back_day")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"🏷 انتخاب دسته برای {type_name}\n\nلطفاً یک دسته انتخاب کنید: 👇"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب دسته توسط کاربر"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.split('_', 1)[1]
    context.user_data['new_trans_category'] = category
    
    await query.edit_message_text(
        f"💰 مبلغ را به تومان وارد کنید:\n\n"
        f"فقط عدد وارد کنید (بدون جداکننده)\n"
        f"برای لغو /cancel را بزنید."
    )
    
    return ENTER_AMOUNT


async def add_new_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع افزودن دسته جدید"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ افزودن دسته جدید\n\n"
        "لطفاً نام دسته جدید را وارد کنید:\n"
        "برای لغو /cancel را بزنید."
    )
    
    return ADD_CATEGORY_NAME


async def receive_new_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت نام دسته جدید"""
    category_name = update.message.text.strip()
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    trans_type = context.user_data.get('new_trans_type')
    
    # تعیین گروه
    if trans_type == 'income':
        category_group = 'income'
    elif trans_type == 'expense':
        category_group = 'expense'
    else:
        category_group = 'personal_expense'
    
    # افزودن به دیتابیس
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO categories (user_id, category_group, category_name)
            VALUES (?, ?, ?)
        ''', (user_scope, category_group, category_name))
        conn.commit()
        
        await update.message.reply_text(f"✅ دسته «{category_name}» با موفقیت اضافه شد!")
        
        # ادامه فرآیند افزودن تراکنش
        context.user_data['new_trans_category'] = category_name
        
        await update.message.reply_text(
            f"💰 مبلغ را به تومان وارد کنید:\n\n"
            f"فقط عدد وارد کنید (بدون جداکننده)\n"
            f"برای لغو /cancel را بزنید."
        )
        
        return ENTER_AMOUNT
        
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ این دسته قبلاً وجود دارد!")
        return ADD_CATEGORY_NAME
    finally:
        conn.close()


async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت مبلغ"""
    try:
        amount = int(update.message.text.strip().replace(',', ''))
        context.user_data['new_trans_amount'] = amount
        
        keyboard = [[InlineKeyboardButton("رد کردن توضیحات", callback_data="skip_desc")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📝 توضیحات (اختیاری):\n\n"
            "توضیحات تراکنش را وارد کنید یا دکمه زیر را بزنید:",
            reply_markup=reply_markup
        )
        
        return ENTER_DESCRIPTION
        
    except ValueError:
        await update.message.reply_text(
            "❌ لطفاً فقط عدد وارد کنید!\n"
            "مثال: 50000"
        )
        return ENTER_AMOUNT


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رد کردن توضیحات"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['new_trans_description'] = None
    await save_transaction(update, context)
    
    return ConversationHandler.END


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت توضیحات"""
    description = update.message.text.strip()
    context.user_data['new_trans_description'] = description
    
    await save_transaction(update, context)
    
    return ConversationHandler.END


async def save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ذخیره تراکنش در دیتابیس"""
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    
    trans_type = context.user_data.get('new_trans_type')
    category = context.user_data.get('new_trans_category')
    amount = context.user_data.get('new_trans_amount')
    description = context.user_data.get('new_trans_description')
    date = context.user_data.get('selected_date')
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO transactions (user_id, transaction_type, category, amount, description, date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_scope, trans_type, category, amount, description, date))
    conn.commit()
    conn.close()
    
    type_emoji = "💼" if trans_type == "income" else "🧾" if trans_type == "expense" else "👤"
    
    success_text = (
        f"✅ تراکنش با موفقیت ثبت شد! {type_emoji}\n\n"
        f"🏷 دسته: {category}\n"
        f"💰 مبلغ: {format_amount(amount)}\n"
        f"📝 توضیحات: {description or 'ندارد'}"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(success_text)
    else:
        await update.message.reply_text(success_text)
    
    # نمایش مجدد صفحه روز
    await show_day_page(update, context)


async def delete_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف تراکنش"""
    query = update.callback_query
    await query.answer()
    
    trans_id = int(query.data.split('_')[2])
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM transactions WHERE id = ?', (trans_id,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text("✅ تراکنش با موفقیت حذف شد!")
    await show_day_page(update, context)


async def menu_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی گزارش‌ها"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📊 گزارش ماهانه", callback_data="report_monthly")],
        [InlineKeyboardButton("📋 گزارش تفکیکی", callback_data="report_detailed")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("📊 گزارش‌ها\n\nنوع گزارش را انتخاب کنید:", reply_markup=reply_markup)


async def report_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گزارش ماهانه"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    
    # ماه جاری
    now = datetime.now()
    month_start = now.replace(day=1).strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # مجموع ورودی‌ها
    c.execute('''
        SELECT SUM(amount) FROM transactions
        WHERE user_id = ? AND transaction_type = 'income' AND date >= ?
    ''', (user_scope, month_start))
    total_income = c.fetchone()[0] or 0
    
    # مجموع خروجی‌ها
    c.execute('''
        SELECT SUM(amount) FROM transactions
        WHERE user_id = ? AND transaction_type = 'expense' AND date >= ?
    ''', (user_scope, month_start))
    total_expense = c.fetchone()[0] or 0
    
    # مجموع خروجی شخصی بدون قسط
    c.execute('''
        SELECT SUM(amount) FROM transactions
        WHERE user_id = ? AND transaction_type = 'personal_expense' 
        AND category != 'قسط' AND date >= ?
    ''', (user_scope, month_start))
    total_personal = c.fetchone()[0] or 0
    
    # مجموع قسط
    c.execute('''
        SELECT SUM(amount) FROM transactions
        WHERE user_id = ? AND transaction_type = 'personal_expense' 
        AND category = 'قسط' AND date >= ?
    ''', (user_scope, month_start))
    total_installment = c.fetchone()[0] or 0
    
    conn.close()
    
    # محاسبات
    net_income = total_income - total_expense
    savings = net_income - total_personal
    
    report_text = (
        f"📊 گزارش ماهانه ({now.strftime('%Y-%m')})\n\n"
        f"💼 مجموع ورودی‌ها: {format_amount(total_income)}\n"
        f"🧾 مجموع خروجی‌ها: {format_amount(total_expense)}\n"
        f"💰 درآمد ماه: {format_amount(net_income)}\n\n"
        f"👤 خروجی شخصی (بدون قسط): {format_amount(total_personal)}\n"
        f"💎 پس‌انداز: {format_amount(savings)}\n"
        f"📦 جمع قسط ماه: {format_amount(total_installment)}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_reports")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(report_text, reply_markup=reply_markup)


async def report_detailed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گزارش تفکیکی"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    
    now = datetime.now()
    month_start = now.replace(day=1).strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    report_text = f"📋 گزارش تفکیکی ({now.strftime('%Y-%m')})\n\n"
    
    # ریز ورودی‌ها
    c.execute('''
        SELECT category, SUM(amount) FROM transactions
        WHERE user_id = ? AND transaction_type = 'income' AND date >= ?
        GROUP BY category
        ORDER BY SUM(amount) DESC
    ''', (user_scope, month_start))
    income_details = c.fetchall()
    
    report_text += "💼 ریز ورودی‌ها:\n"
    for cat, amount in income_details:
        report_text += f"  • {cat}: {format_amount(amount)}\n"
    
    # ریز خروجی‌ها
    c.execute('''
        SELECT category, SUM(amount) FROM transactions
        WHERE user_id = ? AND transaction_type = 'expense' AND date >= ?
        GROUP BY category
        ORDER BY SUM(amount) DESC
    ''', (user_scope, month_start))
    expense_details = c.fetchall()
    
    report_text += "\n🧾 ریز خروجی‌ها:\n"
    for cat, amount in expense_details:
        report_text += f"  • {cat}: {format_amount(amount)}\n"
    
    # ریز خروجی شخصی
    c.execute('''
        SELECT category, SUM(amount) FROM transactions
        WHERE user_id = ? AND transaction_type = 'personal_expense' AND date >= ?
        GROUP BY category
        ORDER BY SUM(amount) DESC
    ''', (user_scope, month_start))
    personal_details = c.fetchall()
    
    report_text += "\n👤 ریز خروجی شخصی:\n"
    for cat, amount in personal_details:
        report_text += f"  • {cat}: {format_amount(amount)}\n"
    
    conn.close()
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_reports")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(report_text, reply_markup=reply_markup)


async def menu_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی تنظیمات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🏷 مدیریت نوع‌ها", callback_data="settings_categories")]
    ]
    
    # فقط ادمین اصلی
    if user_id == ADMIN_CHAT_ID:
        keyboard.append([InlineKeyboardButton("🔐 دسترسی‌ها", callback_data="settings_access")])
        keyboard.append([InlineKeyboardButton("💾 دیتابیس", callback_data="settings_database")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("⚙️ تنظیمات\n\nگزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup)


async def settings_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت نوع‌ها"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("💼 ورودی کار", callback_data="manage_cat_income")],
        [InlineKeyboardButton("🧾 خروجی کار", callback_data="manage_cat_expense")],
        [InlineKeyboardButton("👤 خروجی شخصی", callback_data="manage_cat_personal")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🏷 مدیریت نوع‌ها\n\nگروه مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )


async def manage_category_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت یک گروه از دسته‌ها"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    
    cat_group = query.data.split('_')[2]
    context.user_data['manage_cat_group'] = cat_group
    
    # تعیین نام گروه
    if cat_group == 'income':
        group_name = "ورودی کار 💼"
        db_group = 'income'
    elif cat_group == 'expense':
        group_name = "خروجی کار 🧾"
        db_group = 'expense'
    else:
        group_name = "خروجی شخصی 👤"
        db_group = 'personal_expense'
    
    # دریافت دسته‌ها
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT category_name, is_locked FROM categories
        WHERE user_id = ? AND category_group = ?
        ORDER BY category_name
    ''', (user_scope, db_group))
    categories = c.fetchall()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("➕ اضافه کردن نوع", callback_data="add_cat_to_group")]]
    
    for cat_name, is_locked in categories:
        if is_locked:
            keyboard.append([InlineKeyboardButton(f"🔒 {cat_name}", callback_data="locked")])
        else:
            keyboard.append([
                InlineKeyboardButton(cat_name, callback_data=f"viewcat_{cat_name}"),
                InlineKeyboardButton("🗑", callback_data=f"delcat_{cat_name}")
            ])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_categories")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🏷 مدیریت نوع‌های {group_name}\n\n"
        f"تعداد نوع‌ها: {len(categories)}",
        reply_markup=reply_markup
    )


async def add_category_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن دسته به گروه"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ افزودن نوع جدید\n\n"
        "لطفاً نام نوع را وارد کنید:\n"
        "برای لغو /cancel را بزنید."
    )
    
    return ADD_CATEGORY_NAME


async def receive_category_name_for_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت نام دسته برای گروه"""
    category_name = update.message.text.strip()
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    
    cat_group = context.user_data.get('manage_cat_group')
    
    if cat_group == 'income':
        db_group = 'income'
    elif cat_group == 'expense':
        db_group = 'expense'
    else:
        db_group = 'personal_expense'
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO categories (user_id, category_group, category_name)
            VALUES (?, ?, ?)
        ''', (user_scope, db_group, category_name))
        conn.commit()
        await update.message.reply_text(f"✅ نوع «{category_name}» با موفقیت اضافه شد!")
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ این نوع قبلاً وجود دارد!")
    finally:
        conn.close()
    
    return ConversationHandler.END


async def delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف دسته"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_scope = get_user_scope(user_id)
    
    cat_name = query.data.split('_', 1)[1]
    cat_group = context.user_data.get('manage_cat_group')
    
    if cat_group == 'income':
        db_group = 'income'
    elif cat_group == 'expense':
        db_group = 'expense'
    else:
        db_group = 'personal_expense'
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # بررسی قفل بودن
    c.execute('''
        SELECT is_locked FROM categories
        WHERE user_id = ? AND category_group = ? AND category_name = ?
    ''', (user_scope, db_group, cat_name))
    result = c.fetchone()
    
    if result and result[0] == 1:
        await query.answer("⛔️ این نوع قفل است و قابل حذف نیست!", show_alert=True)
        conn.close()
        return
    
    c.execute('''
        DELETE FROM categories
        WHERE user_id = ? AND category_group = ? AND category_name = ?
    ''', (user_scope, db_group, cat_name))
    conn.commit()
    conn.close()
    
    await query.answer("✅ نوع حذف شد!")
    
    # بازگشت به صفحه مدیریت
    context.user_data['manage_cat_group'] = cat_group
    await manage_category_group(update, context)


async def settings_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیمات دسترسی"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_CHAT_ID:
        await query.answer("⛔️ فقط ادمین اصلی دسترسی دارد!", show_alert=True)
        return
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT access_mode, shared_data FROM settings WHERE user_id = ?', (ADMIN_CHAT_ID,))
    result = c.fetchone()
    conn.close()
    
    access_mode = result[0] if result else 'private'
    shared_data = result[1] if result else 0
    
    keyboard = [
        [InlineKeyboardButton(
            "✅ فقط شما" if access_mode == 'private' else "فقط شما",
            callback_data="access_private"
        )],
        [InlineKeyboardButton(
            "✅ ادمین‌های مجاز" if access_mode == 'admins' else "ادمین‌های مجاز",
            callback_data="access_admins"
        )],
        [InlineKeyboardButton(
            "✅ عمومی" if access_mode == 'public' else "عمومی",
            callback_data="access_public"
        )]
    ]
    
    # اگر حالت ادمین‌های مجاز است
    if access_mode == 'admins':
        shared_text = "روشن ✅" if shared_data == 1 else "خاموش"
        keyboard.append([InlineKeyboardButton(
            f"🔁 اطلاعات مشترک: {shared_text}",
            callback_data="toggle_shared"
        )])
        keyboard.append([InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="manage_admins")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_settings")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    mode_text = {
        'private': 'فقط شما',
        'admins': 'ادمین‌های مجاز',
        'public': 'عمومی'
    }
    
    await query.edit_message_text(
        f"🔐 تنظیمات دسترسی\n\n"
        f"حالت فعلی: {mode_text.get(access_mode, 'نامشخص')}\n\n"
        f"یک حالت را انتخاب کنید:",
        reply_markup=reply_markup
    )


async def set_access_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم حالت دسترسی"""
    query = update.callback_query
    await query.answer()
    
    mode = query.data.split('_')[1]
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO settings (user_id, access_mode)
        VALUES (?, ?)
    ''', (ADMIN_CHAT_ID, mode))
    conn.commit()
    conn.close()
    
    await settings_access(update, context)


async def toggle_shared_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت اطلاعات مشترک"""
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT shared_data FROM settings WHERE user_id = ?', (ADMIN_CHAT_ID,))
    result = c.fetchone()
    
    new_value = 0 if (result and result[0] == 1) else 1
    
    c.execute('''
        UPDATE settings SET shared_data = ? WHERE user_id = ?
    ''', (new_value, ADMIN_CHAT_ID))
    conn.commit()
    conn.close()
    
    await settings_access(update, context)


async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت ادمین‌ها"""
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT admin_id, admin_name FROM admins ORDER BY admin_name')
    admins = c.fetchall()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("➕ اضافه کردن ادمین", callback_data="add_admin")]]
    
    for admin_id, admin_name in admins:
        keyboard.append([
            InlineKeyboardButton(f"{admin_name} ({admin_id})", callback_data=f"viewadmin_{admin_id}"),
            InlineKeyboardButton("🗑", callback_data=f"deladmin_{admin_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_access")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👥 مدیریت ادمین‌ها\n\n"
        f"تعداد ادمین‌ها: {len(admins)}",
        reply_markup=reply_markup
    )


async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع افزودن ادمین"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ افزودن ادمین جدید\n\n"
        "لطفاً آیدی عددی ادمین را وارد کنید:\n"
        "برای لغو /cancel را بزنید."
    )
    
    return ADD_ADMIN_ID


async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت آیدی ادمین"""
    try:
        admin_id = int(update.message.text.strip())
        context.user_data['new_admin_id'] = admin_id
        
        await update.message.reply_text(
            "👤 لطفاً نام ادمین را وارد کنید:\n"
            "برای لغو /cancel را بزنید."
        )
        
        return ADD_ADMIN_NAME
        
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح وارد کنید!")
        return ADD_ADMIN_ID


async def receive_admin_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت نام ادمین"""
    admin_name = update.message.text.strip()
    admin_id = context.user_data.get('new_admin_id')
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO admins (admin_id, admin_name)
            VALUES (?, ?)
        ''', (admin_id, admin_name))
        conn.commit()
        await update.message.reply_text(f"✅ ادمین «{admin_name}» با موفقیت اضافه شد!")
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ این آیدی قبلاً ثبت شده است!")
    finally:
        conn.close()
    
    return ConversationHandler.END


async def delete_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف ادمین"""
    query = update.callback_query
    await query.answer()
    
    admin_id = int(query.data.split('_')[1])
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
    conn.commit()
    conn.close()
    
    await query.answer("✅ ادمین حذف شد!")
    await manage_admins(update, context)


async def settings_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیمات دیتابیس"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_CHAT_ID:
        await query.answer("⛔️ فقط ادمین اصلی دسترسی دارد!", show_alert=True)
        return
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT auto_backup, backup_interval FROM settings WHERE user_id = ?', (ADMIN_CHAT_ID,))
    result = c.fetchone()
    conn.close()
    
    auto_backup = result[0] if result else 0
    backup_interval = result[1] if result else 24
    
    auto_text = "روشن ✅" if auto_backup == 1 else "خاموش"
    
    keyboard = [
        [InlineKeyboardButton("📤 گرفتن بکاپ", callback_data="backup_export")],
        [InlineKeyboardButton("📥 وارد کردن بکاپ", callback_data="backup_import")],
        [InlineKeyboardButton(f"⏱️ بکاپ خودکار: {auto_text}", callback_data="toggle_auto_backup")],
        [InlineKeyboardButton("⚙️ تنظیم بکاپ خودکار", callback_data="config_auto_backup")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💾 مدیریت دیتابیس\n\n"
        f"بکاپ خودکار: {auto_text}\n"
        f"فاصله زمانی: هر {backup_interval} ساعت",
        reply_markup=reply_markup
    )


async def export_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال فایل بکاپ"""
    query = update.callback_query
    await query.answer("در حال آماده‌سازی بکاپ...")
    
    # ساخت نام فایل
    now = datetime.now()
    backup_filename = f"KasbBook_backup_{now.strftime('%Y-%m-%d_%H-%M')}.db"
    
    # ارسال فایل
    with open(DB_NAME, 'rb') as db_file:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=db_file,
            filename=backup_filename
        )
    
    await query.edit_message_text(
        "✅ بکاپ با موفقیت ارسال شد!\n\n"
        "برای بازگشت /start را بزنید."
    )


async def import_backup_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """درخواست فایل بکاپ"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📥 وارد کردن بکاپ\n\n"
        "لطفاً فایل بکاپ (.db) را ارسال کنید:\n"
        "برای لغو /cancel را بزنید."
    )
    
    return UPLOAD_BACKUP_FILE


async def receive_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت و بازیابی فایل بکاپ"""
    document = update.message.document
    
    if not document.file_name.endswith('.db'):
        await update.message.reply_text("❌ فقط فایل‌های .db مجاز هستند!")
        return UPLOAD_BACKUP_FILE
    
    # دانلود فایل
    file = await context.bot.get_file(document.file_id)
    temp_path = f"temp_backup_{datetime.now().timestamp()}.db"
    await file.download_to_drive(temp_path)
    
    # اعتبارسنجی SQLite
    try:
        conn = sqlite3.connect(temp_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = c.fetchall()
        conn.close()
        
        # بررسی جداول ضروری
        required_tables = ['transactions', 'categories', 'settings', 'admins']
        table_names = [t[0] for t in tables]
        
        if not all(t in table_names for t in required_tables):
            os.remove(temp_path)
            await update.message.reply_text("❌ فایل بکاپ معتبر نیست!")
            return UPLOAD_BACKUP_FILE
        
        # ذخیره بکاپ قبلی
        backup_old = f"KasbBook_old_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db"
        if os.path.exists(DB_NAME):
            os.rename(DB_NAME, backup_old)
        
        # جایگزینی فایل
        os.rename(temp_path, DB_NAME)
        
        await update.message.reply_text(
            "✅ بکاپ با موفقیت بازیابی شد!\n\n"
            f"بکاپ قبلی با نام {backup_old} ذخیره شد.\n\n"
            "برای بازگشت /start را بزنید."
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        await update.message.reply_text(f"❌ خطا در بازیابی: {str(e)}")
        return UPLOAD_BACKUP_FILE


async def toggle_auto_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت بکاپ خودکار"""
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT auto_backup FROM settings WHERE user_id = ?', (ADMIN_CHAT_ID,))
    result = c.fetchone()
    
    new_value = 0 if (result and result[0] == 1) else 1
    
    c.execute('''
        UPDATE settings SET auto_backup = ? WHERE user_id = ?
    ''', (new_value, ADMIN_CHAT_ID))
    conn.commit()
    conn.close()
    
    if new_value == 1:
        context.job_queue.run_repeating(
            auto_backup_job,
            interval=3600,  # هر ساعت چک می‌شود
            first=10,
            name=f'auto_backup_{ADMIN_CHAT_ID}'
        )
    else:
        jobs = context.job_queue.get_jobs_by_name(f'auto_backup_{ADMIN_CHAT_ID}')
        for job in jobs:
            job.schedule_removal()
    
    await settings_database(update, context)


async def config_auto_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع تنظیم بکاپ خودکار"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "⚙️ تنظیم بکاپ خودکار\n\n"
        "هر چند ساعت یکبار بکاپ گرفته شود؟\n"
        "لطفاً عدد ساعت را وارد کنید:\n"
        "برای لغو /cancel را بزنید."
    )
    
    return BACKUP_INTERVAL


async def receive_backup_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت فاصله زمانی بکاپ"""
    try:
        interval = int(update.message.text.strip())
        if interval < 1:
            raise ValueError
        
        context.user_data['backup_interval'] = interval
        
        await update.message.reply_text(
            "📬 آیدی مقصد ارسال بکاپ:\n\n"
            "لطفاً آیدی عددی را وارد کنید:\n"
            f"(پیش‌فرض: {ADMIN_CHAT_ID})\n"
            "برای لغو /cancel را بزنید."
        )
        
        return BACKUP_DEST
        
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح بزرگتر از صفر وارد کنید!")
        return BACKUP_INTERVAL


async def receive_backup_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت مقصد بکاپ"""
    try:
        destination = int(update.message.text.strip())
        interval = context.user_data.get('backup_interval')
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''
            UPDATE settings 
            SET backup_interval = ?, backup_destination = ?
            WHERE user_id = ?
        ''', (interval, destination, ADMIN_CHAT_ID))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ تنظیمات بکاپ خودکار ذخیره شد!\n\n"
            f"فاصله زمانی: هر {interval} ساعت\n"
            f"مقصد ارسال: {destination}\n\n"
            "برای بازگشت /start را بزنید."
        )
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک آیدی عددی معتبر وارد کنید!")
        return BACKUP_DEST


async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """تابع اجرای بکاپ خودکار"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT auto_backup, backup_interval, backup_destination 
        FROM settings WHERE user_id = ?
    ''', (ADMIN_CHAT_ID,))
    result = c.fetchone()
    conn.close()
    
    if not result or result[0] != 1:
        return
    
    auto_backup, interval, destination = result
    
    # بررسی زمان
    # برای سادگی، هر بار که این تابع اجرا می‌شود، بکاپ می‌گیرد
    # می‌توانید منطق پیچیده‌تری برای بررسی زمان اضافه کنید
    
    now = datetime.now()
    backup_filename = f"KasbBook_backup_{now.strftime('%Y-%m-%d_%H-%M')}.db"
    
    try:
        with open(DB_NAME, 'rb') as db_file:
            await context.bot.send_document(
                chat_id=destination or ADMIN_CHAT_ID,
                document=db_file,
                filename=backup_filename,
                caption="🔄 بکاپ خودکار"
            )
    except Exception as e:
        logger.error(f"Auto backup error: {e}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو عملیات"""
    if update.message:
        await update.message.reply_text(
            "❌ عملیات لغو شد.\n\n"
            "برای بازگشت /start را بزنید."
        )
    return ConversationHandler.END


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت callback های عمومی"""
    query = update.callback_query
    
    if query.data == "back_main":
        await show_main_menu(update, context)
    elif query.data == "back_day":
        await show_day_page(update, context)
    elif query.data.startswith("header_"):
        await query.answer()
    elif query.data == "locked":
        await query.answer("🔒 این نوع قفل است و قابل حذف نیست!", show_alert=True)

def main():
    """اجرای ربات"""
    init_db()

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN در فایل .env تنظیم نشده است")
    if not ADMIN_CHAT_ID:
        raise RuntimeError("ADMIN_CHAT_ID در فایل .env تنظیم نشده است")

    application = Application.builder().token(BOT_TOKEN).build()

    # انتخاب تاریخ
    date_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(request_gregorian_date, pattern=r"^date_gregorian$"),
            CallbackQueryHandler(request_jalali_date, pattern=r"^date_jalali$"),
        ],
        states={
            SELECT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True,
    )

    # افزودن تراکنش
    add_trans_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_transaction, pattern=r"^add_(income|expense|personal)$")
        ],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(select_category, pattern=r"^selcat_"),
                CallbackQueryHandler(add_new_category_start, pattern=r"^add_new_category$"),
            ],
            ADD_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_category_name)
            ],
            ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)
            ],
            ENTER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description),
                CallbackQueryHandler(skip_description, pattern=r"^skip_desc$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True,
    )

    # مدیریت دسته‌ها
    manage_cat_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_category_to_group, pattern=r"^add_cat_to_group$")
        ],
        states={
            ADD_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name_for_group)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True,
    )

    # مدیریت ادمین‌ها
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern=r"^add_admin$")],
        states={
            ADD_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_id)],
            ADD_ADMIN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True,
    )

    # وارد کردن بکاپ
    backup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(import_backup_request, pattern=r"^backup_import$")],
        states={
            UPLOAD_BACKUP_FILE: [MessageHandler(filters.Document.ALL, receive_backup_file)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True,
    )

    # تنظیم بکاپ خودکار
    config_backup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(config_auto_backup_start, pattern=r"^config_auto_backup$")],
        states={
            BACKUP_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_backup_interval)],
            BACKUP_DEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_backup_destination)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True,
    )

    # اضافه کردن handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(date_conv)
    application.add_handler(add_trans_conv)
    application.add_handler(manage_cat_conv)
    application.add_handler(admin_conv)
    application.add_handler(backup_conv)
    application.add_handler(config_backup_conv)

    # callback handlers
    application.add_handler(CallbackQueryHandler(menu_transactions, pattern=r"^menu_transactions$"))
    application.add_handler(CallbackQueryHandler(menu_reports, pattern=r"^menu_reports$"))
    application.add_handler(CallbackQueryHandler(menu_settings, pattern=r"^menu_settings$"))
    application.add_handler(CallbackQueryHandler(select_date_today, pattern=r"^date_today$"))
    application.add_handler(CallbackQueryHandler(view_transaction, pattern=r"^view_trans_"))
    application.add_handler(CallbackQueryHandler(delete_transaction, pattern=r"^delete_trans_"))
    application.add_handler(CallbackQueryHandler(report_monthly, pattern=r"^report_monthly$"))
    application.add_handler(CallbackQueryHandler(report_detailed, pattern=r"^report_detailed$"))
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

    # در نهایت همه چیزهای متفرقه
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("🚀 ربات KasbBook شروع به کار کرد!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
