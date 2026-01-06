# bot.py
# KasbBook - Inline-only Finance Manager Telegram Bot (SQLite)
# Python 3.10+ | python-telegram-bot v20+ | sqlite3 | pytz | jdatetime | python-dotenv
#

import os
import re
import io
import json
import shutil
import sqlite3
import logging
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict

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
TZ = pytz.timezone("Asia/Tehran")

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

# =========================
# ENV
# =========================
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

        def _ensure_setting(key: str, default: str) -> None:
            if conn.execute("SELECT 1 FROM settings WHERE k=?", (key,)).fetchone() is None:
                conn.execute("INSERT INTO settings(k,v) VALUES(?,?)", (key, default))

        _ensure_setting("access_mode", ACCESS_ADMIN_ONLY)
        _ensure_setting("share_enabled", "0")

        # Backup settings
        _ensure_setting("backup_enabled", "0")                   # 0/1
        _ensure_setting("backup_target_type", "chat")            # chat/channel
        _ensure_setting("backup_target_id", str(ADMIN_CHAT_ID))  # default admin chat id
        _ensure_setting("backup_interval_hours", "1")            # integer hours

        conn.commit()

def get_setting(k: str) -> str:
    with db_conn() as conn:
        r = conn.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
        if not r:
            raise RuntimeError(f"Missing setting: {k}")
        return str(r["v"])

def set_setting(k: str, v: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, v),
        )
        conn.commit()

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

def is_primary_admin(user_id: int) -> bool:
    return user_id == ADMIN_CHAT_ID

def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_CHAT_ID:
        return True
    with db_conn() as conn:
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
            conn.execute("UPDATE categories SET is_locked=1 WHERE id=?", (row["id"],))
        conn.commit()

def fetch_cats(scope: str, owner: int, grp: str) -> List[sqlite3.Row]:
    with db_conn() as conn:
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
            await q.edit_message_text(rtl(text))
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
ED_AMOUNT, ED_DESC = range(2)

DB_SET_TARGET_ID, DB_SET_INTERVAL, DB_RESTORE_WAIT_DOC = range(3)

# =========================
# Commands setup
# =========================
async def setup_commands(app: Application) -> None:
    try:
        await app.bot.set_my_commands([BotCommand("start", "شروع ربات")])
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
    if action == "home":
        await q.edit_message_text(rtl(start_text()), reply_markup=main_menu())
        return
    if action == "tx":
        await q.edit_message_text(rtl("📌 تراکنش‌ها:"), reply_markup=tx_menu())
        return
    if action == "st":
        await q.edit_message_text(rtl("⚙️ تنظیمات:"), reply_markup=settings_menu(user.id))
        return
    if action == "report":
        await report_root(update, context, edit=True)
        return

    await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=main_menu())

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
        await q.edit_message_text(rtl("🧩 مدیریت دسته‌ها:"), reply_markup=cats_root_menu())
        return
    if action == "access":
        if not is_primary_admin(user.id):
            await q.edit_message_text(rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
            return
        await q.edit_message_text(rtl("🔐 دسترسی ربات:"), reply_markup=access_menu(user.id))
        return
    if action == "db":
        if not is_primary_admin(user.id):
            await q.edit_message_text(rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
            return
        await q.edit_message_text(rtl(db_menu_text()), reply_markup=db_menu_kb())
        return

    await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=settings_menu(user.id))

async def access_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    if not is_primary_admin(user.id):
        await q.edit_message_text(rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return

    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "mode":
        mode = parts[2]
        if mode not in (ACCESS_ADMIN_ONLY, ACCESS_PUBLIC):
            await q.edit_message_text(rtl("حالت نامعتبر."), reply_markup=access_menu(user.id))
            return
        set_setting("access_mode", mode)
        await q.edit_message_text(rtl("✅ انجام شد."), reply_markup=access_menu(user.id))
        return

    if act == "share":
        if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
            await q.edit_message_text(rtl("این گزینه فقط در حالت ادمین فعال است."), reply_markup=access_menu(user.id))
            return
        cur = get_setting("share_enabled")
        set_setting("share_enabled", "0" if cur == "1" else "1")
        await q.edit_message_text(rtl("✅ انجام شد."), reply_markup=access_menu(user.id))
        return

    await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=access_menu(user.id))

# =========================
# Admin management
# =========================
def build_admin_panel_kb() -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton("➕ اضافه کردن ادمین", callback_data=f"{CB_AD}:add")])

    with db_conn() as conn:
        admins = conn.execute("SELECT user_id, name FROM admins ORDER BY added_at DESC").fetchall()

    for r in admins[:100]:
        nm = (r["name"] or "").strip() or str(r["user_id"])
        rows.append(
            [
                InlineKeyboardButton(nm, callback_data=f"{CB_AD}:noop"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"{CB_AD}:del:{r['user_id']}"),
            ]
        )

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
        await q.edit_message_text(rtl("⛔ فقط ادمین اصلی."), reply_markup=main_menu())
        return ConversationHandler.END

    if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
        await q.edit_message_text(rtl("این بخش فقط در حالت ادمین فعال است."), reply_markup=access_menu(user.id))
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    act = parts[1]

    if act in ("panel", "noop"):
        await q.edit_message_text(rtl("👥 مدیریت ادمین‌ها:"), reply_markup=build_admin_panel_kb())
        return ConversationHandler.END

    if act == "del":
        try:
            uid = int(parts[2])
        except Exception:
            await q.edit_message_text(rtl("آیدی نامعتبر."), reply_markup=build_admin_panel_kb())
            return ConversationHandler.END

        with db_conn() as conn:
            conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
            conn.commit()

        await q.edit_message_text(rtl("✅ حذف شد.\n\n👥 مدیریت ادمین‌ها:"), reply_markup=build_admin_panel_kb())
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        await q.edit_message_text(rtl("🆔 user_id عددی ادمین جدید را وارد کنید:"))
        return ADM_ADD_UID

    await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=build_admin_panel_kb())
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
    if uid == ADMIN_CHAT_ID:
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

    with db_conn() as conn:
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

    with db_conn() as conn:
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

    await update.effective_chat.send_message(rtl("✅ دسته و تراکنش‌ها ویرایش شد."))
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
        await q.edit_message_text(rtl(f"🧩 {grp_label(grp)}"), reply_markup=build_cat_kb(scope, owner, grp))
        return ConversationHandler.END

    if act == "add":
        grp = parts[2]
        context.user_data.clear()
        context.user_data["cat_grp"] = grp
        await q.edit_message_text(rtl(f"نام دسته جدید برای «{grp_label(grp)}» را وارد کنید:"))
        return CAT_ADD_NAME

    if act == "del":
        cid = int(parts[2])
        with db_conn() as conn:
            row = conn.execute(
                "SELECT grp, name, is_locked FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cid, scope, owner),
            ).fetchone()
            if not row:
                await q.edit_message_text(rtl("پیدا نشد."))
                return ConversationHandler.END

            if row["grp"] == "personal_out" and row["name"] == INSTALLMENT_NAME and int(row["is_locked"]) == 1:
                await q.edit_message_text(rtl("⛔ دسته «قسط» قفل است و حذف نمی‌شود."))
                return ConversationHandler.END

            conn.execute("DELETE FROM categories WHERE id=?", (cid,))
            conn.commit()

        grp = row["grp"]
        await q.edit_message_text(rtl(f"✅ حذف شد.\n\n🧩 {grp_label(grp)}"), reply_markup=build_cat_kb(scope, owner, grp))
        return ConversationHandler.END

    # ✅ FIX: rename handler (برای اینکه دکمه ویرایش واقعاً کار کند)
    if act == "ren":
        cid = int(parts[2])

        with db_conn() as conn:
            row = conn.execute(
                "SELECT grp, name, is_locked FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cid, scope, owner),
            ).fetchone()

        if not row:
            await q.edit_message_text(rtl("پیدا نشد."))
            return ConversationHandler.END

        if row["grp"] == "personal_out" and row["name"] == INSTALLMENT_NAME and int(row["is_locked"]) == 1:
            await q.edit_message_text(rtl("⛔ دسته «قسط» قفل است و ویرایش نمی‌شود."))
            return ConversationHandler.END

        context.user_data.clear()
        context.user_data["rename_cat_id"] = cid
        context.user_data["rename_cat_grp"] = row["grp"]
        context.user_data["rename_old_name"] = row["name"]

        await q.edit_message_text(rtl(f"✏️ نام جدید برای دسته «{row['name']}» را وارد کنید:"))
        return CAT_RENAME_NAME

    await q.edit_message_text(rtl("دستور ناشناخته."))
    return ConversationHandler.END

def build_cat_kb(scope: str, owner: int, grp: str) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    rows: List[List[InlineKeyboardButton]] = []

    rows.append([InlineKeyboardButton("➕ افزودن دسته", callback_data=f"{CB_CT}:add:{grp}")])

    cats = fetch_cats(scope, owner, grp)
    for r in cats[:120]:
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

    with db_conn() as conn:
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
def cat_pick_keyboard(scope: str, owner: int, grp: str, back_cb: str) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    cats = fetch_cats(scope, owner, grp)
    rows: List[List[InlineKeyboardButton]] = []
    for r in cats[:90]:
        rows.append([InlineKeyboardButton(r["name"], callback_data=f"{CB_TX}:cat:{r['id']}")])
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

    await q.edit_message_text(
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
        await q.edit_message_text(rtl("نوع نامعتبر."), reply_markup=tx_menu())
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["tx_origin"] = "daily"
    context.user_data["tx_date_g"] = gdate
    context.user_data["tx_ttype"] = ttype
    context.user_data["tx_daily_gdate"] = gdate

    scope, owner = resolve_scope_owner(user.id)
    await q.edit_message_text(
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
        await q.edit_message_text(
            rtl(f"🔖 نوع تراکنش را انتخاب کنید:\n\n📅 تاریخ: {gdate} ({g_to_j(gdate)})"),
            reply_markup=tx_ttype_kb(back_cb=f"{CB_M}:tx"),
        )
        return TX_TTYPE

    if mode == "g":
        await q.edit_message_text(rtl("تاریخ میلادی را وارد کنید (YYYY-MM-DD):"))
        return TX_DATE_G

    if mode == "j":
        await q.edit_message_text(rtl("تاریخ شمسی را وارد کنید (YYYY/MM/DD):"))
        return TX_DATE_J

    await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=tx_menu())
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
        await q.edit_message_text(rtl("نوع نامعتبر."), reply_markup=tx_menu())
        return ConversationHandler.END

    gdate = context.user_data.get("tx_date_g")
    if not gdate:
        await q.edit_message_text(rtl("خطا: تاریخ مشخص نیست."), reply_markup=tx_menu())
        return ConversationHandler.END

    context.user_data["tx_ttype"] = ttype
    scope, owner = resolve_scope_owner(user.id)
    await q.edit_message_text(
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
        await q.edit_message_text(rtl("نام دسته جدید را وارد کنید:"))
        return TX_CAT_ADD_NAME

    if act != "cat":
        await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=tx_menu())
        return ConversationHandler.END

    try:
        cid = int(parts[2])
    except Exception:
        await q.edit_message_text(rtl("دسته نامعتبر."), reply_markup=tx_menu())
        return ConversationHandler.END

    ttype = context.user_data.get("tx_ttype")
    gdate = context.user_data.get("tx_date_g")
    if ttype not in ("work_in", "work_out", "personal_out") or not gdate:
        await q.edit_message_text(rtl("خطا: اطلاعات ناقص."), reply_markup=tx_menu())
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    with db_conn() as conn:
        row = conn.execute(
            "SELECT name FROM categories WHERE id=? AND scope=? AND owner_user_id=? AND grp=?",
            (cid, scope, owner, ttype),
        ).fetchone()

    if not row:
        await q.edit_message_text(rtl("دسته پیدا نشد. دوباره انتخاب کنید."))
        return TX_CAT_PICK

    context.user_data["tx_category"] = row["name"]
    await q.edit_message_text(rtl("💵 مبلغ را وارد کنید (عدد صحیح):"))
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

    with db_conn() as conn:
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
    with db_conn() as conn:
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

def _day_sums(scope: str, owner: int, gdate: str) -> Tuple[int, int, int, int]:
    with db_conn() as conn:
        w_in = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE scope=? AND owner_user_id=? AND date_g=? AND ttype='work_in'",
            (scope, owner, gdate),
        ).fetchone()["s"]
        w_out = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE scope=? AND owner_user_id=? AND date_g=? AND ttype='work_out'",
            (scope, owner, gdate),
        ).fetchone()["s"]
        installment = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g=? AND ttype='personal_out' AND category=?
            """,
            (scope, owner, gdate, INSTALLMENT_NAME),
        ).fetchone()["s"]
        p_non = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g=? AND ttype='personal_out' AND category<>?
            """,
            (scope, owner, gdate, INSTALLMENT_NAME),
        ).fetchone()["s"]

    return int(w_in), int(w_out), int(installment), int(p_non)

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

def daily_rows_kb(scope: str, owner: int, gdate: str) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    a1, a2, a3 = _short_add_labels()
    rows.append(
        [
            InlineKeyboardButton(a1, callback_data=f"{CB_DL}:add:{gdate}:work_in"),
            InlineKeyboardButton(a2, callback_data=f"{CB_DL}:add:{gdate}:work_out"),
            InlineKeyboardButton(a3, callback_data=f"{CB_DL}:add:{gdate}:personal_out"),
        ]
    )

    def add_section(ttype: str):
        with db_conn() as conn:
            txs = conn.execute(
                """
                SELECT id, category, amount
                FROM transactions
                WHERE scope=? AND owner_user_id=? AND date_g=? AND ttype=?
                ORDER BY id DESC
                LIMIT 80
                """,
                (scope, owner, gdate, ttype),
            ).fetchall()

        rows.append([InlineKeyboardButton(_section_title(ttype), callback_data=f"{CB_DL}:noop")])

        if not txs:
            rows.append([InlineKeyboardButton("خالی", callback_data=f"{CB_DL}:noop")])
            return

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

    add_section("work_in")
    add_section("work_out")
    add_section("personal_out")

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
        await q.edit_message_text(rtl("📄 لیست روزانه\n\nتاریخ را انتخاب کنید:"), reply_markup=daily_pick_menu())
        return DL_DATE_MENU

    if act == "noop":
        return ConversationHandler.END

    if act == "d":
        mode = data[2]
        if mode == "today":
            gdate = today_g()
            scope, owner = resolve_scope_owner(user.id)
            await q.edit_message_text(
                daily_list_text(scope, owner, gdate),
                reply_markup=daily_rows_kb(scope, owner, gdate),
            )
            return ConversationHandler.END

        if mode == "g":
            await q.edit_message_text(rtl("تاریخ میلادی را وارد کنید (YYYY-MM-DD):"))
            return DL_DATE_G

        if mode == "j":
            await q.edit_message_text(rtl("تاریخ شمسی را وارد کنید (YYYY/MM/DD):"))
            return DL_DATE_J

    if act == "show":
        gdate = data[2]
        scope, owner = resolve_scope_owner(user.id)
        await q.edit_message_text(
            daily_list_text(scope, owner, gdate),
            reply_markup=daily_rows_kb(scope, owner, gdate),
        )
        return ConversationHandler.END

    await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=tx_menu())
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
    with db_conn() as conn:
        return conn.execute(
            "SELECT * FROM transactions WHERE id=? AND scope=? AND owner_user_id=?",
            (tx_id, scope, owner),
        ).fetchone()

def tx_view_kb(gdate: str, tx_id: int) -> InlineKeyboardMarkup:
    return ikb(
        [
            [("✏️ ویرایش دسته", f"{CB_DTX}:cat:{gdate}:{tx_id}")],
            [("✏️ ویرایش مبلغ", f"{CB_DTX}:amt:{gdate}:{tx_id}")],
            [("✏️ ویرایش توضیحات", f"{CB_DTX}:desc:{gdate}:{tx_id}")],
            [("🗑 حذف", f"{CB_DTX}:del:{gdate}:{tx_id}")],
            [("⬅️ بازگشت", f"{CB_DL}:show:{gdate}")],
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
        await q.edit_message_text(rtl("تراکنش پیدا نشد."), reply_markup=tx_menu())
        return ConversationHandler.END

    if act == "open":
        lines = [
            "🧾 جزئیات تراکنش",
            "",
            f"📅 تاریخ (میلادی): {tx['date_g']}",
            f"📅 تاریخ (شمسی): {g_to_j(tx['date_g'])}",
            f"🔖 نوع: {ttype_label(tx['ttype'])}",
            f"🏷 دسته: {tx['category']}",
            f"💵 مبلغ: {fmt_num(int(tx['amount']))}",
            f"📝 توضیح: {(tx['description'] or '-').strip()}",
        ]
        await q.edit_message_text(rtl("\n".join(lines)), reply_markup=tx_view_kb(gdate, tx_id))
        return ConversationHandler.END

    if act == "del":
        with db_conn() as conn:
            conn.execute("DELETE FROM transactions WHERE id=? AND scope=? AND owner_user_id=?", (tx_id, scope, owner))
            conn.commit()
        await q.edit_message_text(
            daily_list_text(scope, owner, gdate),
            reply_markup=daily_rows_kb(scope, owner, gdate),
        )
        return ConversationHandler.END

    if act == "amt":
        context.user_data.clear()
        context.user_data["edit_tx_id"] = tx_id
        context.user_data["edit_gdate"] = gdate
        await q.edit_message_text(rtl("💵 مبلغ جدید را وارد کنید (عدد):"))
        return ED_AMOUNT

    if act == "desc":
        context.user_data.clear()
        context.user_data["edit_tx_id"] = tx_id
        context.user_data["edit_gdate"] = gdate
        await q.edit_message_text(rtl("📝 توضیح جدید را وارد کنید (یا - برای حذف):"))
        return ED_DESC

    if act == "cat":
        ttype = tx["ttype"]
        ensure_installment(scope, owner)
        cats = fetch_cats(scope, owner, ttype)

        rows: List[List[InlineKeyboardButton]] = []
        for c in cats[:90]:
            rows.append([InlineKeyboardButton(c["name"], callback_data=f"{CB_DTX}:setcat:{gdate}:{tx_id}:{c['id']}")])
        rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_DTX}:open:{gdate}:{tx_id}")])

        await q.edit_message_text(rtl("🏷 دسته جدید را انتخاب کنید:"), reply_markup=InlineKeyboardMarkup(rows))
        return ConversationHandler.END

    if act == "setcat":
        cat_id = int(parts[4])
        with db_conn() as conn:
            row = conn.execute(
                "SELECT name FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cat_id, scope, owner),
            ).fetchone()
            if not row:
                await q.edit_message_text(rtl("دسته پیدا نشد."))
                return ConversationHandler.END

            conn.execute(
                "UPDATE transactions SET category=?, updated_at=? WHERE id=? AND scope=? AND owner_user_id=?",
                (row["name"], now_ts(), tx_id, scope, owner),
            )
            conn.commit()

        tx2 = get_tx(scope, owner, tx_id)
        lines = [
            "✅ ویرایش شد.",
            "",
            "🧾 جزئیات تراکنش",
            "",
            f"📅 تاریخ (میلادی): {tx2['date_g']}",
            f"📅 تاریخ (شمسی): {g_to_j(tx2['date_g'])}",
            f"🔖 نوع: {ttype_label(tx2['ttype'])}",
            f"🏷 دسته: {tx2['category']}",
            f"💵 مبلغ: {fmt_num(int(tx2['amount']))}",
            f"📝 توضیح: {(tx2['description'] or '-').strip()}",
        ]
        await q.edit_message_text(rtl("\n".join(lines)), reply_markup=tx_view_kb(gdate, tx_id))
        return ConversationHandler.END

    await q.edit_message_text(rtl("دستور ناشناخته."))
    return ConversationHandler.END

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
    with db_conn() as conn:
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
    with db_conn() as conn:
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
# Reports
# =========================
MONTHS = [
    ("Jan", 1), ("Feb", 2), ("Mar", 3),
    ("Apr", 4), ("May", 5), ("Jun", 6),
    ("Jul", 7), ("Aug", 8), ("Sep", 9),
    ("Oct", 10), ("Nov", 11), ("Dec", 12),
]

def sums_for_range(scope: str, owner: int, start_g: str, end_g_exclusive: str) -> Dict[str, int]:
    ensure_installment(scope, owner)
    with db_conn() as conn:
        w_in = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g>=? AND date_g<? AND ttype='work_in'
            """,
            (scope, owner, start_g, end_g_exclusive),
        ).fetchone()[0]

        w_out = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g>=? AND date_g<? AND ttype='work_out'
            """,
            (scope, owner, start_g, end_g_exclusive),
        ).fetchone()[0]

        installment = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g>=? AND date_g<?
              AND ttype='personal_out' AND category=?
            """,
            (scope, owner, start_g, end_g_exclusive, INSTALLMENT_NAME),
        ).fetchone()[0]

        personal_non_install = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g>=? AND date_g<?
              AND ttype='personal_out' AND category<>?
            """,
            (scope, owner, start_g, end_g_exclusive, INSTALLMENT_NAME),
        ).fetchone()[0]

    net = int(w_in) - int(w_out)
    savings_operational = net - int(personal_non_install)
    savings_final = savings_operational - int(installment)

    return {
        "income": int(w_in),
        "work_out": int(w_out),
        "net": int(net),
        "installment": int(installment),
        "personal": int(personal_non_install),
        "savings_operational": int(savings_operational),
        "savings_final": int(savings_final),
    }

# ✅ FIX: گزارش کلی هم باید همین کلیدها را برگرداند
def sums_all(scope: str, owner: int) -> Dict[str, int]:
    ensure_installment(scope, owner)
    with db_conn() as conn:
        w_in = conn.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE scope=? AND owner_user_id=? AND ttype='work_in'",
            (scope, owner),
        ).fetchone()["s"]
        w_out = conn.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE scope=? AND owner_user_id=? AND ttype='work_out'",
            (scope, owner),
        ).fetchone()["s"]
        installment = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND ttype='personal_out' AND category=?
            """,
            (scope, owner, INSTALLMENT_NAME),
        ).fetchone()["s"]
        p_non = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND ttype='personal_out' AND category<>?
            """,
            (scope, owner, INSTALLMENT_NAME),
        ).fetchone()["s"]

    w_in = int(w_in)
    w_out = int(w_out)
    installment = int(installment)
    p_non = int(p_non)

    net = w_in - w_out
    savings_operational = net - p_non
    savings_final = savings_operational - installment

    return {
        "income": w_in,
        "work_out": w_out,
        "net": net,
        "installment": installment,
        "personal": p_non,
        "savings_operational": savings_operational,
        "savings_final": savings_final,
    }

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

def years_with_data(scope: str, owner: int) -> List[int]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT SUBSTR(date_g,1,4) AS y
            FROM transactions
            WHERE scope=? AND owner_user_id=?
            ORDER BY y DESC
            """,
            (scope, owner),
        ).fetchall()
    out: List[int] = []
    for r in rows:
        try:
            out.append(int(r["y"]))
        except Exception:
            pass
    return out

def report_root_kb(years: List[int]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    buf: List[InlineKeyboardButton] = []
    for y in years:
        buf.append(InlineKeyboardButton(str(y), callback_data=f"{CB_RP}:y:{y}"))
        if len(buf) == 3:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_M}:home")])
    return InlineKeyboardMarkup(rows)

def report_year_kb(year: int) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    i = 0
    while i < 12:
        row = []
        for _ in range(3):
            if i >= 12:
                break
            name, mnum = MONTHS[i]
            row.append(InlineKeyboardButton(name, callback_data=f"{CB_RP}:m:{year}:{mnum:02d}"))
            i += 1
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_RP}:root")])
    return InlineKeyboardMarkup(rows)

def report_month_kb(year: int) -> InlineKeyboardMarkup:
    return ikb([[("⬅️ بازگشت", f"{CB_RP}:y:{year}")]])

async def report_root(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return

    scope, owner = resolve_scope_owner(user.id)
    s = sums_all(scope, owner)
    years = years_with_data(scope, owner)

    text = report_lines("📊 گزارش کلی", s)
    kb = report_root_kb(years) if years else ikb([[("⬅️ بازگشت", f"{CB_M}:home")]])

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
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
        year = int(parts[2])
        start = f"{year:04d}-01-01"
        end = f"{year+1:04d}-01-01"
        s = sums_for_range(scope, owner, start, end)

        text = report_lines(f"📊 گزارش سال {year}", s)
        await q.edit_message_text(text, reply_markup=report_year_kb(year))
        return

    if act == "m":
        year = int(parts[2])
        month = int(parts[3])

        start = f"{year:04d}-{month:02d}-01"
        end = f"{year+1:04d}-01-01" if month == 12 else f"{year:04d}-{month+1:02d}-01"

        s = sums_for_range(scope, owner, start, end)
        mname = dict((mnum, name) for name, mnum in MONTHS).get(month, f"{month:02d}")
        text = report_lines(f"📊 گزارش {mname} {year}", s)
        await q.edit_message_text(text, reply_markup=report_month_kb(year))
        return

    await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=main_menu())

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
    tmp_path = f"/tmp/{backup_filename()}"
    src = sqlite3.connect(DB_PATH)
    try:
        dst = sqlite3.connect(tmp_path)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()

    with open(tmp_path, "rb") as f:
        data = f.read()
    try:
        os.remove(tmp_path)
    except Exception:
        pass
    return data

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
        callback=lambda ctx: send_backup_file(ctx),
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
        await q.edit_message_text(rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    act = parts[1] if len(parts) > 1 else ""

    if act == "open":
        await q.edit_message_text(rtl(db_menu_text()), reply_markup=db_menu_kb())
        return ConversationHandler.END

    if act == "backup_now":
        fname = backup_filename()
        data = make_backup_bytes()
        bio = io.BytesIO(data)
        bio.name = fname

        await q.edit_message_text(rtl("در حال ارسال بکاپ..."), reply_markup=db_menu_kb())
        await context.bot.send_document(
            chat_id=user.id,
            document=bio,
            filename=fname,
            caption=rtl(f"🗄 بکاپ دیتابیس\n\n📦 {fname}"),
        )
        await q.edit_message_text(rtl(db_menu_text()), reply_markup=db_menu_kb())
        return ConversationHandler.END

    if act == "toggle":
        cur = get_setting("backup_enabled")
        set_setting("backup_enabled", "0" if cur == "1" else "1")
        schedule_backup_job(context.application)
        await q.edit_message_text(rtl(db_menu_text()), reply_markup=db_menu_kb())
        return ConversationHandler.END

    if act == "target":
        await q.edit_message_text(
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

    await q.edit_message_text(rtl("دستور ناشناخته."), reply_markup=db_menu_kb())
    return ConversationHandler.END

async def db_target_choice_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    if not is_primary_admin(user.id):
        await q.edit_message_text(rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    target_type = parts[2]  # chat/channel

    if target_type == "chat":
        set_setting("backup_target_type", "chat")
        context.user_data.clear()
        context.user_data["db_target_type"] = "chat"
        await q.edit_message_text(
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
        await q.edit_message_text(
            rtl(
                "📣 ارسال بکاپ به کانال\n\n"
                "آیدی عددی کانال را وارد کنید (مثل -1001234567890).\n\n"
                "⚠️ ربات باید در کانال اجازه ارسال داشته باشد."
            )
        )
        return DB_SET_TARGET_ID

    await q.edit_message_text(rtl("گزینه نامعتبر."), reply_markup=db_menu_kb())
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
        await q.edit_message_text(rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return ConversationHandler.END

    context.user_data.clear()
    await q.edit_message_text(rtl("⏱ عدد فاصله بکاپ خودکار را به ساعت وارد کنید (مثلاً 1):"))
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
        await q.edit_message_text(rtl("⛔ فقط ادمین اصلی."), reply_markup=settings_menu(user.id))
        return ConversationHandler.END

    context.user_data.clear()
    await q.edit_message_text(rtl("📤 لطفاً فایل بکاپ با پسوند .db را ارسال کنید:"))
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
    tmp_in = f"/tmp/restore_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.db"
    await file.download_to_drive(custom_path=tmp_in)

    # Emergency backup current DB
    try:
        emergency_name = f"kasbbook_emergency_{datetime.now(TZ).strftime('%Y-%m-%d_%H-%M-%S')}.db"
        data = make_backup_bytes()
        bio = io.BytesIO(data)
        bio.name = emergency_name
        await update.effective_chat.send_message(rtl("🧯 بکاپ اضطراری از دیتابیس فعلی گرفته شد."))
        await context.bot.send_document(
            chat_id=user.id,
            document=bio,
            filename=emergency_name,
            caption=rtl(f"🧯 بکاپ اضطراری قبل از ریستور\n\n📦 {emergency_name}"),
        )
    except Exception as e:
        logger.warning("Failed to send emergency backup: %s", e)

    try:
        shutil.move(tmp_in, DB_PATH)
        init_db()
        await update.effective_chat.send_message(rtl("✅ بکاپ با موفقیت وارد شد."))
    except Exception as e:
        logger.exception("Restore failed: %s", e)
        await update.effective_chat.send_message(rtl("❌ خطا در ریستور بکاپ."))
        return ConversationHandler.END

    schedule_backup_job(context.application)
    await update.effective_chat.send_message(rtl(db_menu_text()), reply_markup=db_menu_kb())
    return ConversationHandler.END

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

    # Commands
    app.add_handler(CommandHandler("start", start))

    # Main
    app.add_handler(CallbackQueryHandler(main_cb, pattern=r"^m:(home|tx|st|report)$"))

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
            await q.edit_message_text(rtl("🔐 دسترسی ربات:"), reply_markup=access_menu(user.id))
        else:
            await q.edit_message_text(rtl(start_text()), reply_markup=main_menu())

    app.add_handler(CallbackQueryHandler(ac_noop, pattern=r"^ac:noop$"))

    # Admin panel (نمایش/حذف) - بدون add (چون add ورودی کانورسیشنه)
    app.add_handler(CallbackQueryHandler(admin_panel_cb, pattern=r"^ad:(panel|del:\d+|noop)$"))

    adm_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_panel_cb, pattern=r"^ad:add$")],
        states={
            ADM_ADD_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_uid)],
            ADM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_name)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(adm_conv)

    # Categories (نمایش/حذف) - بدون add (چون add ورودی کانورسیشنه)
    app.add_handler(CallbackQueryHandler(cats_cb, pattern=r"^ct:(grp:(work_in|work_out|personal_out)|del:\d+|noop)$"))

    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:add:(work_in|work_out|personal_out)$")],
        states={CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_add_name)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(cat_conv)

    cat_rename_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:ren:\d+$")],
        states={
            CAT_RENAME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_rename_name)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(cat_rename_conv)

    # Daily list (کانورسیشن انتخاب تاریخ)
    dl_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(daily_cb, pattern=r"^dl:pick$")],
        states={
            DL_DATE_MENU: [CallbackQueryHandler(daily_cb, pattern=r"^dl:d:(today|g|j)$")],
            DL_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, dl_date_g_input)],
            DL_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, dl_date_j_input)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(dl_conv)

    # Daily non-conv callbacks
    app.add_handler(CallbackQueryHandler(daily_cb, pattern=r"^dl:(d:(today|g|j)|show:\d{4}-\d{2}-\d{2}|noop)$"))

    # Transactions flow (کانورسیشن ساخت تراکنش)
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
            TX_CAT_PICK: [CallbackQueryHandler(tx_cat_pick_cb, pattern=r"^tx:(cat:\d+|cat_add)$")],
            TX_CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_cat_add_name_input)],
            TX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_amount_input)],
            TX_DESC: [
                CommandHandler("skip", tx_desc_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tx_desc_input),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(tx_conv)

    # TX details (نمایش/حذف/انتخاب دسته)
    app.add_handler(CallbackQueryHandler(dtx_cb, pattern=r"^dtx:(open|del|cat):\d{4}-\d{2}-\d{2}:\d+$"))
    app.add_handler(CallbackQueryHandler(dtx_cb, pattern=r"^dtx:setcat:\d{4}-\d{2}-\d{2}:\d+:\d+$"))

    # Edit amount conversation
    edit_amt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:amt:\d{4}-\d{2}-\d{2}:\d+$")],
        states={ED_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_amount_input)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(edit_amt_conv)

    # Edit desc conversation
    edit_desc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:desc:\d{4}-\d{2}-\d{2}:\d+$")],
        states={ED_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_desc_input)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(edit_desc_conv)

    # Reports
    app.add_handler(CallbackQueryHandler(report_cb, pattern=r"^rp:(root|y:\d{4}|m:\d{4}:\d{2})$"))

    # DB menu (فقط منو/تغییر وضعیت/گرفتن بکاپ)
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
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(db_target_conv)

    # DB interval conversation
    db_interval_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(db_interval_entry, pattern=r"^db:interval$")],
        states={DB_SET_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, db_set_interval_input)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(db_interval_conv)

    # DB restore conversation
    db_restore_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(db_restore_entry, pattern=r"^db:restore$")],
        states={DB_RESTORE_WAIT_DOC: [MessageHandler(filters.Document.ALL, db_restore_wait_doc)]},
        fallbacks=[CommandHandler("start", start)],
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

    return app

def main() -> None:
    app = build_app()
    logger.info("%s started. TZ=%s DB=%s", PROJECT_NAME, "Asia/Tehran", DB_PATH)
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
