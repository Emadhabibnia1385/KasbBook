# bot.py
# KasbBook - Inline-only Finance Manager Telegram Bot (SQLite)
# Python 3.9+ | python-telegram-bot v21 | sqlite3 | pytz | jdatetime | python-dotenv
#

import os
import re
import io
import csv
import shutil
import sqlite3
import logging
import asyncio
import tempfile
import traceback
from contextlib import contextmanager
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict, Set, Iterator

import pytz
import jdatetime
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
    BotCommand,
    Document,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# Config / Constants
# =========================
PROJECT_NAME = "KasbBook"
DB_PATH = "KasbBook.db"
BACKUP_DIR = "backups"       # on-disk safety copies, used to undo a failed restore
TZ = pytz.timezone("Asia/Tehran")

# Telegram refuses very large inline keyboards, so every long list is paged.
DAILY_PAGE_SIZE = 8          # transaction rows per section in the daily list
CAT_PAGE_SIZE = 24           # categories per page
ADMIN_PAGE_SIZE = 20         # admins per page
TOP_CATEGORIES = 8           # rows per group in the category breakdown report

ACCESS_ADMIN_ONLY = "admin_only"   # default
ACCESS_PUBLIC = "public"

INSTALLMENT_NAME = "قسط"
RLM = "\u200f"       # RTL mark
ZWSP = "\u200b"      # non-empty invisible char

# Callback prefixes (short)
CB_M = "m"      # main
CB_ST = "st"    # settings
CB_AC = "ac"    # access
CB_AD = "ad"    # admin manage
CB_CT = "ct"    # categories
CB_TX = "tx"    # transaction flow + menus
CB_DL = "dl"    # daily list
CB_DTX = "dtx"  # tx detail/edit
CB_RP = "rp"    # reports
CB_DB = "db"    # database/backup

# Job name
JOB_BACKUP = "kasbbook_auto_backup"

# Global DB lock to reduce "database is locked"
DB_LOCK = asyncio.Lock()

# =========================
# ENV
# =========================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID")       # backward compatible (old name)
ADMIN_USERNAME_RAW = os.getenv("ADMIN_USERNAME")

# Optional new env (recommended)
PRIMARY_ADMIN_USER_ID_RAW = os.getenv("PRIMARY_ADMIN_USER_ID")

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

# Primary admin user_id (new env if provided; else fallback to ADMIN_CHAT_ID)
if PRIMARY_ADMIN_USER_ID_RAW:
    try:
        PRIMARY_ADMIN_USER_ID = int(PRIMARY_ADMIN_USER_ID_RAW)
    except ValueError:
        raise RuntimeError("ENV PRIMARY_ADMIN_USER_ID must be an integer")
else:
    PRIMARY_ADMIN_USER_ID = ADMIN_CHAT_ID  # backward compatible

ADMIN_USERNAME = (ADMIN_USERNAME_RAW or "").strip()
if ADMIN_USERNAME.startswith("@"):
    ADMIN_USERNAME = ADMIN_USERNAME[1:]
if not ADMIN_USERNAME:
    raise RuntimeError("ENV ADMIN_USERNAME is invalid/empty")

# =========================
# Logging
# =========================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(PROJECT_NAME)

# =========================
# DB helpers
# =========================
def db_conn() -> sqlite3.Connection:
    # timeout + WAL reduce lock errors (no schema/data change)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """
    Commit on success, roll back on failure, and always close.

    sqlite3's own `with conn` commits but never closes, so every call site used
    to leak an open handle until the garbage collector caught up.
    """
    conn = db_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def init_db() -> None:
    # A restore swaps the file underneath us, so drop anything cached from it.
    _SETTINGS_CACHE.clear()
    _INSTALLMENT_READY.clear()
    with db() as conn:
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

            -- Performance indexes (safe: no data change)
            CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date_type
                ON transactions(scope, owner_user_id, date_g, ttype);

            CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date_type_cat
                ON transactions(scope, owner_user_id, date_g, ttype, category);

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

        def _ensure_setting(key: str, default: str) -> None:
            if conn.execute("SELECT 1 FROM settings WHERE k=?", (key,)).fetchone() is None:
                conn.execute("INSERT INTO settings(k,v) VALUES(?,?)", (key, default))

        _ensure_setting("access_mode", ACCESS_ADMIN_ONLY)
        _ensure_setting("share_enabled", "0")

        # Backup settings
        _ensure_setting("backup_enabled", "0")                           # 0/1
        _ensure_setting("backup_target_type", "chat")                    # chat/channel
        _ensure_setting("backup_target_id", str(ADMIN_CHAT_ID))          # default destination chat id
        _ensure_setting("backup_interval_hours", "1")                    # integer hours

        conn.commit()

# Settings are read many times per update (access mode, sharing, backup config)
# and only ever change through set_setting, so they are safe to cache in-process.
_SETTINGS_CACHE: Dict[str, str] = {}

def get_setting(k: str) -> str:
    cached = _SETTINGS_CACHE.get(k)
    if cached is not None:
        return cached

    with db() as conn:
        r = conn.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    if not r:
        raise RuntimeError(f"Missing setting: {k}")

    val = str(r["v"])
    _SETTINGS_CACHE[k] = val
    return val

def set_setting(k: str, v: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, v),
        )
        conn.commit()
    _SETTINGS_CACHE[k] = v

def now_ts() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def today_g() -> str:
    return datetime.now(TZ).date().strftime("%Y-%m-%d")

def g_to_j(g_yyyy_mm_dd: str) -> str:
    y, m, d = map(int, g_yyyy_mm_dd.split("-"))
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    return f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}"

def parse_gregorian(s: str) -> Optional[str]:
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        date(y, mo, d)
        return f"{y:04d}-{mo:02d}-{d:02d}"
    except ValueError:
        return None

def parse_jalali_to_g(s: str) -> Optional[str]:
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", s)
    if not m:
        return None
    try:
        jy, jm, jd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        g = jdatetime.date(jy, jm, jd).togregorian()
        return g.strftime("%Y-%m-%d")
    except ValueError:
        return None

# =========================
# Jalali calendar
# =========================
# Transactions store a Gregorian date_g (ISO, so plain string comparison sorts
# correctly). Reports are Jalali, so every Jalali period is converted into a
# Gregorian [start, end) pair before it ever reaches SQL.
JMONTHS = [
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند",
]

def jmonth_name(jm: int) -> str:
    return JMONTHS[jm - 1] if 1 <= jm <= 12 else f"{jm:02d}"

def g_to_j_parts(g_yyyy_mm_dd: str) -> Tuple[int, int, int]:
    y, m, d = map(int, g_yyyy_mm_dd.split("-"))
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    return (jd.year, jd.month, jd.day)

def j_to_g_str(jy: int, jm: int, jd: int) -> str:
    return jdatetime.date(jy, jm, jd).togregorian().strftime("%Y-%m-%d")

def j_year_range_g(jy: int) -> Tuple[str, str]:
    """Gregorian [start, end) spanning a whole Jalali year."""
    return (j_to_g_str(jy, 1, 1), j_to_g_str(jy + 1, 1, 1))

def j_month_range_g(jy: int, jm: int) -> Tuple[str, str]:
    """Gregorian [start, end) spanning a single Jalali month."""
    start = j_to_g_str(jy, jm, 1)
    end = j_to_g_str(jy + 1, 1, 1) if jm == 12 else j_to_g_str(jy, jm + 1, 1)
    return (start, end)

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

# The locked "قسط" category is ensured once per (scope, owner) per process.
# Without this memo, every screen render fired its own write transaction.
_INSTALLMENT_READY: Set[Tuple[str, int]] = set()

def ensure_installment(scope: str, owner_user_id: int) -> None:
    key = (scope, owner_user_id)
    if key in _INSTALLMENT_READY:
        return

    with db() as conn:
        row = conn.execute(
            """
            SELECT id, is_locked FROM categories
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
        elif int(row["is_locked"]) != 1:
            conn.execute("UPDATE categories SET is_locked=1 WHERE id=?", (row["id"],))
        conn.commit()

    _INSTALLMENT_READY.add(key)

def fetch_cats(scope: str, owner: int, grp: str) -> List[sqlite3.Row]:
    with db() as conn:
        return list(
            conn.execute(
                """
                SELECT id, name, is_locked
                FROM categories
                WHERE scope=? AND owner_user_id=? AND grp=?
                ORDER BY is_locked DESC, name COLLATE NOCASE
                """,
                (scope, owner, grp),
            ).fetchall()
        )

# =========================
# UI helpers
# =========================
def rtl(text: str) -> str:
    return "\n".join([RLM + ln for ln in (text or "").splitlines()])

def ikb(rows: List[List[tuple]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=cb) for (t, cb) in row] for row in rows]
    )

async def safe_edit(q, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """
    Edit a callback message, tolerating Telegram's "message is not modified".

    Re-pressing an already-selected button (a mode that is already on, a menu
    that is already open) produces identical text and markup, which Telegram
    rejects with BadRequest. That is a no-op, not a failure.
    """
    try:
        await q.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        raise

def page_nav_row(prefix: str, page: int, total: int, per_page: int) -> List[InlineKeyboardButton]:
    """Prev/next row for a paged list; empty when everything fits on one page."""
    last = max(0, (total - 1) // per_page)
    if last == 0:
        return []

    row: List[InlineKeyboardButton] = []
    if page > 0:
        row.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"{prefix}{page - 1}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{last + 1}", callback_data=f"{CB_M}:noop"))
    if page < last:
        row.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"{prefix}{page + 1}"))
    return row

def fmt_num(n: int) -> str:
    return f"{int(n):,}"

# متن استارت (طبق درخواست شما تغییر نکند)
def start_text() -> str:
    return (
        "📊 KasbBook | مدیریت مالی کسب‌وکار\n\n"
        "با KasbBook می‌تونی:\n"
        "• درآمدها و هزینه‌ها رو ثبت کنی\n"
        "• گزارش روزانه، ماهانه و سالانه ببینی\n"
        "• پس‌انداز و سود واقعی کارت رو تحلیل کنی\n\n"
        "برای شروع از منوی زیر استفاده کن 👇\n\n"
        "🚀 شروع ربات با دستور: /start\n"
        "👨‍💻 Developer: @emadhabibnia"
    )

def main_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📌 تراکنش‌ها", f"{CB_M}:tx")],
            [("📊 گزارش", f"{CB_M}:report")],
            [("⚙️ تنظیمات", f"{CB_M}:st")],
        ]
    )

def tx_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("➕ اضافه کردن تراکنش جدید", f"{CB_TX}:new")],
            [("📄 لیست روزانه", f"{CB_DL}:pick")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )

def settings_menu(user_id: int) -> InlineKeyboardMarkup:
    rows = [[("🧩 مدیریت دسته‌ها", f"{CB_ST}:cats")]]
    if is_primary_admin(user_id):
        rows.append([("🔐 دسترسی ربات", f"{CB_ST}:access")])
        rows.append([("🗄 دیتابیس", f"{CB_ST}:db")])
    rows.append([("⬅️ بازگشت", f"{CB_M}:home")])
    return ikb(rows)

def access_menu(user_id: int) -> InlineKeyboardMarkup:
    mode = get_setting("access_mode")
    a = "✅" if mode == ACCESS_ADMIN_ONLY else ""
    p = "✅" if mode == ACCESS_PUBLIC else ""

    rows = [
        [(f"👑 حالت ادمین {a}", f"{CB_AC}:mode:{ACCESS_ADMIN_ONLY}")],
        [(f"🌐 حالت همگانی {p}", f"{CB_AC}:mode:{ACCESS_PUBLIC}")],
    ]

    if mode == ACCESS_ADMIN_ONLY and is_primary_admin(user_id):
        sh = get_setting("share_enabled")
        sh_txt = "روشن ✅" if sh == "1" else "خاموش ❌"
        rows.append([(f"🔁 اشتراک اطلاعات: {sh_txt}", f"{CB_AC}:share")])
        rows.append([("👥 مدیریت ادمین‌ها", f"{CB_AD}:panel")])

    rows.append([("⬅️ بازگشت", f"{CB_M}:home")])
    return ikb(rows)

def cats_root_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("💰 درآمد کاری", f"{CB_CT}:grp:work_in")],
            [("🏢 هزینه کاری", f"{CB_CT}:grp:work_out")],
            [("👤 هزینه شخصی", f"{CB_CT}:grp:personal_out")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
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

# =========================
# Conversation states
# =========================
ADM_ADD_UID, ADM_ADD_NAME = range(2)
CAT_ADD_NAME = 0
CAT_RENAME_NAME = 1

TX_DATE_MENU, TX_DATE_G, TX_DATE_J, TX_TTYPE, TX_CAT_PICK, TX_CAT_ADD_NAME, TX_AMOUNT, TX_DESC = range(8)
DL_DATE_MENU, DL_DATE_G, DL_DATE_J = range(3)
ED_AMOUNT, ED_DESC, ED_DATE_MENU, ED_DATE_G, ED_DATE_J = range(5)

DB_SET_TARGET_ID, DB_SET_INTERVAL, DB_RESTORE_WAIT_DOC = range(3)

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
    try:
        await update.effective_chat.send_message(ZWSP, reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return

    await update.effective_chat.send_message(
        rtl(start_text()),
        reply_markup=main_menu(),
    )

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
        await update.effective_chat.send_message(rtl("⛔ فقط ادمین اصلی."))
        context.user_data.clear()
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message(rtl("❌ فقط user_id عددی وارد کنید:"))
        return ADM_ADD_UID

    uid = int(t)
    if uid == PRIMARY_ADMIN_USER_ID:
        await update.effective_chat.send_message(rtl("ادمین اصلی را اضافه نکن. یک آیدی دیگر بده:"))
        return ADM_ADD_UID

    context.user_data["new_admin_uid"] = uid
    await update.effective_chat.send_message(rtl("👤 نام/یوزرنیم ادمین را وارد کنید (مثلاً @ali یا Ali):"))
    return ADM_ADD_NAME

async def adm_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_primary_admin(user.id):
        await update.effective_chat.send_message(rtl("⛔ فقط ادمین اصلی."))
        context.user_data.clear()
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message(rtl("نام خالی است. دوباره:"))
        return ADM_ADD_NAME

    uid = context.user_data.get("new_admin_uid")
    if not isinstance(uid, int):
        await update.effective_chat.send_message(rtl("خطا."))
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

    await update.effective_chat.send_message(
        rtl("✅ اضافه شد.\n\n👥 مدیریت ادمین‌ها:"),
        reply_markup=build_admin_panel_kb(),
    )
    context.user_data.clear()
    return ConversationHandler.END

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
        await update.effective_chat.send_message(rtl("نام خالی است. دوباره وارد کنید:"))
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
                await update.effective_chat.send_message(rtl("❌ این نام قبلاً وجود دارد."))
                return CAT_RENAME_NAME

    await update.effective_chat.send_message(
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

def build_cat_kb(scope: str, owner: int, grp: str, page: int = 0) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    cats = fetch_cats(scope, owner, grp)

    page = max(0, min(page, max(0, (len(cats) - 1) // CAT_PAGE_SIZE)))
    window = cats[page * CAT_PAGE_SIZE:(page + 1) * CAT_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton("➕ افزودن دسته", callback_data=f"{CB_CT}:add:{grp}")])

    for r in window:
        nm = r["name"]
        locked = int(r["is_locked"]) == 1
        is_install = (grp == "personal_out" and nm == INSTALLMENT_NAME and locked)

        if is_install:
            rows.append([InlineKeyboardButton(f"🔒 {nm}", callback_data=f"{CB_CT}:noop")])
        else:
            rows.append(
                [
                    InlineKeyboardButton(nm, callback_data=f"{CB_CT}:noop"),
                    InlineKeyboardButton("🗑 حذف", callback_data=f"{CB_CT}:del:{r['id']}"),
                    InlineKeyboardButton("✏️ ویرایش", callback_data=f"{CB_CT}:ren:{r['id']}"),
                ]
            )

    nav = page_nav_row(f"{CB_CT}:page:{grp}:", page, len(cats), CAT_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_ST}:cats")])
    return InlineKeyboardMarkup(rows)

async def cat_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message(rtl("نام خالی است. دوباره وارد کنید:"))
        return CAT_ADD_NAME

    grp = context.user_data.get("cat_grp")
    if grp not in ("work_in", "work_out", "personal_out"):
        await update.effective_chat.send_message(rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
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

    await update.effective_chat.send_message(
        rtl(f"✅ اضافه شد.\n\n🧩 {grp_label(grp)}"),
        reply_markup=build_cat_kb(scope, owner, grp),
    )
    context.user_data.clear()
    return ConversationHandler.END

# =========================
# Transaction flow
# =========================
def cat_pick_keyboard(scope: str, owner: int, grp: str, back_cb: str, page: int = 0) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    cats = fetch_cats(scope, owner, grp)

    page = max(0, min(page, max(0, (len(cats) - 1) // CAT_PAGE_SIZE)))
    window = cats[page * CAT_PAGE_SIZE:(page + 1) * CAT_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = []
    for r in window:
        rows.append([InlineKeyboardButton(r["name"], callback_data=f"{CB_TX}:cat:{r['id']}")])

    nav = page_nav_row(f"{CB_TX}:catp:", page, len(cats), CAT_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("➕ افزودن دسته جدید", callback_data=f"{CB_TX}:cat_add")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)

def tx_date_menu_kb(back_cb: str) -> InlineKeyboardMarkup:
    g = today_g()
    j = g_to_j(g)
    return ikb(
        [
            [(f"✅ امروز ({g} / {j})", f"{CB_TX}:date:today")],
            [("🗓 تاریخ میلادی", f"{CB_TX}:date:g")],
            [("🧿 تاریخ شمسی", f"{CB_TX}:date:j")],
            [("⬅️ بازگشت", back_cb)],
        ]
    )

def tx_ttype_kb(back_cb: str) -> InlineKeyboardMarkup:
    return ikb(
        [
            [("💰 درآمد کاری", f"{CB_TX}:tt:work_in")],
            [("🏢 هزینه کاری", f"{CB_TX}:tt:work_out")],
            [("👤 هزینه شخصی", f"{CB_TX}:tt:personal_out")],
            [("⬅️ بازگشت", back_cb)],
        ]
    )

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
    if ttype not in ("work_in", "work_out", "personal_out"):
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
    if ttype not in ("work_in", "work_out", "personal_out"):
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
        if ttype not in ("work_in", "work_out", "personal_out") or not gdate:
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
    if ttype not in ("work_in", "work_out", "personal_out") or not gdate:
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
    if ttype not in ("work_in", "work_out", "personal_out") or not gdate:
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

    if ttype not in ("work_in", "work_out", "personal_out") or not date_g_ or not category or amount is None:
        await update.effective_chat.send_message(rtl("خطا: اطلاعات ناقص است."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
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

    await update.effective_chat.send_message(rtl("✅ ثبت شد."), reply_markup=tx_menu())
    context.user_data.clear()
    return ConversationHandler.END

# =========================
# Daily list
# =========================
def daily_pick_menu() -> InlineKeyboardMarkup:
    g = today_g()
    j = g_to_j(g)
    return ikb(
        [
            [(f"✅ امروز ({g} / {j})", f"{CB_DL}:d:today")],
            [("🗓 وارد کردن تاریخ میلادی", f"{CB_DL}:d:g")],
            [("🧿 وارد کردن تاریخ شمسی", f"{CB_DL}:d:j")],
            [("⬅️ بازگشت", f"{CB_M}:tx")],
        ]
    )

# Optimized: single query instead of 4 queries
def _day_sums(scope: str, owner: int, gdate: str) -> Tuple[int, int, int, int]:
    with db() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN ttype='work_in' THEN amount ELSE 0 END),0) AS w_in,
                COALESCE(SUM(CASE WHEN ttype='work_out' THEN amount ELSE 0 END),0) AS w_out,
                COALESCE(SUM(CASE WHEN ttype='personal_out' AND category=? THEN amount ELSE 0 END),0) AS inst,
                COALESCE(SUM(CASE WHEN ttype='personal_out' AND category<>? THEN amount ELSE 0 END),0) AS p_non
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g=?
            """,
            (INSTALLMENT_NAME, INSTALLMENT_NAME, scope, owner, gdate),
        ).fetchone()

    return int(row["w_in"]), int(row["w_out"]), int(row["inst"]), int(row["p_non"])

def daily_list_text(scope: str, owner: int, gdate: str) -> str:
    ensure_installment(scope, owner)

    w_in, w_out, inst, p_non_install = _day_sums(scope, owner, gdate)
    net = w_in - w_out
    savings_operational = net - p_non_install
    savings_final = savings_operational - inst

    lines = [
        f"📅 {gdate}  |  {g_to_j(gdate)}",
        "",
        "📊 گزارش روز",
        f"💰 درآمد: {fmt_num(w_in)}",
        f"🏢 هزینه کاری: {fmt_num(w_out)}",
        f"➖ خالص کاری: {fmt_num(net)}",
        f"📄 قسط پرداختی: {fmt_num(inst)}",
        f"👤 هزینه شخصی(بدون قسط): {fmt_num(p_non_install)}",
        f"💾 پس‌انداز عملیاتی: {fmt_num(savings_operational)}",
        f"💾 پس‌انداز نهایی: {fmt_num(savings_final)}",
    ]
    return rtl("\n".join(lines))

def _short_add_labels() -> Tuple[str, str, str]:
    return ("درآمد جدید", "هزینه جدید", "شخصی جدید")

def _section_title(ttype: str) -> str:
    return {
        "work_in": "— لیست درآمد ها —",
        "work_out": "— لیست هزینه ها —",
        "personal_out": "— لیست هزینه های شخصی —",
    }[ttype]

SECTION_ORDER: Tuple[str, str, str] = ("work_in", "work_out", "personal_out")

def _section_counts(scope: str, owner: int, gdate: str) -> Dict[str, int]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT ttype, COUNT(*) AS c
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g=?
            GROUP BY ttype
            """,
            (scope, owner, gdate),
        ).fetchall()

    out = {t: 0 for t in SECTION_ORDER}
    for r in rows:
        out[str(r["ttype"])] = int(r["c"])
    return out

def normalize_pages(raw) -> Tuple[int, int, int]:
    """Coerce callback data / stored state into three page numbers."""
    try:
        p = [max(0, int(x)) for x in raw]
    except (TypeError, ValueError):
        return (0, 0, 0)
    while len(p) < 3:
        p.append(0)
    return (p[0], p[1], p[2])

def current_pages(context: ContextTypes.DEFAULT_TYPE) -> Tuple[int, int, int]:
    """
    Which page of the daily list the user is looking at.

    Kept in chat_data rather than user_data, because the edit conversations call
    user_data.clear() mid-flow and would otherwise reset the list to page 1.
    """
    return normalize_pages(context.chat_data.get("dl_pages", (0, 0, 0)))

def remember_pages(context: ContextTypes.DEFAULT_TYPE, pages) -> Tuple[int, int, int]:
    p = normalize_pages(pages)
    context.chat_data["dl_pages"] = p
    return p

def daily_back_cb(gdate: str, pages: Tuple[int, int, int]) -> str:
    """Back-to-daily-list callback that returns to the page the user was on."""
    p = normalize_pages(pages)
    return f"{CB_DL}:page:{gdate}:{p[0]}:{p[1]}:{p[2]}"

def daily_rows_kb(
    scope: str,
    owner: int,
    gdate: str,
    pages: Tuple[int, int, int] = (0, 0, 0),
) -> InlineKeyboardMarkup:
    """
    Daily list keyboard, paged per section.

    Each of the three sections carries its own page number, so a busy day can
    never build a keyboard Telegram refuses to render.
    """
    pages = normalize_pages(pages)
    counts = _section_counts(scope, owner, gdate)

    # Clamp first, so the page numbers baked into the nav callbacks stay valid.
    shown: List[int] = []
    for idx, ttype in enumerate(SECTION_ORDER):
        last = max(0, (counts[ttype] - 1) // DAILY_PAGE_SIZE)
        shown.append(min(pages[idx], last))

    def page_cb(section_idx: int, page: int) -> str:
        nxt = list(shown)
        nxt[section_idx] = page
        return f"{CB_DL}:page:{gdate}:{nxt[0]}:{nxt[1]}:{nxt[2]}"

    rows: List[List[InlineKeyboardButton]] = []

    a1, a2, a3 = _short_add_labels()
    rows.append(
        [
            InlineKeyboardButton(a1, callback_data=f"{CB_DL}:add:{gdate}:work_in"),
            InlineKeyboardButton(a2, callback_data=f"{CB_DL}:add:{gdate}:work_out"),
            InlineKeyboardButton(a3, callback_data=f"{CB_DL}:add:{gdate}:personal_out"),
        ]
    )

    for idx, ttype in enumerate(SECTION_ORDER):
        total = counts[ttype]
        page = shown[idx]
        last = max(0, (total - 1) // DAILY_PAGE_SIZE)

        title = _section_title(ttype)
        if total:
            title = f"{title} ({total})"
        rows.append([InlineKeyboardButton(title, callback_data=f"{CB_DL}:noop")])

        if total == 0:
            rows.append([InlineKeyboardButton("خالی", callback_data=f"{CB_DL}:noop")])
            continue

        with db() as conn:
            txs = conn.execute(
                """
                SELECT id, category, amount
                FROM transactions
                WHERE scope=? AND owner_user_id=? AND date_g=? AND ttype=?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (scope, owner, gdate, ttype, DAILY_PAGE_SIZE, page * DAILY_PAGE_SIZE),
            ).fetchall()

        for t in txs:
            open_cb = f"{CB_DTX}:open:{gdate}:{t['id']}"
            cat_txt = (t["category"] or "")[:24]
            amt_txt = fmt_num(int(t["amount"]))
            rows.append(
                [
                    InlineKeyboardButton(cat_txt, callback_data=open_cb),
                    InlineKeyboardButton(amt_txt, callback_data=open_cb),
                ]
            )

        if last > 0:
            nav: List[InlineKeyboardButton] = []
            if page > 0:
                nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=page_cb(idx, page - 1)))
            nav.append(InlineKeyboardButton(f"{page + 1}/{last + 1}", callback_data=f"{CB_DL}:noop"))
            if page < last:
                nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=page_cb(idx, page + 1)))
            rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_M}:tx")])
    return InlineKeyboardMarkup(rows)

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
            pages = remember_pages(context, (0, 0, 0))
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
        pages = remember_pages(context, data[3:6] if act == "page" else (0, 0, 0))
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

# =========================
# TX detail/edit
# =========================
def get_tx(scope: str, owner: int, tx_id: int) -> Optional[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM transactions WHERE id=? AND scope=? AND owner_user_id=?",
            (tx_id, scope, owner),
        ).fetchone()

def tx_detail_text(tx: sqlite3.Row, prefix: str = "") -> str:
    lines: List[str] = []
    if prefix:
        lines += [prefix, ""]
    lines += [
        "🧾 جزئیات تراکنش",
        "",
        f"📅 تاریخ (میلادی): {tx['date_g']}",
        f"📅 تاریخ (شمسی): {g_to_j(tx['date_g'])}",
        f"🔖 نوع: {ttype_label(tx['ttype'])}",
        f"🏷 دسته: {tx['category']}",
        f"💵 مبلغ: {fmt_num(int(tx['amount']))}",
        f"📝 توضیح: {(tx['description'] or '-').strip()}",
    ]
    return rtl("\n".join(lines))

def tx_view_kb(gdate: str, tx_id: int, back_cb: Optional[str] = None) -> InlineKeyboardMarkup:
    return ikb(
        [
            [("🏷 ویرایش دسته", f"{CB_DTX}:cat:{gdate}:{tx_id}")],
            [("💵 ویرایش مبلغ", f"{CB_DTX}:amt:{gdate}:{tx_id}")],
            [("📝 ویرایش توضیحات", f"{CB_DTX}:desc:{gdate}:{tx_id}")],
            [("📅 ویرایش تاریخ", f"{CB_DTX}:date:{gdate}:{tx_id}")],
            [("🗑 حذف", f"{CB_DTX}:del:{gdate}:{tx_id}")],
            [("⬅️ بازگشت", back_cb or f"{CB_DL}:show:{gdate}")],
        ]
    )

def tx_cat_change_kb(scope: str, owner: int, ttype: str, gdate: str, tx_id: int, page: int) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    cats = fetch_cats(scope, owner, ttype)

    page = max(0, min(page, max(0, (len(cats) - 1) // CAT_PAGE_SIZE)))
    window = cats[page * CAT_PAGE_SIZE:(page + 1) * CAT_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = []
    for c in window:
        rows.append(
            [InlineKeyboardButton(c["name"], callback_data=f"{CB_DTX}:setcat:{gdate}:{tx_id}:{c['id']}")]
        )

    nav = page_nav_row(f"{CB_DTX}:catp:{gdate}:{tx_id}:", page, len(cats), CAT_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_DTX}:open:{gdate}:{tx_id}")])
    return InlineKeyboardMarkup(rows)

def ed_date_menu_kb(gdate: str, tx_id: int) -> InlineKeyboardMarkup:
    g = today_g()
    return ikb(
        [
            [(f"✅ امروز ({g} / {g_to_j(g)})", f"{CB_DTX}:dset:{gdate}:{tx_id}:today")],
            [("🗓 تاریخ میلادی", f"{CB_DTX}:dset:{gdate}:{tx_id}:g")],
            [("🧿 تاریخ شمسی", f"{CB_DTX}:dset:{gdate}:{tx_id}:j")],
            [("↩️ انصراف", f"{CB_DTX}:open:{gdate}:{tx_id}")],
        ]
    )

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

    if act == "open":
        await safe_edit(q, tx_detail_text(tx), reply_markup=tx_view_kb(gdate, tx_id, back_cb))
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
        async with DB_LOCK:
            with db() as conn:
                conn.execute(
                    "DELETE FROM transactions WHERE id=? AND scope=? AND owner_user_id=?",
                    (tx_id, scope, owner),
                )
                conn.commit()

        pages = current_pages(context)
        await safe_edit(q, 
            daily_list_text(scope, owner, gdate),
            reply_markup=daily_rows_kb(scope, owner, gdate, pages),
        )
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
                        reply_markup=tx_view_kb(gdate, tx_id, back_cb),
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
            reply_markup=tx_view_kb(gdate, tx_id, back_cb),
        )
        return ConversationHandler.END

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=tx_view_kb(gdate, tx_id, back_cb))
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
    pages = remember_pages(context, (0, 0, 0))
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
# Reports (Jalali)
# =========================
# Every period below is converted into a Gregorian [start, end) pair before it
# reaches SQL, because transactions store an ISO date_g that compares as text.

def sums_for_range(
    scope: str,
    owner: int,
    start_g: Optional[str] = None,
    end_g_exclusive: Optional[str] = None,
) -> Dict[str, int]:
    """Totals for a period; omit both bounds for an all-time total."""
    ensure_installment(scope, owner)

    where = "scope=? AND owner_user_id=?"
    params: List = [INSTALLMENT_NAME, INSTALLMENT_NAME, scope, owner]
    if start_g is not None:
        where += " AND date_g>=?"
        params.append(start_g)
    if end_g_exclusive is not None:
        where += " AND date_g<?"
        params.append(end_g_exclusive)

    with db() as conn:
        row = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN ttype='work_in' THEN amount ELSE 0 END),0) AS income,
                COALESCE(SUM(CASE WHEN ttype='work_out' THEN amount ELSE 0 END),0) AS work_out,
                COALESCE(SUM(CASE WHEN ttype='personal_out' AND category=? THEN amount ELSE 0 END),0) AS installment,
                COALESCE(SUM(CASE WHEN ttype='personal_out' AND category<>? THEN amount ELSE 0 END),0) AS personal
            FROM transactions
            WHERE {where}
            """,
            tuple(params),
        ).fetchone()

    income = int(row["income"])
    work_out = int(row["work_out"])
    installment = int(row["installment"])
    personal = int(row["personal"])

    net = income - work_out
    savings_operational = net - personal
    savings_final = savings_operational - installment

    return {
        "income": income,
        "work_out": work_out,
        "net": net,
        "installment": installment,
        "personal": personal,
        "savings_operational": savings_operational,
        "savings_final": savings_final,
    }

def sums_all(scope: str, owner: int) -> Dict[str, int]:
    return sums_for_range(scope, owner)

def report_lines(title: str, s: Dict[str, int]) -> str:
    lines = [
        title,
        "",
        f"💰 درآمد: {fmt_num(s['income'])}",
        f"🏢 هزینه کاری: {fmt_num(s['work_out'])}",
        f"➖ خالص کاری: {fmt_num(s['net'])}",
        "",
        f"📄 قسط پرداختی: {fmt_num(s['installment'])}",
        f"👤 هزینه شخصی (بدون قسط): {fmt_num(s['personal'])}",
        "",
        f"💾 پس‌انداز عملیاتی: {fmt_num(s['savings_operational'])}",
        f"💾 پس‌انداز نهایی: {fmt_num(s['savings_final'])}",
    ]
    return rtl("\n".join(lines))

def jalali_years_with_data(scope: str, owner: int) -> List[int]:
    """Jalali years that contain transactions, newest first."""
    with db() as conn:
        row = conn.execute(
            """
            SELECT MIN(date_g) AS lo, MAX(date_g) AS hi
            FROM transactions
            WHERE scope=? AND owner_user_id=?
            """,
            (scope, owner),
        ).fetchone()

    if not row or not row["lo"]:
        return []

    lo_year = g_to_j_parts(str(row["lo"]))[0]
    hi_year = g_to_j_parts(str(row["hi"]))[0]
    return list(range(hi_year, lo_year - 1, -1))

# --- period spec: how a report range travels inside callback data ----------
# "a" = all time | "y:<jy>" = one Jalali year | "m:<jy>:<jm>" = one Jalali month

def parse_period(parts: List[str]) -> Tuple[str, str, Optional[str], Optional[str]]:
    """(spec, title, start_g, end_g_exclusive) for a period spec."""
    kind = parts[0] if parts else "a"

    if kind == "y" and len(parts) >= 2:
        jy = int(parts[1])
        start, end = j_year_range_g(jy)
        return (f"y:{jy}", f"سال {jy}", start, end)

    if kind == "m" and len(parts) >= 3:
        jy, jm = int(parts[1]), int(parts[2])
        start, end = j_month_range_g(jy, jm)
        return (f"m:{jy}:{jm:02d}", f"{jmonth_name(jm)} {jy}", start, end)

    return ("a", "کلی", None, None)

def period_extra_kb(spec: str) -> List[List[tuple]]:
    return [
        [("🏷 تفکیک دسته‌ها", f"{CB_RP}:bd:{spec}")],
        [("📥 خروجی CSV", f"{CB_RP}:csv:{spec}")],
    ]

def report_root_kb(years: List[int]) -> InlineKeyboardMarkup:
    rows: List[List[tuple]] = period_extra_kb("a")

    buf: List[tuple] = []
    for y in years:
        buf.append((str(y), f"{CB_RP}:y:{y}"))
        if len(buf) == 3:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)

    rows.append([("⬅️ بازگشت", f"{CB_M}:home")])
    return ikb(rows)

def report_year_kb(jy: int) -> InlineKeyboardMarkup:
    rows: List[List[tuple]] = period_extra_kb(f"y:{jy}")

    buf: List[tuple] = []
    for jm in range(1, 13):
        buf.append((jmonth_name(jm), f"{CB_RP}:m:{jy}:{jm:02d}"))
        if len(buf) == 3:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)

    rows.append([("⬅️ بازگشت", f"{CB_RP}:root")])
    return ikb(rows)

def report_month_kb(jy: int, jm: int) -> InlineKeyboardMarkup:
    rows: List[List[tuple]] = period_extra_kb(f"m:{jy}:{jm:02d}")
    rows.append([("⬅️ بازگشت", f"{CB_RP}:y:{jy}")])
    return ikb(rows)

def back_to_period_kb(spec: str) -> InlineKeyboardMarkup:
    if spec == "a":
        return ikb([[("⬅️ بازگشت", f"{CB_RP}:root")]])
    return ikb([[("⬅️ بازگشت", f"{CB_RP}:{spec}")]])

# --- category breakdown ----------------------------------------------------
def category_breakdown(
    scope: str,
    owner: int,
    start_g: Optional[str],
    end_g_exclusive: Optional[str],
) -> Dict[str, List[Tuple[str, int, int]]]:
    """Per-type category totals as (name, sum, count), biggest first."""
    where = "scope=? AND owner_user_id=?"
    params: List = [scope, owner]
    if start_g is not None:
        where += " AND date_g>=?"
        params.append(start_g)
    if end_g_exclusive is not None:
        where += " AND date_g<?"
        params.append(end_g_exclusive)

    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT ttype, category, SUM(amount) AS total, COUNT(*) AS cnt
            FROM transactions
            WHERE {where}
            GROUP BY ttype, category
            ORDER BY total DESC
            """,
            tuple(params),
        ).fetchall()

    out: Dict[str, List[Tuple[str, int, int]]] = {t: [] for t in SECTION_ORDER}
    for r in rows:
        out.setdefault(str(r["ttype"]), []).append(
            (str(r["category"]), int(r["total"]), int(r["cnt"]))
        )
    return out

def breakdown_text(title: str, data: Dict[str, List[Tuple[str, int, int]]]) -> str:
    lines: List[str] = [f"🏷 تفکیک دسته‌ها — {title}"]

    for ttype in SECTION_ORDER:
        items = data.get(ttype, [])
        lines += ["", grp_label(ttype)]
        if not items:
            lines.append("— خالی —")
            continue

        grand = sum(t for _, t, _ in items)
        for name, total, cnt in items[:TOP_CATEGORIES]:
            share = round(total * 100 / grand) if grand else 0
            lines.append(f"• {name}: {fmt_num(total)}  ({share}% — {cnt} مورد)")

        rest = items[TOP_CATEGORIES:]
        if rest:
            lines.append(f"• سایر ({len(rest)} دسته): {fmt_num(sum(t for _, t, _ in rest))}")

    return rtl("\n".join(lines))

# --- CSV export ------------------------------------------------------------
def make_csv_bytes(
    scope: str,
    owner: int,
    start_g: Optional[str],
    end_g_exclusive: Optional[str],
) -> bytes:
    where = "scope=? AND owner_user_id=?"
    params: List = [scope, owner]
    if start_g is not None:
        where += " AND date_g>=?"
        params.append(start_g)
    if end_g_exclusive is not None:
        where += " AND date_g<?"
        params.append(end_g_exclusive)

    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, date_g, ttype, category, amount, description, created_at
            FROM transactions
            WHERE {where}
            ORDER BY date_g ASC, id ASC
            """,
            tuple(params),
        ).fetchall()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["شناسه", "تاریخ میلادی", "تاریخ شمسی", "نوع", "دسته", "مبلغ", "توضیح", "ثبت شده در"])
    for r in rows:
        w.writerow(
            [
                r["id"],
                r["date_g"],
                g_to_j(str(r["date_g"])),
                ttype_label(str(r["ttype"])),
                r["category"],
                int(r["amount"]),
                (r["description"] or ""),
                r["created_at"],
            ]
        )

    # BOM so Excel detects UTF-8 and renders Persian correctly.
    return ("\ufeff" + buf.getvalue()).encode("utf-8")

def csv_filename(spec: str) -> str:
    tag = spec.replace(":", "-")
    ts = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
    return f"kasbbook_{tag}_{ts}.csv"

# --- report screens --------------------------------------------------------
async def report_root(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return

    scope, owner = resolve_scope_owner(user.id)
    s = sums_all(scope, owner)
    years = jalali_years_with_data(scope, owner)

    text = report_lines("📊 گزارش کلی", s)
    kb = report_root_kb(years)

    if edit and update.callback_query:
        await safe_edit(update.callback_query, text, reply_markup=kb)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb)

async def report_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    parts = (q.data or "").split(":")
    act = parts[1]

    scope, owner = resolve_scope_owner(user.id)

    if act == "root":
        await report_root(update, context, edit=True)
        return

    if act == "y":
        jy = int(parts[2])
        start, end = j_year_range_g(jy)
        s = sums_for_range(scope, owner, start, end)
        await safe_edit(q, report_lines(f"📊 گزارش سال {jy}", s), reply_markup=report_year_kb(jy))
        return

    if act == "m":
        jy, jm = int(parts[2]), int(parts[3])
        start, end = j_month_range_g(jy, jm)
        s = sums_for_range(scope, owner, start, end)
        title = f"📊 گزارش {jmonth_name(jm)} {jy}"
        await safe_edit(q, report_lines(title, s), reply_markup=report_month_kb(jy, jm))
        return

    if act == "bd":
        spec, title, start, end = parse_period(parts[2:])
        data = category_breakdown(scope, owner, start, end)
        await safe_edit(q, breakdown_text(title, data), reply_markup=back_to_period_kb(spec))
        return

    if act == "csv":
        spec, title, start, end = parse_period(parts[2:])
        payload = make_csv_bytes(scope, owner, start, end)

        bio = io.BytesIO(payload)
        fname = csv_filename(spec)
        bio.name = fname

        await context.bot.send_document(
            chat_id=user.id,
            document=bio,
            filename=fname,
            caption=rtl(f"📥 خروجی تراکنش‌ها — {title}"),
        )
        return

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=main_menu())

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

def backup_filename() -> str:
    ts = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
    return f"kasbbook_backup_{ts}.db"

def make_backup_bytes() -> bytes:
    """Consistent snapshot of the live DB via SQLite's own backup API."""
    fd, tmp_path = tempfile.mkstemp(prefix="kasbbook_backup_", suffix=".db")
    os.close(fd)

    try:
        src = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        try:
            dst = sqlite3.connect(tmp_path, timeout=30, check_same_thread=False)
            try:
                src.backup(dst)
                dst.commit()
            finally:
                dst.close()
        finally:
            src.close()

        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

def db_sidecars() -> List[str]:
    """WAL/SHM files that belong to the current DB and must not outlive it."""
    return [DB_PATH + "-wal", DB_PATH + "-shm"]

def drop_sidecars() -> None:
    for path in db_sidecars():
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            logger.warning("Could not remove %s: %s", path, e)

def save_disk_backup(name: str, data: bytes) -> Optional[str]:
    """Keep a copy on disk so a failed restore can be rolled back locally."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        path = os.path.join(BACKUP_DIR, name)
        with open(path, "wb") as f:
            f.write(data)
        return path
    except OSError as e:
        logger.warning("Could not write on-disk backup: %s", e)
        return None

def validate_backup_file(path: str) -> Tuple[bool, str]:
    """
    Confirm an uploaded file really is a KasbBook database.

    Restoring overwrites the live DB, so this runs *before* anything is moved.
    """
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error:
        return (False, "فایل قابل باز کردن نیست.")

    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            return (False, "ساختار فایل سالم نیست (integrity_check رد شد).")

        names = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = {"transactions", "categories", "settings"} - names
        if missing:
            return (False, "این فایل دیتابیس KasbBook نیست. جدول‌های نبود: " + "، ".join(sorted(missing)))

        conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
        conn.execute("SELECT COUNT(*) FROM categories").fetchone()
    except sqlite3.DatabaseError as e:
        return (False, f"فایل معتبر نیست: {e}")
    finally:
        conn.close()

    return (True, "")

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
        await update.effective_chat.send_message(rtl("⛔ فقط ادمین اصلی."))
        context.user_data.clear()
        return ConversationHandler.END

    text = (update.message.text or "").strip()

    if text.startswith("/skip"):
        set_setting("backup_target_id", str(ADMIN_CHAT_ID))
        await update.effective_chat.send_message(rtl("✅ مقصد روی آیدی پیش‌فرض ادمین اصلی تنظیم شد."))
    else:
        if not re.fullmatch(r"-?\d+", text):
            await update.effective_chat.send_message(rtl("❌ فقط آیدی عددی وارد کنید (مثلاً 123 یا -100...)."))
            return DB_SET_TARGET_ID
        set_setting("backup_target_id", text)
        await update.effective_chat.send_message(rtl("✅ مقصد بکاپ ثبت شد."))

    schedule_backup_job(context.application)
    await update.effective_chat.send_message(rtl(db_menu_text()), reply_markup=db_menu_kb())
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
        await update.effective_chat.send_message(rtl("⛔ فقط ادمین اصلی."))
        context.user_data.clear()
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message(rtl("❌ فقط عدد وارد کنید (ساعت):"))
        return DB_SET_INTERVAL

    hours = max(1, int(t))
    set_setting("backup_interval_hours", str(hours))
    schedule_backup_job(context.application)
    await update.effective_chat.send_message(rtl("✅ فاصله بکاپ خودکار ثبت شد."))
    await update.effective_chat.send_message(rtl(db_menu_text()), reply_markup=db_menu_kb())
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
        await update.effective_chat.send_message(rtl("⛔ فقط ادمین اصلی."))
        return ConversationHandler.END

    msg = update.message
    if not msg or not msg.document:
        await update.effective_chat.send_message(rtl("❌ لطفاً یک فایل .db ارسال کنید."))
        return DB_RESTORE_WAIT_DOC

    doc: Document = msg.document
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".db"):
        await update.effective_chat.send_message(rtl("❌ فقط فایل با پسوند .db قابل قبول است."))
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
        await update.effective_chat.send_message(
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
        await update.effective_chat.send_message(
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
        await update.effective_chat.send_message(rtl(msg))
        return ConversationHandler.END

    await update.effective_chat.send_message(
        rtl(f"✅ بکاپ با موفقیت وارد شد.\n\n🧯 نسخه قبلی: {rollback_path}")
    )

    schedule_backup_job(context.application)
    await update.effective_chat.send_message(rtl(db_menu_text()), reply_markup=db_menu_kb())
    return ConversationHandler.END

# =========================
# Cancel / error handling
# =========================
async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Escape hatch out of any conversation."""
    context.user_data.clear()
    if not access_allowed(update.effective_user.id):
        await deny(update)
        return ConversationHandler.END

    await update.effective_chat.send_message(rtl("↩️ لغو شد."), reply_markup=main_menu())
    return ConversationHandler.END

# Repeated identical failures should not spam the admin's chat.
_LAST_ERROR_SIG: List[str] = []

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error

    # Re-pressing a button that produces the same screen is not an error.
    if isinstance(err, BadRequest) and "not modified" in str(err).lower():
        return

    logger.error("Unhandled error while processing update", exc_info=err)

    if isinstance(update, Update):
        try:
            if update.callback_query:
                await update.callback_query.answer("خطایی رخ داد. دوباره تلاش کنید.", show_alert=True)
            elif update.effective_chat:
                await update.effective_chat.send_message(
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

# =========================
# Build app (Handlers OK)
# =========================
def build_app() -> Application:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    async def _post_init(application: Application) -> None:
        await setup_commands(application)
        schedule_backup_job(application)

    app.post_init = _post_init

    # Every conversation can be escaped with /start or /cancel.
    common_fallbacks = [CommandHandler("start", start), CommandHandler("cancel", cancel_cmd)]

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # Main
    app.add_handler(CallbackQueryHandler(main_cb, pattern=r"^m:(home|tx|st|report|noop)$"))

    # Settings / Access
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^st:(cats|access|db)$"))
    app.add_handler(CallbackQueryHandler(access_cb, pattern=r"^ac:(mode:(admin_only|public)|share)$"))

    async def ac_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        user = update.effective_user
        if not access_allowed(user.id):
            await deny(update)
            return
        await q.answer()
        if is_primary_admin(user.id):
            await safe_edit(q, rtl("🔐 دسترسی ربات:"), reply_markup=access_menu(user.id))
        else:
            await safe_edit(q, rtl(start_text()), reply_markup=main_menu())

    app.add_handler(CallbackQueryHandler(ac_noop, pattern=r"^ac:noop$"))

    # Admin panel (view/page/delete) - "add" is a conversation entry point
    app.add_handler(
        CallbackQueryHandler(
            admin_panel_cb,
            pattern=r"^ad:(panel|noop|page:\d+|del:\d+|delok:\d+)$",
        )
    )

    adm_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_panel_cb, pattern=r"^ad:add$")],
        states={
            ADM_ADD_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_uid)],
            ADM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_name)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(adm_conv)

    # Categories (view/page/delete) - "add"/"rename" are conversation entry points
    app.add_handler(
        CallbackQueryHandler(
            cats_cb,
            pattern=(
                r"^ct:(grp:(work_in|work_out|personal_out)"
                r"|page:(work_in|work_out|personal_out):\d+"
                r"|del:\d+|delok:\d+|noop)$"
            ),
        )
    )

    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:add:(work_in|work_out|personal_out)$")],
        states={CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_add_name)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(cat_conv)

    cat_rename_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:ren:\d+$")],
        states={
            CAT_RENAME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_rename_name)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(cat_rename_conv)

    # Daily list (date picker conversation)
    dl_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(daily_cb, pattern=r"^dl:pick$")],
        states={
            DL_DATE_MENU: [CallbackQueryHandler(daily_cb, pattern=r"^dl:d:(today|g|j)$")],
            DL_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, dl_date_g_input)],
            DL_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, dl_date_j_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(dl_conv)

    # Daily non-conversation callbacks (including per-section paging)
    app.add_handler(
        CallbackQueryHandler(
            daily_cb,
            pattern=(
                r"^dl:(d:(today|g|j)"
                r"|show:\d{4}-\d{2}-\d{2}"
                r"|page:\d{4}-\d{2}-\d{2}:\d+:\d+:\d+"
                r"|noop)$"
            ),
        )
    )

    # Transaction creation conversation
    tx_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(tx_entry_from_menu, pattern=r"^tx:new$"),
            CallbackQueryHandler(tx_entry_from_daily, pattern=r"^dl:add:\d{4}-\d{2}-\d{2}:(work_in|work_out|personal_out)$"),
        ],
        states={
            TX_DATE_MENU: [CallbackQueryHandler(tx_date_menu_cb, pattern=r"^tx:date:(today|g|j)$")],
            TX_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_g_input)],
            TX_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_j_input)],
            TX_TTYPE: [CallbackQueryHandler(tx_ttype_cb, pattern=r"^tx:tt:(work_in|work_out|personal_out)$")],
            TX_CAT_PICK: [CallbackQueryHandler(tx_cat_pick_cb, pattern=r"^tx:(cat:\d+|catp:\d+|cat_add)$")],
            TX_CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_cat_add_name_input)],
            TX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_amount_input)],
            TX_DESC: [
                CommandHandler("skip", tx_desc_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tx_desc_input),
            ],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(tx_conv)

    # TX details (view / delete-with-confirm / category picker)
    app.add_handler(
        CallbackQueryHandler(dtx_cb, pattern=r"^dtx:(open|del|delok|cat):\d{4}-\d{2}-\d{2}:\d+$")
    )
    app.add_handler(CallbackQueryHandler(dtx_cb, pattern=r"^dtx:catp:\d{4}-\d{2}-\d{2}:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(dtx_cb, pattern=r"^dtx:setcat:\d{4}-\d{2}-\d{2}:\d+:\d+$"))

    # Edit amount conversation
    edit_amt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:amt:\d{4}-\d{2}-\d{2}:\d+$")],
        states={ED_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_amount_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(edit_amt_conv)

    # Edit description conversation
    edit_desc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:desc:\d{4}-\d{2}-\d{2}:\d+$")],
        states={ED_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_desc_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(edit_desc_conv)

    # Edit date conversation ("cancel" leaves through the dtx:open button)
    edit_date_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:date:\d{4}-\d{2}-\d{2}:\d+$")],
        states={
            ED_DATE_MENU: [
                CallbackQueryHandler(
                    edit_date_menu_cb,
                    pattern=r"^dtx:dset:\d{4}-\d{2}-\d{2}:\d+:(today|g|j)$",
                ),
                CallbackQueryHandler(dtx_cb, pattern=r"^dtx:open:\d{4}-\d{2}-\d{2}:\d+$"),
            ],
            ED_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date_g_input)],
            ED_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date_j_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(edit_date_conv)

    # Reports (summary / breakdown / CSV export)
    app.add_handler(
        CallbackQueryHandler(
            report_cb,
            pattern=(
                r"^rp:(root"
                r"|y:\d{4}"
                r"|m:\d{4}:\d{2}"
                r"|bd:(a|y:\d{4}|m:\d{4}:\d{2})"
                r"|csv:(a|y:\d{4}|m:\d{4}:\d{2}))$"
            ),
        )
    )

    # DB menu (menu / toggle / take backup)
    app.add_handler(CallbackQueryHandler(db_cb, pattern=r"^db:(open|backup_now|toggle|target)$"))

    # DB target conversation
    db_target_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(db_target_choice_cb, pattern=r"^db:target:(chat|channel)$")],
        states={
            DB_SET_TARGET_ID: [
                CommandHandler("skip", db_set_target_id_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, db_set_target_id_input),
            ],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(db_target_conv)

    # DB interval conversation
    db_interval_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(db_interval_entry, pattern=r"^db:interval$")],
        states={DB_SET_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, db_set_interval_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(db_interval_conv)

    # DB restore conversation
    db_restore_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(db_restore_entry, pattern=r"^db:restore$")],
        states={DB_RESTORE_WAIT_DOC: [MessageHandler(filters.Document.ALL, db_restore_wait_doc)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(db_restore_conv)

    # Unknown callbacks
    app.add_handler(
        CallbackQueryHandler(
            unknown_callback,
            pattern=r"^(?!m:|st:|ac:|ad:|ct:|tx:|dl:|dtx:|rp:|db:).+",
        ),
        group=90,
    )

    # Nothing should ever fail silently.
    app.add_error_handler(on_error)

    return app

def main() -> None:
    app = build_app()
    logger.info("%s started. TZ=%s DB=%s", PROJECT_NAME, "Asia/Tehran", DB_PATH)
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
