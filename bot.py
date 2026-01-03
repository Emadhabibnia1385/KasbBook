# bot.py
# KasbBook - Telegram Finance Bot
# Requirements: Python 3.10+, python-telegram-bot v20+, pytz, jdatetime, python-dotenv, sqlite3

import os
import re
import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict

import pytz
import jdatetime
from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ------------------------
# Constants & Config
# ------------------------
PROJECT_NAME = "KasbBook"
DB_PATH = "KasbBook.db"
TZ = pytz.timezone("Asia/Tehran")

ACCESS_ADMIN_ONLY = "admin_only"
ACCESS_PUBLIC = "public"

INSTALLMENT_NAME = "قسط"

# Main reply keyboard
KB_MAIN = ReplyKeyboardMarkup(
    [["📌 تراکنش‌ها", "📊 گزارش‌ها"], ["⚙️ تنظیمات"]],
    resize_keyboard=True,
)

KB_SETTINGS = ReplyKeyboardMarkup(
    [["🧩 مدیریت نوع‌ها"], ["🛡 بخش ادمین"], ["🏠 منوی اصلی"]],
    resize_keyboard=True,
)

# Callback prefixes (keep short)
CB_TX = "tx"
CB_REP = "rp"
CB_SET = "st"
CB_ADM = "ad"
CB_CAT = "ct"

# ------------------------
# Logging
# ------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(PROJECT_NAME)

# ------------------------
# ENV
# ------------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID")
ADMIN_USERNAME_RAW = os.getenv("ADMIN_USERNAME")

if not BOT_TOKEN:
    raise RuntimeError("ENV BOT_TOKEN is not set")
if not ADMIN_CHAT_ID_RAW:
    raise RuntimeError("ENV ADMIN_CHAT_ID is not set")
if not ADMIN_USERNAME_RAW:
    raise RuntimeError("ENV ADMIN_USERNAME is not set")

try:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_RAW)
except ValueError:
    raise RuntimeError("ENV ADMIN_CHAT_ID must be an integer")

ADMIN_USERNAME = ADMIN_USERNAME_RAW.strip()
if ADMIN_USERNAME.startswith("@"):
    ADMIN_USERNAME = ADMIN_USERNAME[1:]
if not ADMIN_USERNAME:
    raise RuntimeError("ENV ADMIN_USERNAME is invalid/empty")

# ------------------------
# DB Helpers
# ------------------------
def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    with db_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings(
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admins(
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                added_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
                owner_user_id INTEGER NOT NULL,
                actor_user_id INTEGER NOT NULL,
                date_g TEXT NOT NULL,
                ttype TEXT NOT NULL CHECK(ttype IN ('work_in','work_out','personal_out')),
                category TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK(amount>=0),
                description TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date
                ON transactions(scope, owner_user_id, date_g);

            CREATE TABLE IF NOT EXISTS categories(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
                owner_user_id INTEGER NOT NULL,
                grp TEXT NOT NULL CHECK(grp IN ('work_in','work_out','personal_out')),
                name TEXT NOT NULL,
                is_locked INTEGER NOT NULL DEFAULT 0
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_cat_scope_owner_grp_name
                ON categories(scope, owner_user_id, grp, name);
            """
        )

        # defaults
        cur = conn.execute("SELECT v FROM settings WHERE k='access_mode'")
        if cur.fetchone() is None:
            conn.execute("INSERT INTO settings(k,v) VALUES('access_mode', ?)", (ACCESS_ADMIN_ONLY,))
        cur = conn.execute("SELECT v FROM settings WHERE k='share_enabled'")
        if cur.fetchone() is None:
            conn.execute("INSERT INTO settings(k,v) VALUES('share_enabled', '0')")

        conn.commit()


def get_setting(k: str) -> str:
    with db_conn() as conn:
        row = conn.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
        if not row:
            raise RuntimeError(f"Missing setting: {k}")
        return str(row["v"])


def set_setting(k: str, v: str) -> None:
    with db_conn() as conn:
        conn.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
        conn.commit()


def is_admin_user(user_id: int) -> bool:
    if user_id == ADMIN_CHAT_ID:
        return True
    with db_conn() as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone()
        return row is not None


def access_allowed(user_id: int) -> bool:
    access_mode = get_setting("access_mode")
    if access_mode == ACCESS_PUBLIC:
        return True
    # admin_only
    return is_admin_user(user_id)


def now_tehran_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def today_g_str() -> str:
    return datetime.now(TZ).date().strftime("%Y-%m-%d")


def g_to_j_str(g_yyyy_mm_dd: str) -> str:
    y, m, d = map(int, g_yyyy_mm_dd.split("-"))
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    return f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}"


def parse_date_to_g(text: str) -> Optional[str]:
    s = text.strip()
    # Gregorian: YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            date(y, mo, d)  # validate
            return f"{y:04d}-{mo:02d}-{d:02d}"
        except ValueError:
            return None

    # Jalali: YYYY/MM/DD
    m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        try:
            jy, jm, jd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            g = jdatetime.date(jy, jm, jd).togregorian()
            return g.strftime("%Y-%m-%d")
        except ValueError:
            return None

    return None


def resolve_scope_owner(user_id: int) -> Tuple[str, int]:
    """
    Returns (scope, owner_user_id) based on:
    - Non-admin in public: private, owner=self
    - Non-admin in admin_only: not allowed (caller should block)
    - Admin:
      - share_enabled=1 => shared, owner=ADMIN_CHAT_ID
      - share_enabled=0 => private, owner=self
    """
    if not is_admin_user(user_id):
        # only possible if public
        return ("private", user_id)

    share_enabled = get_setting("share_enabled")
    if share_enabled == "1":
        return ("shared", ADMIN_CHAT_ID)
    return ("private", user_id)


def ensure_installment(scope: str, owner_user_id: int) -> None:
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT id FROM categories
            WHERE scope=? AND owner_user_id=? AND grp='personal_out' AND name=?
            """,
            (scope, owner_user_id, INSTALLMENT_NAME),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO categories(scope, owner_user_id, grp, name, is_locked)
                VALUES(?, ?, 'personal_out', ?, 1)
                """,
                (scope, owner_user_id, INSTALLMENT_NAME),
            )
        else:
            conn.execute(
                "UPDATE categories SET is_locked=1 WHERE id=?",
                (row["id"],),
            )
        conn.commit()


# ------------------------
# Access Denied message
# ------------------------
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


async def deny_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = denied_text(user.id, user.username)
    if update.callback_query:
        q = update.callback_query
        try:
            await q.answer()
        except Exception:
            pass
        # try edit; if fails, send new
        try:
            await q.edit_message_text(text)
        except Exception:
            await update.effective_chat.send_message(text)
    else:
        await update.effective_chat.send_message(text)


# ------------------------
# UI Builders
# ------------------------
def ikb(rows: List[List[Tuple[str, str]]]) -> InlineKeyboardMarkup:
    """
    rows: [[(text, cbdata), ...], ...]
    """
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=cb) for (t, cb) in row] for row in rows]
    )


def tx_menu_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("➕ ثبت تراکنش", f"{CB_TX}:add")],
            [("📄 لیست امروز", f"{CB_TX}:list:today"), ("📄 لیست این ماه", f"{CB_TX}:list:month")],
            [("⬅️ بازگشت", f"{CB_TX}:back")],
        ]
    )


def reports_menu_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📅 خلاصه امروز", f"{CB_REP}:sum:today"), ("🗓 خلاصه این ماه", f"{CB_REP}:sum:month")],
            [("📆 بازه دلخواه", f"{CB_REP}:range")],
            [("⬅️ بازگشت", f"{CB_REP}:back")],
        ]
    )


def settings_menu_ikb(is_primary_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [("🧩 مدیریت نوع‌ها", f"{CB_SET}:cats")],
    ]
    if is_primary_admin:
        rows.append([("🛡 بخش ادمین", f"{CB_SET}:admin")])
    rows.append([("🏠 منوی اصلی", f"{CB_SET}:home")])
    return ikb(rows)


def admin_menu_ikb() -> InlineKeyboardMarkup:
    share_enabled = get_setting("share_enabled")
    share_txt = "روشن ✅" if share_enabled == "1" else "خاموش ❌"
    return ikb(
        [
            [("👥 مدیریت ادمین‌ها", f"{CB_ADM}:admins")],
            [(f"🔁 اشتراک اطلاعات بین ادمین‌ها: {share_txt}", f"{CB_ADM}:share")],
            [("⬅️ بازگشت", f"{CB_ADM}:back")],
        ]
    )


def admins_manage_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("➕ اضافه کردن ادمین", f"{CB_ADM}:add")],
            [("📋 لیست ادمین‌ها", f"{CB_ADM}:list")],
            [("⬅️ بازگشت", f"{CB_ADM}:back2")],
        ]
    )


def cats_manage_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("💰 درآمد کاری", f"{CB_CAT}:grp:work_in")],
            [("🏢 هزینه کاری", f"{CB_CAT}:grp:work_out")],
            [("👤 هزینه شخصی", f"{CB_CAT}:grp:personal_out")],
            [("⬅️ بازگشت", f"{CB_CAT}:back")],
        ]
    )


def grp_label(grp: str) -> str:
    return {
        "work_in": "💰 درآمد کاری",
        "work_out": "🏢 هزینه کاری",
        "personal_out": "👤 هزینه شخصی",
    }.get(grp, grp)


def ttype_label(ttype: str) -> str:
    return {
        "work_in": "درآمد کاری",
        "work_out": "هزینه کاری",
        "personal_out": "هزینه شخصی",
    }.get(ttype, ttype)


# ------------------------
# Conversations (States)
# ------------------------
# Add Transaction flow
TX_TTYPE, TX_DATE, TX_CAT_PICK, TX_CAT_NEW, TX_AMOUNT, TX_DESC = range(6)

# Report range flow
RP_RANGE_START, RP_RANGE_END = range(2)

# Admin add admin flow
ADM_ADD_UID, ADM_ADD_NAME = range(2)

# Category add flow
CAT_ADD_NAME = range(1)

# ------------------------
# Core Handlers
# ------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return

    await update.effective_chat.send_message(
        f"سلام! به {PROJECT_NAME} خوش آمدید.\n\nاز منو انتخاب کنید:",
        reply_markup=KB_MAIN,
    )


async def main_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return

    text = (update.message.text or "").strip()

    if text == "📌 تراکنش‌ها":
        await update.effective_chat.send_message(
            "📌 تراکنش‌ها:",
            reply_markup=tx_menu_ikb(),
        )
        return

    if text == "📊 گزارش‌ها":
        await update.effective_chat.send_message(
            "📊 گزارش‌ها:",
            reply_markup=reports_menu_ikb(),
        )
        return

    if text == "⚙️ تنظیمات":
        is_primary = (user.id == ADMIN_CHAT_ID)
        await update.effective_chat.send_message(
            "⚙️ تنظیمات:",
            reply_markup=settings_menu_ikb(is_primary),
        )
        return

    if text == "🏠 منوی اصلی":
        await update.effective_chat.send_message("🏠 منوی اصلی:", reply_markup=KB_MAIN)
        return

    if text == "🧩 مدیریت نوع‌ها":
        await update.effective_chat.send_message("🧩 مدیریت نوع‌ها:", reply_markup=cats_manage_ikb())
        return

    if text == "🛡 بخش ادمین":
        if user.id != ADMIN_CHAT_ID:
            await update.effective_chat.send_message("⛔ این بخش فقط برای ادمین اصلی فعال است.")
            return
        await update.effective_chat.send_message("🛡 بخش ادمین:", reply_markup=admin_menu_ikb())
        return

    await update.effective_chat.send_message("از منو استفاده کنید.", reply_markup=KB_MAIN)


# ------------------------
# Callback Router (Access gate first)
# ------------------------
async def cb_access_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return
    await q.answer()  # Always answer to avoid "loading..."


# ------------------------
# Transactions: Callbacks + Conversation
# ------------------------
async def tx_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    data = q.data or ""

    # ensure installment for current scope/owner where relevant
    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)

    parts = data.split(":")
    # tx:...
    if len(parts) < 2:
        await q.edit_message_text("خطا در داده ورودی.")
        return ConversationHandler.END

    action = parts[1]

    if action == "back":
        await q.edit_message_text("🏠 منوی اصلی", reply_markup=None)
        await update.effective_chat.send_message("🏠 منوی اصلی:", reply_markup=KB_MAIN)
        return ConversationHandler.END

    if action == "add":
        # start add transaction conversation
        context.user_data.clear()
        await q.edit_message_text(
            "نوع تراکنش را انتخاب کنید:",
            reply_markup=ikb(
                [
                    [("💰 درآمد کاری", f"{CB_TX}:tt:work_in")],
                    [("🏢 هزینه کاری", f"{CB_TX}:tt:work_out")],
                    [("👤 هزینه شخصی", f"{CB_TX}:tt:personal_out")],
                    [("⬅️ لغو", f"{CB_TX}:cancel")],
                ]
            ),
        )
        return TX_TTYPE

    if action == "cancel":
        context.user_data.clear()
        await q.edit_message_text("لغو شد.")
        return ConversationHandler.END

    if action == "tt":
        if len(parts) != 3:
            await q.edit_message_text("خطا.")
            return ConversationHandler.END
        ttype = parts[2]
        if ttype not in ("work_in", "work_out", "personal_out"):
            await q.edit_message_text("نوع نامعتبر.")
            return ConversationHandler.END

        context.user_data["tx_ttype"] = ttype

        # ask for date (text)
        today_g = today_g_str()
        today_j = g_to_j_str(today_g)
        await q.edit_message_text(
            "تاریخ را وارد کنید:\n"
            f"- امروز (میلادی): {today_g}\n"
            f"- امروز (جلالی): {today_j}\n\n"
            "فرمت مجاز:\n"
            "✅ میلادی: YYYY-MM-DD\n"
            "✅ جلالی: YYYY/MM/DD\n\n"
            "برای انتخاب امروز، فقط بنویسید: امروز",
            reply_markup=None,
        )
        return TX_DATE

    if action == "list":
        if len(parts) != 3:
            await q.edit_message_text("خطا.")
            return ConversationHandler.END
        which = parts[2]
        if which == "today":
            start = end = today_g_str()
            title = "📄 لیست امروز"
        else:
            # month range in Gregorian based on Tehran time
            today = datetime.now(TZ).date()
            start = date(today.year, today.month, 1).strftime("%Y-%m-%d")
            # next month start - 1 day
            if today.month == 12:
                nm = date(today.year + 1, 1, 1)
            else:
                nm = date(today.year, today.month + 1, 1)
            end = (nm - datetime.resolution).date().strftime("%Y-%m-%d")  # safe-ish
            # better end: last day of month
            # We'll compute last day properly:
            # (We avoid extra imports; do it cleanly)
            if today.month == 12:
                nm2 = date(today.year + 1, 1, 1)
            else:
                nm2 = date(today.year, today.month + 1, 1)
            end = (nm2 - datetime.timedelta(days=1)).strftime("%Y-%m-%d")  # type: ignore
            title = "📄 لیست این ماه"

        text = build_tx_list_text(scope, owner, start, end)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


def fetch_categories(scope: str, owner: int, grp: str) -> List[sqlite3.Row]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, is_locked
            FROM categories
            WHERE scope=? AND owner_user_id=? AND grp=?
            ORDER BY is_locked DESC, name COLLATE NOCASE
            """,
            (scope, owner, grp),
        ).fetchall()
        return list(rows)


async def tx_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if t == "امروز":
        g = today_g_str()
    else:
        g = parse_date_to_g(t)

    if not g:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید.")
        return TX_DATE

    context.user_data["tx_date_g"] = g

    ttype = context.user_data.get("tx_ttype")
    if not ttype:
        await update.effective_chat.send_message("خطا: نوع تراکنش مشخص نیست.")
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)
    cats = fetch_categories(scope, owner, ttype)

    # Build inline categories buttons
    rows = []
    for r in cats[:12]:
        rows.append([(f"{r['name']}", f"{CB_TX}:cat:{r['id']}")])
    if len(cats) > 12:
        # still stable: show "more" by letting user type category name (fallback)
        rows.append([("✍️ وارد کردن دستی نام نوع", f"{CB_TX}:cat_manual")])
    rows.append([("➕ افزودن نوع جدید", f"{CB_TX}:cat_new")])
    rows.append([("⬅️ لغو", f"{CB_TX}:cancel")])

    await update.effective_chat.send_message(
        f"نوع ({ttype_label(ttype)}) را انتخاب کنید:",
        reply_markup=ikb(rows),
    )
    return TX_CAT_PICK


async def tx_cat_pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    data = q.data or ""

    await q.answer()

    parts = data.split(":")
    if len(parts) < 2 or parts[0] != CB_TX:
        await q.edit_message_text("خطا.")
        context.user_data.clear()
        return ConversationHandler.END

    action = parts[1]

    if action == "cancel":
        context.user_data.clear()
        await q.edit_message_text("لغو شد.")
        return ConversationHandler.END

    if action == "cat_new":
        await q.edit_message_text("نام نوع جدید را وارد کنید:")
        return TX_CAT_NEW

    if action == "cat_manual":
        await q.edit_message_text("نام نوع را دستی وارد کنید:")
        return TX_CAT_NEW

    if action == "cat":
        if len(parts) != 3:
            await q.edit_message_text("خطا.")
            context.user_data.clear()
            return ConversationHandler.END
        cat_id = parts[2]
        try:
            cid = int(cat_id)
        except ValueError:
            await q.edit_message_text("نوع نامعتبر.")
            context.user_data.clear()
            return ConversationHandler.END

        scope, owner = resolve_scope_owner(user.id)
        ttype = context.user_data.get("tx_ttype")
        if not ttype:
            await q.edit_message_text("خطا.")
            context.user_data.clear()
            return ConversationHandler.END

        with db_conn() as conn:
            row = conn.execute(
                "SELECT name FROM categories WHERE id=? AND scope=? AND owner_user_id=? AND grp=?",
                (cid, scope, owner, ttype),
            ).fetchone()
        if not row:
            await q.edit_message_text("نوع پیدا نشد.")
            return TX_CAT_PICK

        context.user_data["tx_category"] = row["name"]
        await q.edit_message_text("مبلغ را وارد کنید (عدد صحیح، بدون اعشار):")
        return TX_AMOUNT

    await q.edit_message_text("دستور ناشناخته.")
    context.user_data.clear()
    return ConversationHandler.END


async def tx_cat_new_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message("نام نمی‌تواند خالی باشد. دوباره وارد کنید:")
        return TX_CAT_NEW

    # save category if not exists, and select it
    scope, owner = resolve_scope_owner(user.id)
    ttype = context.user_data.get("tx_ttype")
    if not ttype:
        await update.effective_chat.send_message("خطا: نوع تراکنش مشخص نیست.")
        context.user_data.clear()
        return ConversationHandler.END

    ensure_installment(scope, owner)

    with db_conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO categories(scope, owner_user_id, grp, name, is_locked)
                VALUES(?, ?, ?, ?, 0)
                """,
                (scope, owner, ttype, name),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass

    context.user_data["tx_category"] = name
    await update.effective_chat.send_message("مبلغ را وارد کنید (عدد صحیح، بدون اعشار):")
    return TX_AMOUNT


async def tx_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return ConversationHandler.END

    t = (update.message.text or "").strip().replace(",", "").replace("،", "")
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message("❌ مبلغ نامعتبر است. فقط عدد وارد کنید:")
        return TX_AMOUNT

    amount = int(t)
    context.user_data["tx_amount"] = amount
    await update.effective_chat.send_message("توضیحات (اختیاری) را وارد کنید یا /skip بزنید:")
    return TX_DESC


async def tx_desc_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await finalize_tx(update, context, description=None)


async def tx_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = (update.message.text or "").strip()
    return await finalize_tx(update, context, description=desc if desc else None)


async def finalize_tx(update: Update, context: ContextTypes.DEFAULT_TYPE, description: Optional[str]) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return ConversationHandler.END

    ttype = context.user_data.get("tx_ttype")
    date_g = context.user_data.get("tx_date_g")
    category = context.user_data.get("tx_category")
    amount = context.user_data.get("tx_amount")

    if not all([ttype, date_g, category]) or amount is None:
        await update.effective_chat.send_message("خطا: اطلاعات ناقص است.")
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)

    ts = now_tehran_str()
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO transactions(
                scope, owner_user_id, actor_user_id, date_g, ttype, category,
                amount, description, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (scope, owner, user.id, date_g, ttype, category, int(amount), description, ts, ts),
        )
        conn.commit()

    date_j = g_to_j_str(date_g)
    msg = (
        "✅ تراکنش ثبت شد.\n\n"
        f"📅 تاریخ: {date_g} | {date_j}\n"
        f"🔖 نوع: {ttype_label(ttype)}\n"
        f"🏷 دسته: {category}\n"
        f"💵 مبلغ: {amount}\n"
        f"📝 توضیح: {description or '-'}\n"
    )
    await update.effective_chat.send_message(msg, reply_markup=KB_MAIN)
    context.user_data.clear()
    return ConversationHandler.END


def build_tx_list_text(scope: str, owner: int, start_g: str, end_g: str) -> str:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, date_g, ttype, category, amount, description
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g BETWEEN ? AND ?
            ORDER BY date_g DESC, id DESC
            LIMIT 50
            """,
            (scope, owner, start_g, end_g),
        ).fetchall()

    if not rows:
        return "📄 هیچ تراکنشی پیدا نشد."

    lines = ["📄 <b>آخرین تراکنش‌ها (حداکثر 50)</b>\n"]
    for r in rows:
        dj = g_to_j_str(r["date_g"])
        desc = (r["description"] or "").strip()
        desc_part = f" — {desc}" if desc else ""
        lines.append(
            f"• <b>{r['date_g']}</b> ({dj}) | {ttype_label(r['ttype'])} | "
            f"{r['category']} | <b>{r['amount']}</b>{desc_part}"
        )
    return "\n".join(lines)


# ------------------------
# Reports: callbacks + conversation
# ------------------------
async def rep_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    data = q.data or ""
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)

    parts = data.split(":")
    if len(parts) < 2:
        await q.edit_message_text("خطا.")
        return ConversationHandler.END

    action = parts[1]
    if action == "back":
        await q.edit_message_text("🏠 منوی اصلی", reply_markup=None)
        await update.effective_chat.send_message("🏠 منوی اصلی:", reply_markup=KB_MAIN)
        return ConversationHandler.END

    if action == "sum":
        if len(parts) != 3:
            await q.edit_message_text("خطا.")
            return ConversationHandler.END
        which = parts[2]
        if which == "today":
            start = end = today_g_str()
            title = "📅 خلاصه امروز"
        else:
            today = datetime.now(TZ).date()
            start = date(today.year, today.month, 1).strftime("%Y-%m-%d")
            # last day of month
            if today.month == 12:
                nm = date(today.year + 1, 1, 1)
            else:
                nm = date(today.year, today.month + 1, 1)
            end = (nm - datetime.timedelta(days=1)).strftime("%Y-%m-%d")  # type: ignore
            title = "🗓 خلاصه این ماه"

        text = build_summary_text(scope, owner, start, end, title=title)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    if action == "range":
        context.user_data.clear()
        await q.edit_message_text(
            "تاریخ شروع را وارد کنید:\n"
            "✅ میلادی: YYYY-MM-DD\n"
            "✅ جلالی: YYYY/MM/DD"
        )
        return RP_RANGE_START

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


async def rep_range_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    g = parse_date_to_g(t)
    if not g:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید:")
        return RP_RANGE_START

    context.user_data["rp_start"] = g
    await update.effective_chat.send_message("تاریخ پایان را وارد کنید:")
    return RP_RANGE_END


async def rep_range_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    g2 = parse_date_to_g(t)
    if not g2:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید:")
        return RP_RANGE_END

    g1 = context.user_data.get("rp_start")
    if not g1:
        await update.effective_chat.send_message("خطا.")
        context.user_data.clear()
        return ConversationHandler.END

    if g2 < g1:
        g1, g2 = g2, g1

    scope, owner = resolve_scope_owner(user.id)
    text = build_summary_text(scope, owner, g1, g2, title="📆 گزارش بازه دلخواه")
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=KB_MAIN)
    context.user_data.clear()
    return ConversationHandler.END


def build_summary_text(scope: str, owner: int, start_g: str, end_g: str, title: str) -> str:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT ttype, SUM(amount) AS s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g BETWEEN ? AND ?
            GROUP BY ttype
            """,
            (scope, owner, start_g, end_g),
        ).fetchall()

    sums = {r["ttype"]: int(r["s"] or 0) for r in rows}
    w_in = sums.get("work_in", 0)
    w_out = sums.get("work_out", 0)
    p_out = sums.get("personal_out", 0)
    net = w_in - (w_out + p_out)

    sj1 = g_to_j_str(start_g)
    sj2 = g_to_j_str(end_g)

    return (
        f"<b>{title}</b>\n"
        f"📅 بازه: <b>{start_g}</b> ({sj1}) تا <b>{end_g}</b> ({sj2})\n\n"
        f"💰 درآمد کاری: <b>{w_in}</b>\n"
        f"🏢 هزینه کاری: <b>{w_out}</b>\n"
        f"👤 هزینه شخصی: <b>{p_out}</b>\n\n"
        f"📌 تراز (درآمد - هزینه‌ها): <b>{net}</b>"
    )


# ------------------------
# Settings & Admin callbacks
# ------------------------
async def settings_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    data = q.data or ""
    await q.answer()

    parts = data.split(":")
    if len(parts) < 2:
        await q.edit_message_text("خطا.")
        return ConversationHandler.END

    action = parts[1]

    if action == "home":
        await q.edit_message_text("🏠 منوی اصلی", reply_markup=None)
        await update.effective_chat.send_message("🏠 منوی اصلی:", reply_markup=KB_MAIN)
        return ConversationHandler.END

    if action == "cats":
        await q.edit_message_text("🧩 مدیریت نوع‌ها:", reply_markup=cats_manage_ikb())
        return ConversationHandler.END

    if action == "admin":
        if user.id != ADMIN_CHAT_ID:
            await q.edit_message_text("⛔ این بخش فقط برای ادمین اصلی فعال است.")
            return ConversationHandler.END
        await q.edit_message_text("🛡 بخش ادمین:", reply_markup=admin_menu_ikb())
        return ConversationHandler.END

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    data = q.data or ""
    await q.answer()

    if user.id != ADMIN_CHAT_ID:
        await q.edit_message_text("⛔ این بخش فقط برای ادمین اصلی فعال است.")
        return ConversationHandler.END

    parts = data.split(":")
    if len(parts) < 2:
        await q.edit_message_text("خطا.")
        return ConversationHandler.END

    action = parts[1]

    if action == "back":
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=settings_menu_ikb(True))
        return ConversationHandler.END

    if action == "admins":
        await q.edit_message_text("👥 مدیریت ادمین‌ها:", reply_markup=admins_manage_ikb())
        return ConversationHandler.END

    if action == "back2":
        await q.edit_message_text("🛡 بخش ادمین:", reply_markup=admin_menu_ikb())
        return ConversationHandler.END

    if action == "share":
        cur = get_setting("share_enabled")
        newv = "0" if cur == "1" else "1"
        set_setting("share_enabled", newv)
        await q.edit_message_text("✅ تنظیم شد.", reply_markup=admin_menu_ikb())
        return ConversationHandler.END

    if action == "add":
        context.user_data.clear()
        await q.edit_message_text("🆔 user_id عددی ادمین جدید را وارد کنید:")
        return ADM_ADD_UID

    if action == "list":
        text, markup = build_admins_list()
        await q.edit_message_text(text, reply_markup=markup)
        return ConversationHandler.END

    if action == "del":
        if len(parts) != 3:
            await q.edit_message_text("خطا.")
            return ConversationHandler.END
        try:
            uid = int(parts[2])
        except ValueError:
            await q.edit_message_text("آیدی نامعتبر.")
            return ConversationHandler.END

        with db_conn() as conn:
            conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
            conn.commit()
        text, markup = build_admins_list()
        await q.edit_message_text("✅ حذف شد.\n\n" + text, reply_markup=markup)
        return ConversationHandler.END

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


def build_admins_list() -> Tuple[str, InlineKeyboardMarkup]:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, name, added_at FROM admins ORDER BY added_at DESC"
        ).fetchall()

    lines = ["📋 <b>لیست ادمین‌ها</b>\n"]
    btn_rows = []
    if not rows:
        lines.append("— (خالی)")
    else:
        for r in rows[:25]:
            lines.append(f"• {r['name']} — <code>{r['user_id']}</code> — {r['added_at']}")
            btn_rows.append([("🗑 حذف", f"{CB_ADM}:del:{r['user_id']}")])

    btn_rows.append([("⬅️ بازگشت", f"{CB_ADM}:back2")])
    return "\n".join(lines), ikb(btn_rows)


async def adm_add_uid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
        await update.effective_chat.send_message("⛔ این بخش فقط برای ادمین اصلی فعال است.")
        context.user_data.clear()
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message("❌ فقط user_id عددی وارد کنید:")
        return ADM_ADD_UID

    uid = int(t)
    if uid == ADMIN_CHAT_ID:
        await update.effective_chat.send_message("ادمین اصلی نیازی به اضافه شدن ندارد. یک آیدی دیگر وارد کنید:")
        return ADM_ADD_UID

    context.user_data["new_admin_uid"] = uid
    await update.effective_chat.send_message("👤 نام ادمین را وارد کنید:")
    return ADM_ADD_NAME


async def adm_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
        await update.effective_chat.send_message("⛔ این بخش فقط برای ادمین اصلی فعال است.")
        context.user_data.clear()
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message("نام نمی‌تواند خالی باشد. دوباره وارد کنید:")
        return ADM_ADD_NAME

    uid = context.user_data.get("new_admin_uid")
    if not isinstance(uid, int):
        await update.effective_chat.send_message("خطا.")
        context.user_data.clear()
        return ConversationHandler.END

    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO admins(user_id, name, added_at)
            VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET name=excluded.name
            """,
            (uid, name, now_tehran_str()),
        )
        conn.commit()

    await update.effective_chat.send_message("✅ ادمین اضافه شد.", reply_markup=KB_MAIN)
    context.user_data.clear()
    return ConversationHandler.END


# ------------------------
# Categories management (callbacks + conversation)
# ------------------------
async def cats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    data = q.data or ""
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)

    parts = data.split(":")
    if len(parts) < 2:
        await q.edit_message_text("خطا.")
        return ConversationHandler.END

    action = parts[1]

    if action == "back":
        is_primary = (user.id == ADMIN_CHAT_ID)
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=settings_menu_ikb(is_primary))
        return ConversationHandler.END

    if action == "grp":
        if len(parts) != 3:
            await q.edit_message_text("خطا.")
            return ConversationHandler.END
        grp = parts[2]
        if grp not in ("work_in", "work_out", "personal_out"):
            await q.edit_message_text("گروه نامعتبر.")
            return ConversationHandler.END

        context.user_data.clear()
        context.user_data["cat_grp"] = grp

        text, markup = build_cat_list(scope, owner, grp)
        await q.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    if action == "add":
        # ct:add:<grp>
        if len(parts) != 3:
            await q.edit_message_text("خطا.")
            return ConversationHandler.END
        grp = parts[2]
        if grp not in ("work_in", "work_out", "personal_out"):
            await q.edit_message_text("گروه نامعتبر.")
            return ConversationHandler.END

        context.user_data.clear()
        context.user_data["cat_grp"] = grp
        await q.edit_message_text(f"نام نوع جدید برای «{grp_label(grp)}» را وارد کنید:")
        return CAT_ADD_NAME

    if action == "del":
        # ct:del:<id>
        if len(parts) != 3:
            await q.edit_message_text("خطا.")
            return ConversationHandler.END
        try:
            cid = int(parts[2])
        except ValueError:
            await q.edit_message_text("آیدی نامعتبر.")
            return ConversationHandler.END

        with db_conn() as conn:
            row = conn.execute(
                "SELECT grp, name, is_locked FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cid, scope, owner),
            ).fetchone()
            if not row:
                await q.edit_message_text("پیدا نشد.")
                return ConversationHandler.END
            if int(row["is_locked"]) == 1 and row["name"] == INSTALLMENT_NAME and row["grp"] == "personal_out":
                await q.edit_message_text("⛔ نوع «قسط» قفل است و حذف نمی‌شود.")
                return ConversationHandler.END

            conn.execute("DELETE FROM categories WHERE id=?", (cid,))
            conn.commit()

        grp = row["grp"]
        text, markup = build_cat_list(scope, owner, grp)
        await q.edit_message_text("✅ حذف شد.\n\n" + text, reply_markup=markup, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    if action == "back_grp":
        await q.edit_message_text("🧩 مدیریت نوع‌ها:", reply_markup=cats_manage_ikb())
        return ConversationHandler.END

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


def build_cat_list(scope: str, owner: int, grp: str) -> Tuple[str, InlineKeyboardMarkup]:
    rows = fetch_categories(scope, owner, grp)
    lines = [f"🧩 <b>{grp_label(grp)}</b>\n"]
    btn_rows = []

    if not rows:
        lines.append("— (خالی)")
    else:
        for r in rows[:30]:
            lock = "🔒 " if int(r["is_locked"]) == 1 else ""
            lines.append(f"• {lock}{r['name']}")
            if not (int(r["is_locked"]) == 1 and r["name"] == INSTALLMENT_NAME and grp == "personal_out"):
                btn_rows.append([("🗑 حذف", f"{CB_CAT}:del:{r['id']}")])

    btn_rows.append([("➕ افزودن", f"{CB_CAT}:add:{grp}")])
    btn_rows.append([("⬅️ بازگشت", f"{CB_CAT}:back_grp")])
    return "\n".join(lines), ikb(btn_rows)


async def cat_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message("نام نمی‌تواند خالی باشد. دوباره وارد کنید:")
        return CAT_ADD_NAME

    grp = context.user_data.get("cat_grp")
    if grp not in ("work_in", "work_out", "personal_out"):
        await update.effective_chat.send_message("خطا.")
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)

    with db_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO categories(scope, owner_user_id, grp, name, is_locked) VALUES(?,?,?,?,0)",
                (scope, owner, grp, name),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass

    # show list again
    text, markup = build_cat_list(scope, owner, grp)
    await update.effective_chat.send_message("✅ ثبت شد.\n\n" + text, reply_markup=markup, parse_mode=ParseMode.HTML)
    context.user_data.clear()
    return ConversationHandler.END


# ------------------------
# Fallback / Unknown
# ------------------------
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update, context)
        return
    await update.effective_chat.send_message("دستور نامعتبر است. از منو استفاده کنید.", reply_markup=KB_MAIN)


# ------------------------
# App Setup
# ------------------------
def build_app() -> Application:
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Access gate for callbacks (group 0 so it runs before others)
    app.add_handler(CallbackQueryHandler(cb_access_gate, pattern=r"^(tx|rp|st|ad|ct):",), group=0)

    # /start
    app.add_handler(CommandHandler("start", start), group=1)

    # Transactions conversation (inline-driven + message steps)
    tx_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(tx_cb, pattern=r"^tx:(add|list:today|list:month|back)$")],
        states={
            TX_TTYPE: [CallbackQueryHandler(tx_cb, pattern=r"^tx:(tt:(work_in|work_out|personal_out)|cancel)$")],
            TX_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_input)],
            TX_CAT_PICK: [CallbackQueryHandler(tx_cat_pick_cb, pattern=r"^tx:(cat:\d+|cat_new|cat_manual|cancel)$")],
            TX_CAT_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_cat_new_input)],
            TX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_amount_input)],
            TX_DESC: [
                CommandHandler("skip", tx_desc_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tx_desc_input),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(tx_cb, pattern=r"^tx:cancel$"),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
        name="tx_conv",
        persistent=False,
    )
    # Additional callback entry for list and other tx ops
    app.add_handler(CallbackQueryHandler(tx_cb, pattern=r"^tx:(list:(today|month)|back|cancel|tt:|add|cat:|cat_new|cat_manual)"), group=2)
    app.add_handler(tx_conv, group=3)

    # Reports conversation
    rep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(rep_cb, pattern=r"^rp:(sum:(today|month)|range|back)$")],
        states={
            RP_RANGE_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, rep_range_start)],
            RP_RANGE_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, rep_range_end)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="rep_conv",
        persistent=False,
    )
    app.add_handler(CallbackQueryHandler(rep_cb, pattern=r"^rp:(sum:(today|month)|range|back)$"), group=2)
    app.add_handler(rep_conv, group=3)

    # Settings callbacks
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^st:(cats|admin|home)$"), group=2)

    # Admin callbacks + conversation (only primary admin)
    adm_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_cb, pattern=r"^ad:(add)$")],
        states={
            ADM_ADD_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_uid)],
            ADM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_name)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="adm_conv",
        persistent=False,
    )
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^ad:(admins|share|list|del:\d+|back|back2|add)$"), group=2)
    app.add_handler(adm_conv, group=3)

    # Categories callbacks + conversation
    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:add:(work_in|work_out|personal_out)$")],
        states={CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_add_name)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="cat_conv",
        persistent=False,
    )
    app.add_handler(CallbackQueryHandler(cats_cb, pattern=r"^ct:(grp:(work_in|work_out|personal_out)|del:\d+|back|back_grp|add:(work_in|work_out|personal_out))$"), group=2)
    app.add_handler(cat_conv, group=3)

    # Main menu text router
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_router), group=10)

    # Unknown
    app.add_handler(MessageHandler(filters.ALL, unknown), group=99)

    return app


# ------------------------
# Run
# ------------------------
def main() -> None:
    app = build_app()
    logger.info("%s started. TZ=%s DB=%s", PROJECT_NAME, "Asia/Tehran", DB_PATH)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
