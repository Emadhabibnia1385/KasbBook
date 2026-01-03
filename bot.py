# bot.py
# KasbBook - Finance Manager Telegram Bot
# InlineKeyboard only (NO ReplyKeyboard) + force remove old reply keyboards
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

# ------------------------
# Config
# ------------------------
PROJECT_NAME = "KasbBook"
DB_PATH = "KasbBook.db"
TZ = pytz.timezone("Asia/Tehran")

ACCESS_ADMIN_ONLY = "admin_only"
ACCESS_PUBLIC = "public"

INSTALLMENT_NAME = "قسط"

# callback prefixes (short)
CB_MAIN = "m"
CB_TX = "tx"
CB_RP = "rp"
CB_ST = "st"
CB_AD = "ad"
CB_CT = "ct"
CB_AC = "ac"  # access

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
# DB
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

        if conn.execute("SELECT 1 FROM settings WHERE k='access_mode'").fetchone() is None:
            conn.execute("INSERT INTO settings(k,v) VALUES('access_mode', ?)", (ACCESS_ADMIN_ONLY,))
        if conn.execute("SELECT 1 FROM settings WHERE k='share_enabled'").fetchone() is None:
            conn.execute("INSERT INTO settings(k,v) VALUES('share_enabled','0')")

        conn.commit()


def get_setting(k: str) -> str:
    with db_conn() as conn:
        row = conn.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
        if not row:
            raise RuntimeError(f"Missing setting: {k}")
        return str(row["v"])


def set_setting(k: str, v: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, v),
        )
        conn.commit()


def now_tehran_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def today_g_str() -> str:
    return datetime.now(TZ).date().strftime("%Y-%m-%d")


def g_to_j_str(g_yyyy_mm_dd: str) -> str:
    y, m, d = map(int, g_yyyy_mm_dd.split("-"))
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    return f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}"


def parse_gregorian(text: str) -> Optional[str]:
    s = (text or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        date(y, mo, d)
        return f"{y:04d}-{mo:02d}-{d:02d}"
    except ValueError:
        return None


def parse_jalali_to_g(text: str) -> Optional[str]:
    s = (text or "").strip()
    m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", s)
    if not m:
        return None
    try:
        jy, jm, jd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        g = jdatetime.date(jy, jm, jd).togregorian()
        return g.strftime("%Y-%m-%d")
    except ValueError:
        return None


def month_range_g_for_date(g_yyyy_mm_dd: str) -> Tuple[str, str]:
    y, m, _ = map(int, g_yyyy_mm_dd.split("-"))
    start = date(y, m, 1)
    nm = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    end = nm - timedelta(days=1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def is_admin_user(user_id: int) -> bool:
    if user_id == ADMIN_CHAT_ID:
        return True
    with db_conn() as conn:
        return conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone() is not None


def access_allowed(user_id: int) -> bool:
    mode = get_setting("access_mode")
    if mode == ACCESS_PUBLIC:
        return True
    return is_admin_user(user_id)


def resolve_scope_owner(user_id: int) -> Tuple[str, int]:
    """
    - public: everyone can work on their own private data (scope=private, owner=user_id)
    - admin_only:
        - only admins allowed
        - share_enabled=1: shared scope, owner=ADMIN_CHAT_ID
        - share_enabled=0: private per admin
    """
    mode = get_setting("access_mode")
    if mode == ACCESS_PUBLIC:
        return ("private", user_id)

    # admin_only:
    # this function assumes the caller is already authorized
    if not is_admin_user(user_id):
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


# ------------------------
# Access denied
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


async def deny_update(update: Update) -> None:
    user = update.effective_user
    text = denied_text(user.id, user.username)

    if update.callback_query:
        q = update.callback_query
        try:
            await q.answer()
        except Exception:
            pass
        # try edit; if not possible, send
        try:
            await q.edit_message_text(text)
        except Exception:
            await update.effective_chat.send_message(text, reply_markup=ReplyKeyboardRemove())
    else:
        await update.effective_chat.send_message(text, reply_markup=ReplyKeyboardRemove())


# ------------------------
# UI helpers
# ------------------------
def ikb(rows: List[List[Tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=cb) for (t, cb) in row] for row in rows]
    )


def main_menu_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📌 تراکنش‌ها", f"{CB_MAIN}:tx"), ("📊 گزارش‌ها", f"{CB_MAIN}:rp")],
            [("⚙️ تنظیمات", f"{CB_MAIN}:st")],
        ]
    )


def tx_menu_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("➕ ثبت تراکنش", f"{CB_TX}:add")],
            [("📄 لیست امروز", f"{CB_TX}:list:today"), ("📄 لیست این ماه (میلادی)", f"{CB_TX}:list:month")],
            [("⬅️ منوی اصلی", f"{CB_MAIN}:home")],
        ]
    )


def rp_menu_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📅 خلاصه امروز", f"{CB_RP}:sum:today"), ("🗓 خلاصه این ماه (میلادی)", f"{CB_RP}:sum:month")],
            [("📆 بازه دلخواه", f"{CB_RP}:range")],
            [("⬅️ منوی اصلی", f"{CB_MAIN}:home")],
        ]
    )


def settings_menu_ikb(is_primary_admin: bool) -> InlineKeyboardMarkup:
    rows = [[("🧩 مدیریت نوع‌ها", f"{CB_ST}:cats")]]
    if is_primary_admin:
        rows.append([("🔐 دسترسی ربات", f"{CB_ST}:access")])
    rows.append([("⬅️ منوی اصلی", f"{CB_MAIN}:home")])
    return ikb(rows)


def access_menu_ikb() -> InlineKeyboardMarkup:
    mode = get_setting("access_mode")
    admin_mark = "✅" if mode == ACCESS_ADMIN_ONLY else ""
    public_mark = "✅" if mode == ACCESS_PUBLIC else ""
    rows = [
        [(f"👑 حالت ادمین {admin_mark}", f"{CB_AC}:mode:{ACCESS_ADMIN_ONLY}")],
        [(f"🌐 حالت همگانی {public_mark}", f"{CB_AC}:mode:{ACCESS_PUBLIC}")],
    ]
    if mode == ACCESS_ADMIN_ONLY:
        share = get_setting("share_enabled")
        share_txt = "روشن ✅" if share == "1" else "خاموش ❌"
        rows.append([(f"🔁 اشتراک اطلاعات بین ادمین‌ها: {share_txt}", f"{CB_AC}:share")])
    rows.append([("⬅️ بازگشت", f"{CB_ST}:back")])
    return ikb(rows)


def cats_menu_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("💰 درآمد کاری", f"{CB_CT}:grp:work_in")],
            [("🏢 هزینه کاری", f"{CB_CT}:grp:work_out")],
            [("👤 هزینه شخصی", f"{CB_CT}:grp:personal_out")],
            [("⬅️ منوی اصلی", f"{CB_MAIN}:home")],
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
# States
# ------------------------
TX_TTYPE, TX_DATE_MENU, TX_DATE_G, TX_DATE_J, TX_CAT_PICK, TX_CAT_NEW, TX_AMOUNT, TX_DESC = range(8)
RP_RANGE_START, RP_RANGE_END = range(2)
CAT_ADD_NAME = 0

# ------------------------
# /start
# ------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    # remove any old reply keyboards
    await update.effective_chat.send_message(" ", reply_markup=ReplyKeyboardRemove())

    if not access_allowed(user.id):
        await deny_update(update)
        return

    is_primary = (user.id == ADMIN_CHAT_ID)
    await update.effective_chat.send_message(
        f"سلام! به {PROJECT_NAME} خوش آمدید.\n\nاز منوی زیر انتخاب کنید:",
        reply_markup=main_menu_ikb(),
    )


# ------------------------
# Main callbacks
# ------------------------
async def main_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    await q.answer()

    action = (q.data or "").split(":")[1]
    if action == "home":
        await q.edit_message_text("🏠 منوی اصلی:", reply_markup=main_menu_ikb())
    elif action == "tx":
        await q.edit_message_text("📌 تراکنش‌ها:", reply_markup=tx_menu_ikb())
    elif action == "rp":
        await q.edit_message_text("📊 گزارش‌ها:", reply_markup=rp_menu_ikb())
    elif action == "st":
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=settings_menu_ikb(user.id == ADMIN_CHAT_ID))
    else:
        await q.edit_message_text("دستور ناشناخته.")


# ------------------------
# Settings callbacks
# ------------------------
async def settings_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    await q.answer()

    is_primary = (user.id == ADMIN_CHAT_ID)
    action = (q.data or "").split(":")[1]

    if action == "cats":
        await q.edit_message_text("🧩 مدیریت نوع‌ها:", reply_markup=cats_menu_ikb())
        return
    if action == "access":
        if not is_primary:
            await q.edit_message_text("⛔ این بخش فقط برای ادمین اصلی فعال است.")
            return
        await q.edit_message_text("🔐 دسترسی ربات:", reply_markup=access_menu_ikb())
        return
    if action == "back":
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=settings_menu_ikb(is_primary))
        return

    await q.edit_message_text("دستور ناشناخته.")


async def access_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    await q.answer()

    if user.id != ADMIN_CHAT_ID:
        await q.edit_message_text("⛔ فقط ادمین اصلی.")
        return

    parts = (q.data or "").split(":")
    action = parts[1]

    if action == "mode":
        mode = parts[2]
        if mode not in (ACCESS_ADMIN_ONLY, ACCESS_PUBLIC):
            await q.edit_message_text("حالت نامعتبر.")
            return
        set_setting("access_mode", mode)

        # if switched to public, share irrelevant but keep value; UI hides it.
        await q.edit_message_text("✅ تنظیم شد.\n\n🔐 دسترسی ربات:", reply_markup=access_menu_ikb())
        return

    if action == "share":
        if get_setting("access_mode") != ACCESS_ADMIN_ONLY:
            await q.edit_message_text("این گزینه فقط در حالت ادمین فعال است.", reply_markup=access_menu_ikb())
            return
        cur = get_setting("share_enabled")
        set_setting("share_enabled", "0" if cur == "1" else "1")
        await q.edit_message_text("✅ تنظیم شد.\n\n🔐 دسترسی ربات:", reply_markup=access_menu_ikb())
        return

    await q.edit_message_text("دستور ناشناخته.")


# ------------------------
# Categories (inline management, add needs typing name)
# ------------------------
def fetch_cats(scope: str, owner: int, grp: str) -> List[sqlite3.Row]:
    with db_conn() as conn:
        return list(
            conn.execute(
                "SELECT id, name, is_locked FROM categories WHERE scope=? AND owner_user_id=? AND grp=? ORDER BY is_locked DESC, name",
                (scope, owner, grp),
            ).fetchall()
        )


def build_cat_list(scope: str, owner: int, grp: str) -> Tuple[str, InlineKeyboardMarkup]:
    rows = fetch_cats(scope, owner, grp)

    lines = [f"🧩 <b>{grp_label(grp)}</b>\n"]
    kb: List[List[InlineKeyboardButton]] = []

    if not rows:
        lines.append("— (خالی)")
    else:
        for r in rows[:40]:
            name = r["name"]
            locked = int(r["is_locked"]) == 1
            is_installment = (grp == "personal_out" and name == INSTALLMENT_NAME and locked)

            lines.append(f"• {'🔒 ' if locked else ''}{name}")

            row_btns = [InlineKeyboardButton(name, callback_data=f"{CB_CT}:noop")]
            if not is_installment:
                row_btns.append(InlineKeyboardButton("🗑 حذف", callback_data=f"{CB_CT}:del:{r['id']}"))
            kb.append(row_btns)

    kb.append([InlineKeyboardButton("➕ افزودن", callback_data=f"{CB_CT}:add:{grp}")])
    kb.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_ST}:cats")])
    return "\n".join(lines), InlineKeyboardMarkup(kb)


def resolve_scope_owner(user_id: int) -> Tuple[str, int]:
    mode = get_setting("access_mode")
    if mode == ACCESS_PUBLIC:
        return ("private", user_id)

    # admin_only (caller must be authorized)
    share_enabled = get_setting("share_enabled")
    if share_enabled == "1":
        return ("shared", ADMIN_CHAT_ID)
    return ("private", user_id)


async def cats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)

    parts = (q.data or "").split(":")
    action = parts[1]

    if action == "noop":
        return ConversationHandler.END

    if action == "grp":
        grp = parts[2]
        context.user_data.clear()
        context.user_data["cat_grp"] = grp
        text, markup = build_cat_list(scope, owner, grp)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return ConversationHandler.END

    if action == "add":
        grp = parts[2]
        context.user_data.clear()
        context.user_data["cat_grp"] = grp
        await q.edit_message_text(f"نام نوع جدید برای «{grp_label(grp)}» را وارد کنید:")
        return CAT_ADD_NAME

    if action == "del":
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
        text, markup = build_cat_list(scope, owner, grp)
        await q.edit_message_text("✅ حذف شد.\n\n" + text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return ConversationHandler.END

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


async def cat_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
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

    text, markup = build_cat_list(scope, owner, grp)
    await update.effective_chat.send_message("✅ اضافه شد.\n\n" + text, parse_mode=ParseMode.HTML, reply_markup=markup)
    context.user_data.clear()
    return ConversationHandler.END


# ------------------------
# Transactions / Reports (minimal menus)
# ------------------------
async def tx_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    await q.answer()
    await q.edit_message_text("📌 تراکنش‌ها:", reply_markup=tx_menu_ikb())


async def rp_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    await q.answer()
    await q.edit_message_text("📊 گزارش‌ها:", reply_markup=rp_menu_ikb())


# ------------------------
# Unknown handlers (FIX: no double messages)
# ------------------------
async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    await update.effective_chat.send_message("از /start شروع کنید.", reply_markup=main_menu_ikb())


async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    await q.answer()
    # just go home
    await q.edit_message_text("🏠 منوی اصلی:", reply_markup=main_menu_ikb())


# ------------------------
# Build App
# ------------------------
def build_app() -> Application:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    # main menu callbacks
    app.add_handler(CallbackQueryHandler(main_cb, pattern=r"^m:(home|tx|rp|st)$"))
    app.add_handler(CallbackQueryHandler(tx_menu_cb, pattern=r"^m:tx$"))
    app.add_handler(CallbackQueryHandler(rp_menu_cb, pattern=r"^m:rp$"))

    # settings
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^st:(cats|access|back)$"))
    app.add_handler(CallbackQueryHandler(access_cb, pattern=r"^ac:(mode:(admin_only|public)|share)$"))

    # categories conversation (add name)
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

    # unknown: FIXED to prevent double start/deny
    app.add_handler(CallbackQueryHandler(unknown_callback), group=90)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text), group=99)

    return app


def main() -> None:
    app = build_app()
    logger.info("%s started. TZ=%s DB=%s", PROJECT_NAME, "Asia/Tehran", DB_PATH)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
