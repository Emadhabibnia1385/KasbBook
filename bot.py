# bot.py
# KasbBook - Inline-only stable bot (Daily list + editable rows)
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
CB_DL = "dl"    # daily list
CB_DTX = "dtx"  # daily tx view/edit

RLM = "\u200f"  # Right-to-left mark (best effort for RTL in Telegram)

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
    """
    public: always private per user
    admin_only:
        share=1 => shared, owner=ADMIN_CHAT_ID
        share=0 => private per admin
    """
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


def rtl_lines(lines: List[str]) -> str:
    # best-effort RTL: prepend RLM to each line
    return "\n".join([(RLM + ln) for ln in lines])


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
            [("📄 لیست روزانه", f"{CB_DL}:pick")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )


def rp_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📅 خلاصه امروز", f"{CB_RP}:sum:today")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )


def settings_menu(user_id: int) -> InlineKeyboardMarkup:
    rows = [[("🧩 مدیریت دسته‌ها", f"{CB_ST}:cats")]]
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
ADM_ADD_UID, ADM_ADD_NAME = range(2)
CAT_ADD_NAME = 0

DL_DATE_MENU, DL_DATE_G, DL_DATE_J = range(3)
ED_AMOUNT, ED_DESC = range(2)

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
        rtl_lines([f"🏠 {PROJECT_NAME}", "", "یک گزینه انتخاب کنید:"]),
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
        await q.edit_message_text(rtl_lines(["🏠 منوی اصلی:"]), reply_markup=main_menu())
    elif action == "tx":
        await q.edit_message_text(rtl_lines(["📌 تراکنش‌ها:"]), reply_markup=tx_menu())
    elif action == "rp":
        await q.edit_message_text(rtl_lines(["📊 گزارش‌ها:"]), reply_markup=rp_menu())
    elif action == "st":
        await q.edit_message_text(rtl_lines(["⚙️ تنظیمات:"]), reply_markup=settings_menu(user.id))
    else:
        await q.edit_message_text(rtl_lines(["دستور ناشناخته."]))


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
        await q.edit_message_text(rtl_lines(["🧩 مدیریت دسته‌ها:"]), reply_markup=cats_root_menu())
        return
    if action == "access":
        if not is_primary_admin(user.id):
            await q.edit_message_text(rtl_lines(["⛔ فقط ادمین اصلی."]), reply_markup=settings_menu(user.id))
            return
        await q.edit_message_text(rtl_lines(["🔐 دسترسی ربات:"]), reply_markup=access_menu(user.id))
        return
    if action == "back":
        await q.edit_message_text(rtl_lines(["⚙️ تنظیمات:"]), reply_markup=settings_menu(user.id))
        return

    await q.edit_message_text(rtl_lines(["دستور ناشناخته."]))


async def access_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    if not is_primary_admin(user.id):
        await q.edit_message_text(rtl_lines(["⛔ فقط ادمین اصلی."]), reply_markup=settings_menu(user.id))
        return

    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "mode":
        mode = parts[2]
        if mode not in (ACCESS_ADMIN_ONLY, ACCESS_PUBLIC):
            await q.edit_message_text(rtl_lines(["حالت نامعتبر."]), reply_markup=access_menu(user.id))
            return
        set_setting("access_mode", mode)
        await q.edit_message_text(rtl_lines(["✅ انجام شد."]), reply_markup=access_menu(user.id))
        return

    if act == "share":
        if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
            await q.edit_message_text(rtl_lines(["این گزینه فقط در حالت ادمین فعال است."]), reply_markup=access_menu(user.id))
            return
        cur = get_setting("share_enabled")
        set_setting("share_enabled", "0" if cur == "1" else "1")
        await q.edit_message_text(rtl_lines(["✅ انجام شد."]), reply_markup=access_menu(user.id))
        return

    await q.edit_message_text(rtl_lines(["دستور ناشناخته."]), reply_markup=access_menu(user.id))


# ---------------------------
# ADMIN MANAGEMENT
# ---------------------------
def build_admin_panel_kb() -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton("➕ اضافه کردن ادمین", callback_data=f"{CB_AD}:add")])

    with db_conn() as conn:
        admins = conn.execute("SELECT user_id, name FROM admins ORDER BY added_at DESC").fetchall()

    for r in admins[:80]:
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
        await q.edit_message_text(rtl_lines(["⛔ فقط ادمین اصلی."]), reply_markup=access_menu(user.id))
        return ConversationHandler.END

    if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
        await q.edit_message_text(rtl_lines(["این بخش فقط در حالت ادمین فعال است."]), reply_markup=access_menu(user.id))
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    act = parts[1]

    if act in ("panel", "noop"):
        await q.edit_message_text(rtl_lines(["👥 مدیریت ادمین‌ها:"]), reply_markup=build_admin_panel_kb())
        return ConversationHandler.END

    if act == "del":
        try:
            uid = int(parts[2])
        except Exception:
            await q.edit_message_text(rtl_lines(["آیدی نامعتبر."]), reply_markup=build_admin_panel_kb())
            return ConversationHandler.END

        with db_conn() as conn:
            conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
            conn.commit()

        await q.edit_message_text(rtl_lines(["✅ حذف شد.", "", "👥 مدیریت ادمین‌ها:"]), reply_markup=build_admin_panel_kb())
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        await q.edit_message_text(rtl_lines(["🆔 user_id عددی ادمین جدید را وارد کنید:"]))
        return ADM_ADD_UID

    await q.edit_message_text(rtl_lines(["دستور ناشناخته."]), reply_markup=build_admin_panel_kb())
    return ConversationHandler.END


async def adm_add_uid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_primary_admin(user.id):
        await update.effective_chat.send_message(rtl_lines(["⛔ فقط ادمین اصلی."]))
        context.user_data.clear()
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message(rtl_lines(["❌ فقط user_id عددی وارد کنید:"]))
        return ADM_ADD_UID

    uid = int(t)
    if uid == ADMIN_CHAT_ID:
        await update.effective_chat.send_message(rtl_lines(["ادمین اصلی را اضافه نکن. یک آیدی دیگر بده:"]))
        return ADM_ADD_UID

    context.user_data["new_admin_uid"] = uid
    await update.effective_chat.send_message(rtl_lines(["👤 نام/یوزرنیم ادمین را وارد کنید (مثلاً @ali یا Ali):"]))
    return ADM_ADD_NAME


async def adm_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_primary_admin(user.id):
        await update.effective_chat.send_message(rtl_lines(["⛔ فقط ادمین اصلی."]))
        context.user_data.clear()
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message(rtl_lines(["نام خالی است. دوباره:"]))
        return ADM_ADD_NAME

    uid = context.user_data.get("new_admin_uid")
    if not isinstance(uid, int):
        await update.effective_chat.send_message(rtl_lines(["خطا."]))
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
        rtl_lines(["✅ اضافه شد.", "", "👥 مدیریت ادمین‌ها:"]),
        reply_markup=build_admin_panel_kb(),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# CATEGORIES (buttons only) + add button at TOP
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

    # add on top
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
                ]
            )

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
        await q.edit_message_text(rtl_lines([f"🧩 {grp_label(grp)}"]), reply_markup=build_cat_kb(scope, owner, grp))
        return ConversationHandler.END

    if act == "add":
        grp = parts[2]
        context.user_data.clear()
        context.user_data["cat_grp"] = grp
        await q.edit_message_text(rtl_lines([f"نام دسته جدید برای «{grp_label(grp)}» را وارد کنید:"]))
        return CAT_ADD_NAME

    if act == "del":
        cid = int(parts[2])
        with db_conn() as conn:
            row = conn.execute(
                "SELECT grp, name, is_locked FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cid, scope, owner),
            ).fetchone()
            if not row:
                await q.edit_message_text(rtl_lines(["پیدا نشد."]))
                return ConversationHandler.END
            if row["grp"] == "personal_out" and row["name"] == INSTALLMENT_NAME and int(row["is_locked"]) == 1:
                await q.edit_message_text(rtl_lines(["⛔ دسته «قسط» قفل است و حذف نمی‌شود."]))
                return ConversationHandler.END
            conn.execute("DELETE FROM categories WHERE id=?", (cid,))
            conn.commit()

        grp = row["grp"]
        await q.edit_message_text(rtl_lines(["✅ حذف شد.", "", f"🧩 {grp_label(grp)}"]), reply_markup=build_cat_kb(scope, owner, grp))
        return ConversationHandler.END

    await q.edit_message_text(rtl_lines(["دستور ناشناخته."]))
    return ConversationHandler.END


async def cat_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message(rtl_lines(["نام خالی است. دوباره وارد کنید:"]))
        return CAT_ADD_NAME

    grp = context.user_data.get("cat_grp")
    if grp not in ("work_in", "work_out", "personal_out"):
        await update.effective_chat.send_message(rtl_lines(["خطا."]))
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
        rtl_lines(["✅ اضافه شد.", "", f"🧩 {grp_label(grp)}"]),
        reply_markup=build_cat_kb(scope, owner, grp),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# TRANSACTIONS - Add flow (rename labels to "دسته")
# ---------------------------
def cat_pick_keyboard(scope: str, owner: int, grp: str) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    cats = fetch_cats(scope, owner, grp)
    rows: List[List[InlineKeyboardButton]] = []
    for r in cats[:80]:
        rows.append([InlineKeyboardButton(r["name"], callback_data=f"{CB_TX}:cat:{r['id']}")])
    rows.append([InlineKeyboardButton("➕ افزودن دسته جدید", callback_data=f"{CB_TX}:cat_add")])
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
        await q.edit_message_text(rtl_lines(["لغو شد."]), reply_markup=tx_menu())
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        await q.edit_message_text(
            rtl_lines(["دسته‌بندی تراکنش را انتخاب کنید:"]),
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

    if act == "tt":
        ttype = parts[2]
        context.user_data["tx_ttype"] = ttype
        tg = today_g()
        tj = g_to_j(tg)
        await q.edit_message_text(
            rtl_lines([
                "📅 تاریخ را انتخاب کنید:",
                "",
                f"امروز (میلادی): {tg}",
                f"امروز (شمسی): {tj}",
                "",
                "🔸 محاسبات ماه فقط بر اساس ماه میلادی است.",
                "اگر تاریخ شمسی وارد کنید تبدیل می‌کنیم.",
            ]),
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
            await q.edit_message_text(rtl_lines(["🏷 دسته را انتخاب کنید:"]), reply_markup=cat_pick_keyboard(scope, owner, ttype))
            return TX_CAT_PICK

        if mode == "g":
            await q.edit_message_text(rtl_lines(["تاریخ میلادی را وارد کنید (YYYY-MM-DD):"]))
            return TX_DATE_G

        if mode == "j":
            await q.edit_message_text(rtl_lines(["تاریخ شمسی را وارد کنید (YYYY/MM/DD):"]))
            return TX_DATE_J

        await q.edit_message_text(rtl_lines(["حالت نامعتبر."]), reply_markup=tx_menu())
        return ConversationHandler.END

    await q.edit_message_text(rtl_lines(["دستور ناشناخته."]), reply_markup=tx_menu())
    return ConversationHandler.END


async def tx_date_g_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_gregorian(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl_lines(["❌ تاریخ نامعتبر است. دوباره وارد کنید (YYYY-MM-DD):"]))
        return TX_DATE_G

    context.user_data["tx_date_g"] = g
    scope, owner = resolve_scope_owner(user.id)
    ttype = context.user_data.get("tx_ttype")

    await update.effective_chat.send_message(rtl_lines(["🏷 دسته را انتخاب کنید:"]), reply_markup=cat_pick_keyboard(scope, owner, ttype))
    return TX_CAT_PICK


async def tx_date_j_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_jalali_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl_lines(["❌ تاریخ نامعتبر است. دوباره وارد کنید (YYYY/MM/DD):"]))
        return TX_DATE_J

    context.user_data["tx_date_g"] = g
    scope, owner = resolve_scope_owner(user.id)
    ttype = context.user_data.get("tx_ttype")

    await update.effective_chat.send_message(
        rtl_lines([f"✅ تبدیل شد به میلادی: {g}", "", "🏷 دسته را انتخاب کنید:"]),
        reply_markup=cat_pick_keyboard(scope, owner, ttype),
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

    if act == "cancel":
        context.user_data.clear()
        await q.edit_message_text(rtl_lines(["لغو شد."]), reply_markup=tx_menu())
        return ConversationHandler.END

    if act == "cat_add":
        await q.edit_message_text(rtl_lines(["نام دسته جدید را وارد کنید:"]))
        return TX_CAT_ADD_NAME

    if act == "cat":
        try:
            cid = int(parts[2])
        except Exception:
            await q.edit_message_text(rtl_lines(["دسته نامعتبر."]), reply_markup=tx_menu())
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
            await q.edit_message_text(rtl_lines(["دسته پیدا نشد. دوباره انتخاب کنید."]))
            return TX_CAT_PICK

        context.user_data["tx_category"] = row["name"]
        await q.edit_message_text(rtl_lines(["💵 مبلغ را وارد کنید (عدد صحیح):"]))
        return TX_AMOUNT

    await q.edit_message_text(rtl_lines(["دستور ناشناخته."]))
    return ConversationHandler.END


async def tx_cat_add_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message(rtl_lines(["نام خالی است. دوباره وارد کنید:"]))
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
    await update.effective_chat.send_message(rtl_lines(["✅ دسته اضافه شد.", "💵 حالا مبلغ را وارد کنید:"]))
    return TX_AMOUNT


async def tx_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    t = (update.message.text or "").strip().replace(",", "").replace("،", "")
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message(rtl_lines(["❌ مبلغ نامعتبر است. فقط عدد وارد کنید:"]))
        return TX_AMOUNT

    context.user_data["tx_amount"] = int(t)
    await update.effective_chat.send_message(rtl_lines(["📝 توضیحات (اختیاری) را وارد کنید یا /skip بزنید:"]))
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
        await update.effective_chat.send_message(rtl_lines(["خطا: اطلاعات ناقص است."]))
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

    lines = [
        "✅ تراکنش ثبت شد.",
        "",
        f"📅 تاریخ (میلادی): {date_g_}",
        f"📅 تاریخ (شمسی): {g_to_j(date_g_)}",
        f"🔖 دسته‌بندی: {ttype_label(ttype)}",
        f"🏷 دسته: {category}",
        f"💵 مبلغ: {amount}",
        f"📝 توضیح: {desc or '-'}",
    ]
    await update.effective_chat.send_message(rtl_lines(lines), reply_markup=tx_menu())
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# REPORTS (simple)
# ---------------------------
async def rp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    g = today_g()

    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT ttype, SUM(amount) AS s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g=?
            GROUP BY ttype
            """,
            (scope, owner, g),
        ).fetchall()

    sums = {r["ttype"]: int(r["s"] or 0) for r in rows}
    w_in = sums.get("work_in", 0)
    w_out = sums.get("work_out", 0)
    p_out = sums.get("personal_out", 0)

    lines = [
        "📊 خلاصه امروز",
        "",
        f"📅 تاریخ: {g} ({g_to_j(g)})",
        f"💰 درآمد کاری: {w_in}",
        f"🏢 هزینه کاری: {w_out}",
        f"👤 هزینه شخصی: {p_out}",
    ]
    await q.edit_message_text(rtl_lines(lines), reply_markup=rp_menu())
    return ConversationHandler.END


# ---------------------------
# DAILY LIST (pick date -> summary + filter buttons + rows)
# ---------------------------
def daily_pick_menu() -> InlineKeyboardMarkup:
    g = today_g()
    j = g_to_j(g)
    return ikb(
        [
            [("✅ امروز", f"{CB_DL}:d:today")],
            [("🗓 وارد کردن تاریخ میلادی", f"{CB_DL}:d:g")],
            [("🧿 وارد کردن تاریخ شمسی", f"{CB_DL}:d:j")],
            [("⬅️ بازگشت", f"{CB_M}:tx")],
        ]
    )


def daily_filter_kb(gdate: str, flt: str) -> InlineKeyboardMarkup:
    # flt: all/work_in/work_out/personal_out
    def mark(key: str) -> str:
        return " ✅" if flt == key else ""

    rows = [
        [("💰 درآمد کاری" + mark("work_in"), f"{CB_DL}:view:{gdate}:work_in"),
         ("🏢 هزینه کاری" + mark("work_out"), f"{CB_DL}:view:{gdate}:work_out")],
        [("👤 هزینه شخصی" + mark("personal_out"), f"{CB_DL}:view:{gdate}:personal_out"),
         ("📄 همه" + mark("all"), f"{CB_DL}:view:{gdate}:all")],
        [("⬅️ بازگشت", f"{CB_TX}:back_to_menu")],
    ]
    return ikb(rows)


def daily_rows_kb(scope: str, owner: int, gdate: str, flt: str) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    # filter buttons
    fkb = daily_filter_kb(gdate, flt)
    for r in fkb.inline_keyboard:
        rows.append(r)

    # list rows
    with db_conn() as conn:
        params = [scope, owner, gdate]
        where = "scope=? AND owner_user_id=? AND date_g=?"
        if flt in ("work_in", "work_out", "personal_out"):
            where += " AND ttype=?"
            params.append(flt)

        txs = conn.execute(
            f"""
            SELECT id, ttype, category, amount
            FROM transactions
            WHERE {where}
            ORDER BY id DESC
            LIMIT 80
            """,
            tuple(params),
        ).fetchall()

    if not txs:
        rows.append([InlineKeyboardButton("— هیچ تراکنشی نیست —", callback_data=f"{CB_DL}:noop")])
        return InlineKeyboardMarkup(rows)

    for t in txs:
        txt = f"{t['category']} | {int(t['amount'])}"
        rows.append([InlineKeyboardButton(txt, callback_data=f"{CB_DTX}:open:{gdate}:{t['id']}")])

    return InlineKeyboardMarkup(rows)


def daily_summary_text(scope: str, owner: int, gdate: str) -> str:
    ensure_installment(scope, owner)

    with db_conn() as conn:
        sums = conn.execute(
            """
            SELECT ttype, SUM(amount) AS s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g=?
            GROUP BY ttype
            """,
            (scope, owner, gdate),
        ).fetchall()

        p_all = conn.execute(
            """
            SELECT SUM(amount) AS s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g=? AND ttype='personal_out'
            """,
            (scope, owner, gdate),
        ).fetchone()["s"]
        p_all = int(p_all or 0)

        p_install = conn.execute(
            """
            SELECT SUM(amount) AS s
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND date_g=? AND ttype='personal_out' AND category=?
            """,
            (scope, owner, gdate, INSTALLMENT_NAME),
        ).fetchone()["s"]
        p_install = int(p_install or 0)

    d = {r["ttype"]: int(r["s"] or 0) for r in sums}
    w_in = d.get("work_in", 0)
    w_out = d.get("work_out", 0)
    p_out = d.get("personal_out", 0)

    net = w_in - w_out
    personal_ex_install = max(p_all - p_install, 0)
    savings = net - personal_ex_install

    lines = [
        "📄 گزارش روزانه",
        "",
        f"📅 تاریخ: {gdate} ({g_to_j(gdate)})",
        "",
        f"💰 درآمد کاری: {w_in}",
        f"🏢 هزینه کاری: {w_out}",
        f"🧮 درآمد خالص: {net}",
        f"👤 هزینه شخصی (بدون قسط): {personal_ex_install}",
        f"💾 پس‌انداز: {savings}",
        "",
        "⬇️ لیست تراکنش‌ها:",
    ]
    return rtl_lines(lines)


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
        await q.edit_message_text(rtl_lines(["📄 لیست روزانه", "", "تاریخ را انتخاب کنید:"]), reply_markup=daily_pick_menu())
        return DL_DATE_MENU

    if act == "noop":
        return ConversationHandler.END

    if act == "d":
        mode = data[2]
        if mode == "today":
            gdate = today_g()
            scope, owner = resolve_scope_owner(user.id)
            text = daily_summary_text(scope, owner, gdate)
            await q.edit_message_text(text, reply_markup=daily_rows_kb(scope, owner, gdate, "all"))
            return ConversationHandler.END

        if mode == "g":
            await q.edit_message_text(rtl_lines(["تاریخ میلادی را وارد کنید (YYYY-MM-DD):"]))
            return DL_DATE_G

        if mode == "j":
            await q.edit_message_text(rtl_lines(["تاریخ شمسی را وارد کنید (YYYY/MM/DD):"]))
            return DL_DATE_J

    if act == "view":
        # dl:view:<gdate>:<flt>
        gdate = data[2]
        flt = data[3]
        scope, owner = resolve_scope_owner(user.id)
        text = daily_summary_text(scope, owner, gdate)
        await q.edit_message_text(text, reply_markup=daily_rows_kb(scope, owner, gdate, flt))
        return ConversationHandler.END

    await q.edit_message_text(rtl_lines(["دستور ناشناخته."]), reply_markup=tx_menu())
    return ConversationHandler.END


async def dl_date_g_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_gregorian(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl_lines(["❌ تاریخ نامعتبر است. دوباره (YYYY-MM-DD):"]))
        return DL_DATE_G

    scope, owner = resolve_scope_owner(user.id)
    text = daily_summary_text(scope, owner, g)
    await update.effective_chat.send_message(text, reply_markup=daily_rows_kb(scope, owner, g, "all"))
    context.user_data.clear()
    return ConversationHandler.END


async def dl_date_j_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    g = parse_jalali_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message(rtl_lines(["❌ تاریخ نامعتبر است. دوباره (YYYY/MM/DD):"]))
        return DL_DATE_J

    scope, owner = resolve_scope_owner(user.id)
    text = daily_summary_text(scope, owner, g)
    await update.effective_chat.send_message(
        rtl_lines([f"✅ تبدیل شد به میلادی: {g}", ""]) + "\n" + text,
        reply_markup=daily_rows_kb(scope, owner, g, "all"),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------
# DAILY TX VIEW/EDIT
# ---------------------------
def get_tx(scope: str, owner: int, tx_id: int) -> Optional[sqlite3.Row]:
    with db_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM transactions
            WHERE id=? AND scope=? AND owner_user_id=?
            """,
            (tx_id, scope, owner),
        ).fetchone()


def tx_view_kb(gdate: str, tx_id: int) -> InlineKeyboardMarkup:
    return ikb(
        [
            [("✏️ ویرایش دسته", f"{CB_DTX}:cat:{gdate}:{tx_id}")],
            [("✏️ ویرایش مبلغ", f"{CB_DTX}:amt:{gdate}:{tx_id}")],
            [("✏️ ویرایش توضیحات", f"{CB_DTX}:desc:{gdate}:{tx_id}")],
            [("🗑 حذف", f"{CB_DTX}:del:{gdate}:{tx_id}")],
            [("⬅️ بازگشت", f"{CB_DL}:view:{gdate}:all")],
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
        await q.edit_message_text(rtl_lines(["تراکنش پیدا نشد."]), reply_markup=tx_menu())
        return ConversationHandler.END

    if act == "open":
        lines = [
            "🧾 جزئیات تراکنش",
            "",
            f"📅 تاریخ (میلادی): {tx['date_g']}",
            f"📅 تاریخ (شمسی): {g_to_j(tx['date_g'])}",
            f"🔖 دسته‌بندی: {ttype_label(tx['ttype'])}",
            f"🏷 دسته: {tx['category']}",
            f"💵 مبلغ: {int(tx['amount'])}",
            f"📝 توضیح: {(tx['description'] or '-').strip()}",
        ]
        await q.edit_message_text(rtl_lines(lines), reply_markup=tx_view_kb(gdate, tx_id))
        return ConversationHandler.END

    if act == "del":
        with db_conn() as conn:
            conn.execute("DELETE FROM transactions WHERE id=? AND scope=? AND owner_user_id=?", (tx_id, scope, owner))
            conn.commit()
        text = daily_summary_text(scope, owner, gdate)
        await q.edit_message_text(rtl_lines(["✅ حذف شد.", ""]) + "\n" + text, reply_markup=daily_rows_kb(scope, owner, gdate, "all"))
        return ConversationHandler.END

    if act == "amt":
        context.user_data.clear()
        context.user_data["edit_tx_id"] = tx_id
        context.user_data["edit_gdate"] = gdate
        await q.edit_message_text(rtl_lines(["💵 مبلغ جدید را وارد کنید (عدد):"]))
        return ED_AMOUNT

    if act == "desc":
        context.user_data.clear()
        context.user_data["edit_tx_id"] = tx_id
        context.user_data["edit_gdate"] = gdate
        await q.edit_message_text(rtl_lines(["📝 توضیح جدید را وارد کنید (یا - برای حذف):"]))
        return ED_DESC

    if act == "cat":
        # show category picker for tx['ttype']
        ttype = tx["ttype"]
        ensure_installment(scope, owner)
        cats = fetch_cats(scope, owner, ttype)
        rows: List[List[InlineKeyboardButton]] = []
        for c in cats[:80]:
            rows.append([InlineKeyboardButton(c["name"], callback_data=f"{CB_DTX}:setcat:{gdate}:{tx_id}:{c['id']}")])
        rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_DTX}:open:{gdate}:{tx_id}")])
        await q.edit_message_text(rtl_lines(["🏷 دسته جدید را انتخاب کنید:"]), reply_markup=InlineKeyboardMarkup(rows))
        return ConversationHandler.END

    if act == "setcat":
        # dtx:setcat:gdate:txid:catid
        cat_id = int(parts[4])
        with db_conn() as conn:
            row = conn.execute(
                "SELECT name FROM categories WHERE id=? AND scope=? AND owner_user_id=?",
                (cat_id, scope, owner),
            ).fetchone()
            if not row:
                await q.edit_message_text(rtl_lines(["دسته پیدا نشد."]))
                return ConversationHandler.END
            cat_name = row["name"]
            conn.execute(
                "UPDATE transactions SET category=?, updated_at=? WHERE id=? AND scope=? AND owner_user_id=?",
                (cat_name, now_ts(), tx_id, scope, owner),
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
            f"🔖 دسته‌بندی: {ttype_label(tx2['ttype'])}",
            f"🏷 دسته: {tx2['category']}",
            f"💵 مبلغ: {int(tx2['amount'])}",
            f"📝 توضیح: {(tx2['description'] or '-').strip()}",
        ]
        await q.edit_message_text(rtl_lines(lines), reply_markup=tx_view_kb(gdate, tx_id))
        return ConversationHandler.END

    await q.edit_message_text(rtl_lines(["دستور ناشناخته."]))
    return ConversationHandler.END


async def edit_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    t = (update.message.text or "").strip().replace(",", "").replace("،", "")
    if not re.fullmatch(r"\d+", t):
        await update.effective_chat.send_message(rtl_lines(["❌ مبلغ نامعتبر است. فقط عدد وارد کنید:"]))
        return ED_AMOUNT

    tx_id = context.user_data.get("edit_tx_id")
    gdate = context.user_data.get("edit_gdate")
    if not isinstance(tx_id, int) or not isinstance(gdate, str):
        await update.effective_chat.send_message(rtl_lines(["خطا."]))
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
    tx = get_tx(scope, owner, tx_id)
    lines = [
        "✅ ویرایش شد.",
        "",
        "🧾 جزئیات تراکنش",
        "",
        f"📅 تاریخ (میلادی): {tx['date_g']}",
        f"📅 تاریخ (شمسی): {g_to_j(tx['date_g'])}",
        f"🔖 دسته‌بندی: {ttype_label(tx['ttype'])}",
        f"🏷 دسته: {tx['category']}",
        f"💵 مبلغ: {int(tx['amount'])}",
        f"📝 توضیح: {(tx['description'] or '-').strip()}",
    ]
    await update.effective_chat.send_message(rtl_lines(lines), reply_markup=tx_view_kb(gdate, tx_id))
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
        await update.effective_chat.send_message(rtl_lines(["خطا."]))
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
    tx = get_tx(scope, owner, tx_id)
    lines = [
        "✅ ویرایش شد.",
        "",
        "🧾 جزئیات تراکنش",
        "",
        f"📅 تاریخ (میلادی): {tx['date_g']}",
        f"📅 تاریخ (شمسی): {g_to_j(tx['date_g'])}",
        f"🔖 دسته‌بندی: {ttype_label(tx['ttype'])}",
        f"🏷 دسته: {tx['category']}",
        f"💵 مبلغ: {int(tx['amount'])}",
        f"📝 توضیح: {(tx['description'] or '-').strip()}",
    ]
    await update.effective_chat.send_message(rtl_lines(lines), reply_markup=tx_view_kb(gdate, tx_id))
    return ConversationHandler.END


# ---------------------------
# Back helper for tx menu
# ---------------------------
async def tx_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()
    await q.edit_message_text(rtl_lines(["📌 تراکنش‌ها:"]), reply_markup=tx_menu())


# ---------------------------
# UNKNOWN callback (no menus)
# ---------------------------
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


# ---------------------------
# BUILD APP
# ---------------------------
def build_app() -> Application:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # only /start shows main menu automatically
    app.add_handler(CommandHandler("start", start))

    # main navigation
    app.add_handler(CallbackQueryHandler(main_cb, pattern=r"^m:(home|tx|rp|st)$"))

    # tx menu + back
    app.add_handler(CallbackQueryHandler(tx_cb, pattern=r"^tx:(add|tt:(work_in|work_out|personal_out)|d:(today|g|j)|cancel)$"))
    app.add_handler(CallbackQueryHandler(tx_back, pattern=r"^tx:back_to_menu$"))

    # settings
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^st:(cats|access|back)$"))
    app.add_handler(CallbackQueryHandler(access_cb, pattern=r"^ac:(mode:(admin_only|public)|share)$"))

    # admin
    app.add_handler(CallbackQueryHandler(admin_panel_cb, pattern=r"^ad:(panel|del:\d+|noop|add)$"))
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

    # categories
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

    # add transaction conversation
    tx_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(tx_cb, pattern=r"^tx:add$")],
        states={
            TX_TTYPE: [CallbackQueryHandler(tx_cb, pattern=r"^tx:tt:(work_in|work_out|personal_out)$")],
            TX_DATE_MENU: [CallbackQueryHandler(tx_cb, pattern=r"^tx:d:(today|g|j)$|^tx:cancel$")],
            TX_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_g_input)],
            TX_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_j_input)],
            TX_CAT_PICK: [CallbackQueryHandler(tx_cat_pick_cb, pattern=r"^tx:(cat:\d+|cat_add|cancel)$")],
            TX_CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_cat_add_name_input)],
            TX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_amount_input)],
            TX_DESC: [
                CommandHandler("skip", tx_desc_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tx_desc_input),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="tx_conv",
        persistent=False,
    )
    app.add_handler(tx_conv)

    # reports
    app.add_handler(CallbackQueryHandler(rp_cb, pattern=r"^rp:sum:today$"))

    # daily list pick date (conversation)
    dl_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(daily_cb, pattern=r"^dl:pick$")],
        states={
            DL_DATE_MENU: [CallbackQueryHandler(daily_cb, pattern=r"^dl:d:(today|g|j)$")],
            DL_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, dl_date_g_input)],
            DL_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, dl_date_j_input)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="dl_conv",
        persistent=False,
    )
    app.add_handler(dl_conv)

    # daily list view/filter
    app.add_handler(CallbackQueryHandler(daily_cb, pattern=r"^dl:view:\d{4}-\d{2}-\d{2}:(all|work_in|work_out|personal_out)$"))
    app.add_handler(CallbackQueryHandler(daily_cb, pattern=r"^dl:d:(today|g|j)$"))
    app.add_handler(CallbackQueryHandler(daily_cb, pattern=r"^dl:noop$"))

    # daily tx open/edit + edit conversations
    app.add_handler(CallbackQueryHandler(dtx_cb, pattern=r"^dtx:(open|del|amt|desc|cat):\d{4}-\d{2}-\d{2}:\d+$"))
    app.add_handler(CallbackQueryHandler(dtx_cb, pattern=r"^dtx:setcat:\d{4}-\d{2}-\d{2}:\d+:\d+$"))

    edit_amt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:amt:\d{4}-\d{2}-\d{2}:\d+$")],
        states={ED_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_amount_input)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="edit_amt_conv",
        persistent=False,
    )
    app.add_handler(edit_amt_conv)

    edit_desc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:desc:\d{4}-\d{2}-\d{2}:\d+$")],
        states={ED_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_desc_input)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="edit_desc_conv",
        persistent=False,
    )
    app.add_handler(edit_desc_conv)

    # unknown callbacks (no menus)
    app.add_handler(
        CallbackQueryHandler(
            unknown_callback,
            pattern=r"^(?!m:|tx:|rp:|st:|ac:|ad:|ct:|dl:|dtx:).+",
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
