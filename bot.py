# bot.py
# KasbBook - Inline-only stable bot
# Python 3.10+ | python-telegram-bot v20+ | sqlite3 | pytz | jdatetime | python-dotenv

import os
import re
import sqlite3
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List, Dict

import pytz
import jdatetime
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
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

# ---------------------------
# Constants
# ---------------------------
PROJECT_NAME = "KasbBook"
DB_PATH = "KasbBook.db"
TZ = pytz.timezone("Asia/Tehran")

ACCESS_ADMIN_ONLY = "admin_only"   # default
ACCESS_PUBLIC = "public"

INSTALLMENT_NAME = "قسط"

# callback prefixes (short)
CB_M = "m"      # main
CB_TX = "tx"    # transactions
CB_RP = "rp"    # reports
CB_ST = "st"    # settings
CB_AC = "ac"    # access settings
CB_AD = "ad"    # admin manage
CB_CT = "ct"    # categories

# ---------------------------
# ENV
# ---------------------------
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

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(PROJECT_NAME)

# ---------------------------
# DB helpers
# ---------------------------
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

        if conn.execute("SELECT 1 FROM settings WHERE k='access_mode'").fetchone() is None:
            conn.execute("INSERT INTO settings(k,v) VALUES('access_mode', ?)", (ACCESS_ADMIN_ONLY,))
        if conn.execute("SELECT 1 FROM settings WHERE k='share_enabled'").fetchone() is None:
            conn.execute("INSERT INTO settings(k,v) VALUES('share_enabled', '0')")

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


def parse_any_date_to_g(s: str) -> Optional[str]:
    return parse_gregorian(s) or parse_jalali_to_g(s)


def month_range_for(g_yyyy_mm_dd: str) -> Tuple[str, str]:
    y, m, _ = map(int, g_yyyy_mm_dd.split("-"))
    start = date(y, m, 1)
    nm = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    end = nm - timedelta(days=1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


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


# ---------------------------
# UI helpers (Inline only)
# ---------------------------
def ikb(rows: List[List[Tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=cb) for (t, cb) in row] for row in rows]
    )


def main_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📌 تراکنش‌ها", f"{CB_M}:tx"), ("📊 گزارش‌ها", f"{CB_M}:rp")],
            [("⚙️ تنظیمات", f"{CB_M}:st")],
        ]
    )


def tx_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("➕ ثبت تراکنش", f"{CB_TX}:add")],
            [("📄 لیست امروز", f"{CB_TX}:list:today"), ("📄 لیست این ماه (میلادی)", f"{CB_TX}:list:month")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )


def rp_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📅 خلاصه امروز", f"{CB_RP}:sum:today"), ("🗓 خلاصه این ماه (میلادی)", f"{CB_RP}:sum:month")],
            [("📆 بازه دلخواه", f"{CB_RP}:range")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )


def settings_menu(user_id: int) -> InlineKeyboardMarkup:
    rows = [[("🧩 مدیریت نوع‌ها", f"{CB_ST}:cats")]]
    if is_primary_admin(user_id):
        rows.append([("🔐 دسترسی ربات", f"{CB_ST}:access")])
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

    rows.append([("⬅️ بازگشت", f"{CB_ST}:back")])
    return ikb(rows)


def cats_root_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("💰 درآمد کاری", f"{CB_CT}:grp:work_in")],
            [("🏢 هزینه کاری", f"{CB_CT}:grp:work_out")],
            [("👤 هزینه شخصی", f"{CB_CT}:grp:personal_out")],
            [("⬅️ بازگشت", f"{CB_ST}:back")],
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


# ---------------------------
# Access denied
# ---------------------------
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
    try:
        await update.effective_chat.send_message("\u200b", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    user = update.effective_user
    text = denied_text(user.id, user.username)

    if update.callback_query:
        q = update.callback_query
        try:
            await q.answer()
        except Exception:
            pass
        try:
            await q.edit_message_text(text)
        except Exception:
            await update.effective_chat.send_message(text)
    else:
        await update.effective_chat.send_message(text)


# ---------------------------
# STATES
# ---------------------------
TX_TTYPE, TX_DATE_MENU, TX_DATE_G, TX_DATE_J, TX_CAT_PICK, TX_CAT_ADD_NAME, TX_AMOUNT, TX_DESC = range(8)
RP_START, RP_END = range(2)
ADM_ADD_UID, ADM_ADD_NAME = range(2)
CAT_ADD_NAME = 0


# ---------------------------
# START
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.effective_chat.send_message("\u200b", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return

    await update.effective_chat.send_message(
        f"🏠 {PROJECT_NAME}\n\nیک گزینه انتخاب کنید:",
        reply_markup=main_menu(),
    )


# ---------------------------
# MAIN callbacks
# ---------------------------
async def main_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    action = (q.data or "").split(":")[1]
    if action == "home":
        await q.edit_message_text("🏠 منوی اصلی:", reply_markup=main_menu())
    elif action == "tx":
        await q.edit_message_text("📌 تراکنش‌ها:", reply_markup=tx_menu())
    elif action == "rp":
        await q.edit_message_text("📊 گزارش‌ها:", reply_markup=rp_menu())
    elif action == "st":
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=settings_menu(user.id))
    else:
        await q.edit_message_text("دستور ناشناخته.", reply_markup=main_menu())


# ---------------------------
# SETTINGS callbacks
# ---------------------------
async def settings_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    action = (q.data or "").split(":")[1]
    if action == "cats":
        await q.edit_message_text("🧩 مدیریت نوع‌ها:", reply_markup=cats_root_menu())
        return
    if action == "access":
        if not is_primary_admin(user.id):
            await q.edit_message_text("⛔ فقط ادمین اصلی.", reply_markup=settings_menu(user.id))
            return
        await q.edit_message_text("🔐 دسترسی ربات:", reply_markup=access_menu(user.id))
        return
    if action == "back":
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=settings_menu(user.id))
        return

    await q.edit_message_text("دستور ناشناخته.", reply_markup=settings_menu(user.id))


async def access_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    if not is_primary_admin(user.id):
        await q.edit_message_text("⛔ فقط ادمین اصلی.", reply_markup=settings_menu(user.id))
        return

    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "mode":
        mode = parts[2]
        if mode not in (ACCESS_ADMIN_ONLY, ACCESS_PUBLIC):
            await q.edit_message_text("حالت نامعتبر.", reply_markup=access_menu(user.id))
            return
        set_setting("access_mode", mode)
        await q.edit_message_text("✅ انجام شد.", reply_markup=access_menu(user.id))
        return

    if act == "share":
        if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
            await q.edit_message_text("این گزینه فقط در حالت ادمین فعال است.", reply_markup=access_menu(user.id))
            return
        cur = get_setting("share_enabled")
        set_setting("share_enabled", "0" if cur == "1" else "1")
        await q.edit_message_text("✅ انجام شد.", reply_markup=access_menu(user.id))
        return

    await q.edit_message_text("دستور ناشناخته.", reply_markup=access_menu(user.id))


# ---------------------------
# ADMIN MANAGEMENT (panel table style)
# ---------------------------
def build_admin_panel_kb() -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton("➕ اضافه کردن ادمین", callback_data=f"{CB_AD}:add")])

    with db_conn() as conn:
        admins = conn.execute("SELECT user_id, name FROM admins ORDER BY added_at DESC").fetchall()

    # each row: [name] [delete]
    for r in admins[:60]:
        nm = (r["name"] or "").strip() or str(r["user_id"])
        rows.append(
            [
                InlineKeyboardButton(nm, callback_data=f"{CB_AD}:noop"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"{CB_AD}:del:{r['user_id']}"),
            ]
        )

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_ST}:access")])
    return InlineKeyboardMarkup(rows)


async def admin_panel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user

    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    if not is_primary_admin(user.id):
        await q.edit_message_text("⛔ فقط ادمین اصلی.", reply_markup=access_menu(user.id))
        return ConversationHandler.END

    if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
        await q.edit_message_text("این بخش فقط در حالت ادمین فعال است.", reply_markup=access_menu(user.id))
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    act = parts[1]

    if act in ("panel", "noop"):
        await q.edit_message_text("👥 مدیریت ادمین‌ها:", reply_markup=build_admin_panel_kb())
        return ConversationHandler.END

    if act == "del":
        try:
            uid = int(parts[2])
        except Exception:
            await q.edit_message_text("آیدی نامعتبر.", reply_markup=build_admin_panel_kb())
            return ConversationHandler.END

        with db_conn() as conn:
            conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
            conn.commit()

        await q.edit_message_text("✅ حذف شد.", reply_markup=build_admin_panel_kb())
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        await q.edit_message_text("🆔 user_id عددی ادمین جدید را وارد کنید:")
        return ADM_ADD_UID

    await q.edit_message_text("دستور ناشناخته.", reply_markup=build_admin_panel_kb())
    return ConversationHandler.END


async def adm_add_uid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_primary_admin(user.id):
        await update.effective_chat.send_message("⛔ فقط ادمین اصلی.")
        context.user_data.clear()
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message("❌ فقط user_id عددی وارد کنید:")
        return ADM_ADD_UID

    uid = int(t)
    if uid == ADMIN_CHAT_ID:
        await update.effective_chat.send_message("ادمین اصلی را اضافه نکن. یک آیدی دیگر بده:")
        return ADM_ADD_UID

    context.user_data["new_admin_uid"] = uid
    await update.effective_chat.send_message("👤 نام/یوزرنیم ادمین را وارد کنید (مثلاً @ali یا Ali):")
    return ADM_ADD_NAME


async def adm_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_primary_admin(user.id):
        await update.effective_chat.send_message("⛔ فقط ادمین اصلی.")
        context.user_data.clear()
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message("نام خالی است. دوباره:")
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
            ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, added_at=excluded.added_at
            """,
            (uid, name, now_ts()),
        )
        conn.commit()

    # IMPORTANT: do NOT jump to start/main menu
    await update.effective_chat.send_message("✅ اضافه شد.", reply_markup=build_admin_panel_kb())
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# CATEGORIES (NO TEXT LIST; only buttons)
# ---------------------------
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


def build_cat_kb(scope: str, owner: int, grp: str) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    rows: List[List[InlineKeyboardButton]] = []

    cats = fetch_cats(scope, owner, grp)
    for r in cats[:80]:
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
                ]
            )

    rows.append([InlineKeyboardButton("➕ افزودن", callback_data=f"{CB_CT}:add:{grp}")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_ST}:cats")])
    return InlineKeyboardMarkup(rows)


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
        await q.edit_message_text(f"🧩 {grp_label(grp)}", reply_markup=build_cat_kb(scope, owner, grp))
        return ConversationHandler.END

    if act == "add":
        grp = parts[2]
        context.user_data.clear()
        context.user_data["cat_grp"] = grp
        await q.edit_message_text(f"نام نوع جدید برای «{grp_label(grp)}» را وارد کنید:")
        return CAT_ADD_NAME

    if act == "del":
        cid = int(parts[2])
        with db_conn() as conn:
            row = conn.execute(
                "SELECT grp, name, is_locked FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cid, scope, owner),
            ).fetchone()
            if not row:
                await q.edit_message_text("پیدا نشد.")
                return ConversationHandler.END
            if row["grp"] == "personal_out" and row["name"] == INSTALLMENT_NAME and int(row["is_locked"]) == 1:
                await q.edit_message_text("⛔ نوع «قسط» قفل است و حذف نمی‌شود.")
                return ConversationHandler.END
            conn.execute("DELETE FROM categories WHERE id=?", (cid,))
            conn.commit()

        grp = row["grp"]
        await q.edit_message_text("✅ حذف شد.", reply_markup=build_cat_kb(scope, owner, grp))
        return ConversationHandler.END

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


async def cat_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message("نام خالی است. دوباره وارد کنید:")
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

    # IMPORTANT: no main menu, no text list
    await update.effective_chat.send_message("✅ اضافه شد.", reply_markup=build_cat_kb(scope, owner, grp))
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# TRANSACTIONS
# ---------------------------
def cat_pick_keyboard(scope: str, owner: int, grp: str) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    cats = fetch_cats(scope, owner, grp)
    rows: List[List[InlineKeyboardButton]] = []
    for r in cats[:60]:
        rows.append([InlineKeyboardButton(r["name"], callback_data=f"{CB_TX}:cat:{r['id']}")])
    rows.append([InlineKeyboardButton("➕ افزودن نوع جدید", callback_data=f"{CB_TX}:cat_add")])
    rows.append([InlineKeyboardButton("⬅️ لغو", callback_data=f"{CB_TX}:cancel")])
    return InlineKeyboardMarkup(rows)


async def tx_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "cancel":
        context.user_data.clear()
        await q.edit_message_text("لغو شد.", reply_markup=tx_menu())
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        await q.edit_message_text(
            "نوع تراکنش را انتخاب کنید:",
            reply_markup=ikb(
                [
                    [("💰 درآمد کاری", f"{CB_TX}:tt:work_in")],
                    [("🏢 هزینه کاری", f"{CB_TX}:tt:work_out")],
                    [("👤 هزینه شخصی", f"{CB_TX}:tt:personal_out")],
                    [("⬅️ بازگشت", f"{CB_M}:tx")],
                ]
            ),
        )
        return TX_TTYPE

    if act == "list":
        which = parts[2]
        scope, owner = resolve_scope_owner(user.id)

        if which == "today":
            start = end = today_g()
            title = "📄 لیست امروز"
        else:
            start, end = month_range_for(today_g())
            title = "📄 لیست این ماه (میلادی)"

        with db_conn() as conn:
            rows = conn.execute(
                """
                SELECT date_g, ttype, category, amount, description
                FROM transactions
                WHERE scope=? AND owner_user_id=? AND date_g BETWEEN ? AND ?
                ORDER BY date_g DESC, id DESC
                LIMIT 120
                """,
                (scope, owner, start, end),
            ).fetchall()

        if not rows:
            text = f"<b>{title}</b>\n\n📄 هیچ تراکنشی ثبت نشده."
        else:
            lines = [f"<b>{title}</b>\n"]
            for r in rows:
                desc = (r["description"] or "").strip()
                desc_part = f" — {desc}" if desc else ""
                lines.append(
                    f"• <b>{r['date_g']}</b> ({g_to_j(r['date_g'])}) | {ttype_label(r['ttype'])} | "
                    f"{r['category']} | <b>{int(r['amount'])}</b>{desc_part}"
                )
            text = "\n".join(lines)

        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=tx_menu())
        return ConversationHandler.END

    if act == "tt":
        ttype = parts[2]
        context.user_data["tx_ttype"] = ttype
        tg = today_g()
        tj = g_to_j(tg)
        await q.edit_message_text(
            "📅 تاریخ را انتخاب کنید:\n\n"
            f"امروز (میلادی): {tg}\n"
            f"امروز (شمسی): {tj}\n\n"
            "🔸 محاسبات ماه فقط بر اساس ماه میلادی است.\n"
            "اگر تاریخ شمسی وارد کنید تبدیل می‌کنیم.",
            reply_markup=ikb(
                [
                    [("✅ امروز", f"{CB_TX}:d:today")],
                    [("🗓 وارد کردن تاریخ میلادی", f"{CB_TX}:d:g")],
                    [("🧿 وارد کردن تاریخ شمسی", f"{CB_TX}:d:j")],
                    [("⬅️ لغو", f"{CB_TX}:cancel")],
                ]
            ),
        )
        return TX_DATE_MENU

    if act == "d":
        mode = parts[2]
        if mode == "today":
            context.user_data["tx_date_g"] = today_g()
            scope, owner = resolve_scope_owner(user.id)
            ttype = context.user_data.get("tx_ttype")
            await q.edit_message_text("🏷 دسته را انتخاب کنید:", reply_markup=cat_pick_keyboard(scope, owner, ttype))
            return TX_CAT_PICK

        if mode == "g":
            await q.edit_message_text("تاریخ میلادی را وارد کنید (YYYY-MM-DD):")
            return TX_DATE_G

        if mode == "j":
            await q.edit_message_text("تاریخ شمسی را وارد کنید (YYYY/MM/DD):")
            return TX_DATE_J

        await q.edit_message_text("حالت نامعتبر.", reply_markup=tx_menu())
        return ConversationHandler.END

    await q.edit_message_text("دستور ناشناخته.", reply_markup=tx_menu())
    return ConversationHandler.END


async def tx_date_g_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_gregorian(update.message.text or "")
    if not g:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید (YYYY-MM-DD):")
        return TX_DATE_G

    context.user_data["tx_date_g"] = g
    scope, owner = resolve_scope_owner(user.id)
    ttype = context.user_data.get("tx_ttype")

    await update.effective_chat.send_message("🏷 دسته را انتخاب کنید:", reply_markup=cat_pick_keyboard(scope, owner, ttype))
    return TX_CAT_PICK


async def tx_date_j_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_jalali_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید (YYYY/MM/DD):")
        return TX_DATE_J

    context.user_data["tx_date_g"] = g
    scope, owner = resolve_scope_owner(user.id)
    ttype = context.user_data.get("tx_ttype")

    await update.effective_chat.send_message(f"✅ تبدیل شد به میلادی: {g}\n\n🏷 دسته را انتخاب کنید:",
                                            reply_markup=cat_pick_keyboard(scope, owner, ttype))
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

    if act == "cancel":
        context.user_data.clear()
        await q.edit_message_text("لغو شد.", reply_markup=tx_menu())
        return ConversationHandler.END

    if act == "cat_add":
        await q.edit_message_text("نام نوع جدید را وارد کنید:")
        return TX_CAT_ADD_NAME

    if act == "cat":
        try:
            cid = int(parts[2])
        except Exception:
            await q.edit_message_text("نوع نامعتبر.", reply_markup=tx_menu())
            context.user_data.clear()
            return ConversationHandler.END

        scope, owner = resolve_scope_owner(user.id)
        ttype = context.user_data.get("tx_ttype")

        with db_conn() as conn:
            row = conn.execute(
                "SELECT name FROM categories WHERE id=? AND scope=? AND owner_user_id=? AND grp=?",
                (cid, scope, owner, ttype),
            ).fetchone()
        if not row:
            await q.edit_message_text("دسته پیدا نشد. دوباره انتخاب کنید.")
            return TX_CAT_PICK

        context.user_data["tx_category"] = row["name"]
        await q.edit_message_text("💵 مبلغ را وارد کنید (عدد صحیح):")
        return TX_AMOUNT

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


async def tx_cat_add_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message("نام خالی است. دوباره وارد کنید:")
        return TX_CAT_ADD_NAME

    scope, owner = resolve_scope_owner(user.id)
    ttype = context.user_data.get("tx_ttype")
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
    await update.effective_chat.send_message("✅ نوع اضافه شد.\n💵 حالا مبلغ را وارد کنید:")
    return TX_AMOUNT


async def tx_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    t = (update.message.text or "").strip().replace(",", "").replace("،", "")
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message("❌ مبلغ نامعتبر است. فقط عدد وارد کنید:")
        return TX_AMOUNT

    context.user_data["tx_amount"] = int(t)
    await update.effective_chat.send_message("📝 توضیحات (اختیاری) را وارد کنید یا /skip بزنید:")
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
        await update.effective_chat.send_message("خطا: اطلاعات ناقص است.")
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

    # IMPORTANT: do NOT force main menu
    await update.effective_chat.send_message(
        "✅ تراکنش ثبت شد.\n"
        f"📅 {date_g_} ({g_to_j(date_g_)})\n"
        f"🏷 {category}\n"
        f"💵 {amount}\n"
        f"📝 {desc or '-'}",
        reply_markup=tx_menu(),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# REPORTS
# ---------------------------
def summary_text(scope: str, owner: int, start_g: str, end_g: str, title: str) -> str:
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

    sums: Dict[str, int] = {r["ttype"]: int(r["s"] or 0) for r in rows}
    w_in = sums.get("work_in", 0)
    w_out = sums.get("work_out", 0)
    p_out = sums.get("personal_out", 0)
    net = w_in - (w_out + p_out)

    return (
        f"<b>{title}</b>\n"
        f"📅 بازه: <b>{start_g}</b> تا <b>{end_g}</b>\n"
        f"💰 درآمد: <b>{w_in}</b>\n"
        f"🏢 هزینه کاری: <b>{w_out}</b>\n"
        f"👤 هزینه شخصی: <b>{p_out}</b>\n"
        f"📌 تراز: <b>{net}</b>"
    )


async def rp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "sum":
        which = parts[2]
        if which == "today":
            start = end = today_g()
            title = "📅 خلاصه امروز"
        else:
            start, end = month_range_for(today_g())
            title = "🗓 خلاصه این ماه (میلادی)"
        text = summary_text(scope, owner, start, end, title)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=rp_menu())
        return ConversationHandler.END

    if act == "range":
        context.user_data.clear()
        await q.edit_message_text(
            "تاریخ شروع را وارد کنید:\n"
            "✅ میلادی: YYYY-MM-DD\n"
            "✅ شمسی: YYYY/MM/DD"
        )
        return RP_START

    await q.edit_message_text("دستور ناشناخته.", reply_markup=rp_menu())
    return ConversationHandler.END


async def rp_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_any_date_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید:")
        return RP_START

    context.user_data["rp_start"] = g
    await update.effective_chat.send_message("تاریخ پایان را وارد کنید:")
    return RP_END


async def rp_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g2 = parse_any_date_to_g(update.message.text or "")
    if not g2:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید:")
        return RP_END

    g1 = context.user_data.get("rp_start")
    if not g1:
        await update.effective_chat.send_message("خطا.")
        context.user_data.clear()
        return ConversationHandler.END

    if g2 < g1:
        g1, g2 = g2, g1

    scope, owner = resolve_scope_owner(user.id)
    text = summary_text(scope, owner, g1, g2, "📆 گزارش بازه دلخواه")
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=rp_menu())
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# UNKNOWN handlers (do not break valid callbacks)
# ---------------------------
async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await update.effective_chat.send_message("از /start شروع کنید.", reply_markup=main_menu())


async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()
    try:
        await q.edit_message_text("دکمه نامعتبر/قدیمی است.", reply_markup=main_menu())
    except Exception:
        await update.effective_chat.send_message("دکمه نامعتبر/قدیمی است.", reply_markup=main_menu())


# ---------------------------
# BUILD APP
# ---------------------------
def build_app() -> Application:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(main_cb, pattern=r"^m:(home|tx|rp|st)$"))

    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^st:(cats|access|back)$"))
    app.add_handler(CallbackQueryHandler(access_cb, pattern=r"^ac:(mode:(admin_only|public)|share)$"))

    # Admin panel + conversation for adding admin
    app.add_handler(CallbackQueryHandler(admin_panel_cb, pattern=r"^ad:(panel|del:\d+|noop)$"))
    adm_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_panel_cb, pattern=r"^ad:add$")],
        states={
            ADM_ADD_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_uid)],
            ADM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_name)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="adm_conv",
        persistent=False,
    )
    app.add_handler(adm_conv)

    # Categories conversation
    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:add:(work_in|work_out|personal_out)$")],
        states={CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_add_name)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="cat_conv",
        persistent=False,
    )
    app.add_handler(cat_conv)
    app.add_handler(CallbackQueryHandler(cats_cb, pattern=r"^ct:(grp:(work_in|work_out|personal_out)|del:\d+|noop)$"))

    # Transactions conversation
    tx_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(tx_cb, pattern=r"^tx:(add|list:(today|month))$")],
        states={
            TX_TTYPE: [CallbackQueryHandler(tx_cb, pattern=r"^tx:(tt:(work_in|work_out|personal_out)|cancel)$")],
            TX_DATE_MENU: [CallbackQueryHandler(tx_cb, pattern=r"^tx:(d:(today|g|j)|cancel)$")],
            TX_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_g_input)],
            TX_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_j_input)],
            TX_CAT_PICK: [CallbackQueryHandler(tx_cat_pick_cb, pattern=r"^tx:(cat:\d+|cat_add|cancel)$")],
            TX_CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_cat_add_name_input)],
            TX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_amount_input)],
            TX_DESC: [CommandHandler("skip", tx_desc_skip), MessageHandler(filters.TEXT & ~filters.COMMAND, tx_desc_input)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="tx_conv",
        persistent=False,
    )
    app.add_handler(tx_conv)

    # Reports conversation
    rp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(rp_cb, pattern=r"^rp:(sum:(today|month)|range)$")],
        states={
            RP_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, rp_start)],
            RP_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, rp_end)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="rp_conv",
        persistent=False,
    )
    app.add_handler(rp_conv)
    app.add_handler(CallbackQueryHandler(rp_cb, pattern=r"^rp:(sum:(today|month)|range)$"))

    # Unknown callbacks ONLY
    app.add_handler(
        CallbackQueryHandler(
            unknown_callback,
            pattern=r"^(?!m:|tx:|rp:|st:|ac:|ad:|ct:).+",
        ),
        group=90,
    )

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text), group=99)
    return app


def main() -> None:
    app = build_app()
    logger.info("%s started. TZ=%s DB=%s", PROJECT_NAME, "Asia/Tehran", DB_PATH)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
