# bot.py
# KasbBook - Finance Manager Telegram Bot
# Python 3.10+ | python-telegram-bot v20+ | sqlite3 | pytz | jdatetime | python-dotenv
# InlineKeyboard only (NO ReplyKeyboard)

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
    # IMPORTANT: SQLite syntax must be valid (no "(YYYY-MM-DD)" annotations).
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
    if m == 12:
        nm = date(y + 1, 1, 1)
    else:
        nm = date(y, m + 1, 1)
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
    - Non-admin (public): private per user
    - Admin:
      - share_enabled=1 => shared, owner=ADMIN_CHAT_ID
      - share_enabled=0 => private per admin
    """
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
        try:
            await q.edit_message_text(text)
        except Exception:
            await update.effective_chat.send_message(text)
    else:
        await update.effective_chat.send_message(text)


# ------------------------
# UI helpers (Inline only)
# ------------------------
def ikb(rows: List[List[Tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=cb) for (t, cb) in row] for row in rows]
    )


def main_menu_ikb(is_primary_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [("📌 تراکنش‌ها", f"{CB_MAIN}:tx"), ("📊 گزارش‌ها", f"{CB_MAIN}:rp")],
        [("⚙️ تنظیمات", f"{CB_MAIN}:st")],
    ]
    return ikb(rows)


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
        rows.append([("🛡 بخش ادمین", f"{CB_ST}:admin")])
    rows.append([("⬅️ منوی اصلی", f"{CB_MAIN}:home")])
    return ikb(rows)


def admin_menu_ikb() -> InlineKeyboardMarkup:
    share_enabled = get_setting("share_enabled")
    share_txt = "روشن ✅" if share_enabled == "1" else "خاموش ❌"
    return ikb(
        [
            [("👥 مدیریت ادمین‌ها", f"{CB_AD}:admins")],
            [(f"🔁 اشتراک اطلاعات بین ادمین‌ها: {share_txt}", f"{CB_AD}:share")],
            [("⬅️ بازگشت", f"{CB_ST}:back")],
        ]
    )


def admins_manage_ikb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("➕ اضافه کردن ادمین", f"{CB_AD}:add")],
            [("📋 لیست ادمین‌ها + حذف", f"{CB_AD}:list")],
            [("⬅️ بازگشت", f"{CB_AD}:back2")],
        ]
    )


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
ADM_ADD_UID, ADM_ADD_NAME = range(2)
CAT_ADD_NAME = 0  # single state


# ------------------------
# /start
# ------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    is_primary = (user.id == ADMIN_CHAT_ID)
    await update.effective_chat.send_message(
        f"سلام! به {PROJECT_NAME} خوش آمدید.\n\nاز منوی زیر انتخاب کنید:",
        reply_markup=main_menu_ikb(is_primary),
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
    is_primary = (user.id == ADMIN_CHAT_ID)

    if action == "home":
        await q.edit_message_text("🏠 منوی اصلی:", reply_markup=main_menu_ikb(is_primary))
    elif action == "tx":
        await q.edit_message_text("📌 تراکنش‌ها:", reply_markup=tx_menu_ikb())
    elif action == "rp":
        await q.edit_message_text("📊 گزارش‌ها:", reply_markup=rp_menu_ikb())
    elif action == "st":
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=settings_menu_ikb(is_primary))
    else:
        await q.edit_message_text("دستور ناشناخته.")


# ------------------------
# Transactions
# ------------------------
def fetch_categories(scope: str, owner: int, grp: str) -> List[sqlite3.Row]:
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


async def tx_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    if action == "add":
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

    if action == "list":
        which = parts[2]
        if which == "today":
            start = end = today_g_str()
            title = "📄 لیست امروز"
        else:
            start, end = month_range_g_for_date(today_g_str())
            title = "📄 لیست این ماه (میلادی)"

        text = f"<b>{title}</b>\n\n" + build_tx_list_text(scope, owner, start, end)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=tx_menu_ikb())
        return ConversationHandler.END

    if action == "cancel":
        context.user_data.clear()
        await q.edit_message_text("لغو شد.", reply_markup=tx_menu_ikb())
        return ConversationHandler.END

    if action == "tt":
        ttype = parts[2]
        if ttype not in ("work_in", "work_out", "personal_out"):
            await q.edit_message_text("نوع نامعتبر.")
            return ConversationHandler.END

        context.user_data["tx_ttype"] = ttype

        # Date inline menu (3 options)
        tg = today_g_str()
        tj = g_to_j_str(tg)
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

    if action == "d":
        mode = parts[2]
        if mode == "today":
            context.user_data["tx_date_g"] = today_g_str()
            await q.edit_message_text("✅ تاریخ ثبت شد. حالا دسته را انتخاب کنید...")
            await send_category_picker(update, context)
            return TX_CAT_PICK
        if mode == "g":
            await q.edit_message_text("تاریخ میلادی را وارد کنید (YYYY-MM-DD):")
            return TX_DATE_G
        if mode == "j":
            await q.edit_message_text("تاریخ شمسی را وارد کنید (YYYY/MM/DD):")
            return TX_DATE_J
        await q.edit_message_text("حالت نامعتبر.")
        return ConversationHandler.END

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


async def tx_date_g_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END

    g = parse_gregorian(update.message.text or "")
    if not g:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید (YYYY-MM-DD):")
        return TX_DATE_G

    context.user_data["tx_date_g"] = g
    await update.effective_chat.send_message("✅ تاریخ ثبت شد. حالا دسته را انتخاب کنید...")
    await send_category_picker(update, context)
    return TX_CAT_PICK


async def tx_date_j_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END

    g = parse_jalali_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید (YYYY/MM/DD):")
        return TX_DATE_J

    context.user_data["tx_date_g"] = g
    await update.effective_chat.send_message(f"✅ تبدیل شد به میلادی: {g}\nحالا دسته را انتخاب کنید...")
    await send_category_picker(update, context)
    return TX_CAT_PICK


async def send_category_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ttype = context.user_data.get("tx_ttype")
    if ttype not in ("work_in", "work_out", "personal_out"):
        await update.effective_chat.send_message("خطا: نوع تراکنش مشخص نیست.")
        return

    scope, owner = resolve_scope_owner(user.id)
    ensure_installment(scope, owner)

    cats = fetch_categories(scope, owner, ttype)
    rows = []
    for r in cats[:12]:
        rows.append([(r["name"], f"{CB_TX}:cat:{r['id']}")])
    if len(cats) > 12:
        rows.append([("✍️ وارد کردن دستی نام نوع", f"{CB_TX}:cat_manual")])
    rows.append([("➕ افزودن نوع جدید", f"{CB_TX}:cat_new")])
    rows.append([("⬅️ لغو", f"{CB_TX}:cancel")])

    await update.effective_chat.send_message(
        f"🏷 دسته ({ttype_label(ttype)}) را انتخاب کنید:",
        reply_markup=ikb(rows),
    )


async def tx_cat_pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    action = parts[1]

    if action == "cancel":
        context.user_data.clear()
        await q.edit_message_text("لغو شد.", reply_markup=tx_menu_ikb())
        return ConversationHandler.END

    if action in ("cat_new", "cat_manual"):
        await q.edit_message_text("نام نوع را وارد کنید:")
        return TX_CAT_NEW

    if action == "cat":
        try:
            cid = int(parts[2])
        except ValueError:
            await q.edit_message_text("نوع نامعتبر.")
            context.user_data.clear()
            return ConversationHandler.END

        ttype = context.user_data.get("tx_ttype")
        if ttype not in ("work_in", "work_out", "personal_out"):
            await q.edit_message_text("خطا.")
            context.user_data.clear()
            return ConversationHandler.END

        scope, owner = resolve_scope_owner(user.id)

        with db_conn() as conn:
            row = conn.execute(
                "SELECT name FROM categories WHERE id=? AND scope=? AND owner_user_id=? AND grp=?",
                (cid, scope, owner, ttype),
            ).fetchone()

        if not row:
            await q.edit_message_text("دسته پیدا نشد.")
            return TX_CAT_PICK

        context.user_data["tx_category"] = row["name"]
        await q.edit_message_text("💵 مبلغ را وارد کنید (عدد صحیح، بدون اعشار):")
        return TX_AMOUNT

    await q.edit_message_text("دستور ناشناخته.")
    context.user_data.clear()
    return ConversationHandler.END


async def tx_cat_new_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message("نام نمی‌تواند خالی باشد. دوباره وارد کنید:")
        return TX_CAT_NEW

    ttype = context.user_data.get("tx_ttype")
    if ttype not in ("work_in", "work_out", "personal_out"):
        await update.effective_chat.send_message("خطا.")
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
    await update.effective_chat.send_message("💵 مبلغ را وارد کنید (عدد صحیح، بدون اعشار):")
    return TX_AMOUNT


async def tx_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
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


async def finalize_tx(update: Update, context: ContextTypes.DEFAULT_TYPE, description: Optional[str]) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END

    ttype = context.user_data.get("tx_ttype")
    date_g = context.user_data.get("tx_date_g")
    category = context.user_data.get("tx_category")
    amount = context.user_data.get("tx_amount")

    if ttype not in ("work_in", "work_out", "personal_out") or not date_g or not category or amount is None:
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

    msg = (
        "✅ تراکنش ثبت شد.\n\n"
        f"📅 تاریخ (میلادی): {date_g}\n"
        f"📅 تاریخ (شمسی): {g_to_j_str(date_g)}\n"
        f"🔖 نوع: {ttype_label(ttype)}\n"
        f"🏷 دسته: {category}\n"
        f"💵 مبلغ: {amount}\n"
        f"📝 توضیح: {description or '-'}\n"
    )
    is_primary = (user.id == ADMIN_CHAT_ID)
    await update.effective_chat.send_message(msg, reply_markup=main_menu_ikb(is_primary))
    context.user_data.clear()
    return ConversationHandler.END


# ------------------------
# Reports
# ------------------------
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

    sums: Dict[str, int] = {r["ttype"]: int(r["s"] or 0) for r in rows}
    w_in = sums.get("work_in", 0)
    w_out = sums.get("work_out", 0)
    p_out = sums.get("personal_out", 0)
    net = w_in - (w_out + p_out)

    return (
        f"<b>{title}</b>\n"
        f"📅 بازه (میلادی): <b>{start_g}</b> تا <b>{end_g}</b>\n"
        f"📅 بازه (شمسی): {g_to_j_str(start_g)} تا {g_to_j_str(end_g)}\n\n"
        f"💰 درآمد کاری: <b>{w_in}</b>\n"
        f"🏢 هزینه کاری: <b>{w_out}</b>\n"
        f"👤 هزینه شخصی: <b>{p_out}</b>\n\n"
        f"📌 تراز: <b>{net}</b>"
    )


async def rp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END
    await q.answer()

    scope, owner = resolve_scope_owner(user.id)

    parts = (q.data or "").split(":")
    action = parts[1]

    if action == "sum":
        which = parts[2]
        if which == "today":
            start = end = today_g_str()
            title = "📅 خلاصه امروز"
        else:
            start, end = month_range_g_for_date(today_g_str())
            title = "🗓 خلاصه این ماه (میلادی)"

        text = build_summary_text(scope, owner, start, end, title)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=rp_menu_ikb())
        return ConversationHandler.END

    if action == "range":
        context.user_data.clear()
        await q.edit_message_text(
            "تاریخ شروع را وارد کنید:\n"
            "✅ میلادی: YYYY-MM-DD\n"
            "✅ شمسی: YYYY/MM/DD\n\n"
            "🔸 محاسبات ماه/بازه بر اساس میلادی است و شمسی تبدیل می‌شود."
        )
        return RP_RANGE_START

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


def parse_any_date_to_g(text: str) -> Optional[str]:
    return parse_gregorian(text) or parse_jalali_to_g(text)


async def rp_range_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END

    g = parse_any_date_to_g(update.message.text or "")
    if not g:
        await update.effective_chat.send_message("❌ تاریخ نامعتبر است. دوباره وارد کنید:")
        return RP_RANGE_START

    context.user_data["rp_start"] = g
    await update.effective_chat.send_message("تاریخ پایان را وارد کنید:")
    return RP_RANGE_END


async def rp_range_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END

    g2 = parse_any_date_to_g(update.message.text or "")
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
    text = build_summary_text(scope, owner, g1, g2, "📆 گزارش بازه دلخواه")
    is_primary = (user.id == ADMIN_CHAT_ID)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_ikb(is_primary))
    context.user_data.clear()
    return ConversationHandler.END


# ------------------------
# Settings / Admin / Categories (minimal but stable)
# ------------------------
async def settings_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    await q.answer()

    is_primary = (user.id == ADMIN_CHAT_ID)

    parts = (q.data or "").split(":")
    action = parts[1]

    if action == "cats":
        await q.edit_message_text("🧩 مدیریت نوع‌ها:", reply_markup=cats_menu_ikb())
        return

    if action == "admin":
        if not is_primary:
            await q.edit_message_text("⛔ این بخش فقط برای ادمین اصلی فعال است.")
            return
        await q.edit_message_text("🛡 بخش ادمین:", reply_markup=admin_menu_ikb())
        return

    if action == "back":
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=settings_menu_ikb(is_primary))
        return

    await q.edit_message_text("دستور ناشناخته.")


def build_admins_list() -> Tuple[str, InlineKeyboardMarkup]:
    with db_conn() as conn:
        rows = conn.execute("SELECT user_id, name, added_at FROM admins ORDER BY added_at DESC").fetchall()

    lines = ["📋 <b>لیست ادمین‌ها</b>\n"]
    btn_rows = []
    if not rows:
        lines.append("— (خالی)")
    else:
        for r in rows[:25]:
            lines.append(f"• {r['name']} — <code>{r['user_id']}</code> — {r['added_at']}")
            btn_rows.append([("🗑 حذف", f"{CB_AD}:del:{r['user_id']}")])

    btn_rows.append([("⬅️ بازگشت", f"{CB_AD}:back2")])
    return "\n".join(lines), ikb(btn_rows)


async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return ConversationHandler.END
    await q.answer()

    if user.id != ADMIN_CHAT_ID:
        await q.edit_message_text("⛔ این بخش فقط برای ادمین اصلی فعال است.")
        return ConversationHandler.END

    parts = (q.data or "").split(":")
    action = parts[1]

    if action == "admins":
        await q.edit_message_text("👥 مدیریت ادمین‌ها:", reply_markup=admins_manage_ikb())
        return ConversationHandler.END

    if action == "back2":
        await q.edit_message_text("🛡 بخش ادمین:", reply_markup=admin_menu_ikb())
        return ConversationHandler.END

    if action == "share":
        cur = get_setting("share_enabled")
        set_setting("share_enabled", "0" if cur == "1" else "1")
        await q.edit_message_text("✅ تنظیم شد.", reply_markup=admin_menu_ikb())
        return ConversationHandler.END

    if action == "list":
        text, markup = build_admins_list()
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return ConversationHandler.END

    if action == "del":
        try:
            uid = int(parts[2])
        except Exception:
            await q.edit_message_text("آیدی نامعتبر.")
            return ConversationHandler.END
        with db_conn() as conn:
            conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
            conn.commit()
        text, markup = build_admins_list()
        await q.edit_message_text("✅ حذف شد.\n\n" + text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return ConversationHandler.END

    if action == "add":
        context.user_data.clear()
        await q.edit_message_text("🆔 user_id عددی ادمین جدید را وارد کنید:")
        return ADM_ADD_UID

    await q.edit_message_text("دستور ناشناخته.")
    return ConversationHandler.END


async def adm_add_uid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
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
    await update.effective_chat.send_message("👤 نام ادمین را وارد کنید:")
    return ADM_ADD_NAME


async def adm_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
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
            ON CONFLICT(user_id) DO UPDATE SET name=excluded.name
            """,
            (uid, name, now_tehran_str()),
        )
        conn.commit()

    is_primary = True
    await update.effective_chat.send_message("✅ ادمین اضافه شد.", reply_markup=main_menu_ikb(is_primary))
    context.user_data.clear()
    return ConversationHandler.END


# ---- Categories (basic: list by grp, add/delete with lock for installment)
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
    btns = []
    if not rows:
        lines.append("— (خالی)")
    else:
        for r in rows[:30]:
            lock = "🔒 " if int(r["is_locked"]) == 1 else ""
            lines.append(f"• {lock}{r['name']}")
            if not (grp == "personal_out" and r["name"] == INSTALLMENT_NAME and int(r["is_locked"]) == 1):
                btns.append([("🗑 حذف", f"{CB_CT}:del:{r['id']}")])

    btns.append([("➕ افزودن", f"{CB_CT}:add:{grp}")])
    btns.append([("⬅️ بازگشت", f"{CB_ST}:cats")])
    return "\n".join(lines), ikb(btns)


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
    await update.effective_chat.send_message("✅ ثبت شد.\n\n" + text, parse_mode=ParseMode.HTML, reply_markup=markup)
    context.user_data.clear()
    return ConversationHandler.END


# ------------------------
# Unknown
# ------------------------
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny_update(update)
        return
    is_primary = (user.id == ADMIN_CHAT_ID)
    await update.effective_chat.send_message("از /start شروع کنید.", reply_markup=main_menu_ikb(is_primary))


# ------------------------
# Build App
# ------------------------
def build_app() -> Application:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", start))

    # main menu
    app.add_handler(CallbackQueryHandler(main_cb, pattern=r"^m:(home|tx|rp|st)$"))

    # settings
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^st:(cats|admin|back)$"))

    # transactions conversation
    tx_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(tx_cb, pattern=r"^tx:(add|list:(today|month))$")],
        states={
            TX_TTYPE: [CallbackQueryHandler(tx_cb, pattern=r"^tx:(tt:(work_in|work_out|personal_out)|cancel)$")],
            TX_DATE_MENU: [CallbackQueryHandler(tx_cb, pattern=r"^tx:(d:(today|g|j)|cancel)$")],
            TX_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_g_input)],
            TX_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_j_input)],
            TX_CAT_PICK: [CallbackQueryHandler(tx_cat_pick_cb, pattern=r"^tx:(cat:\d+|cat_new|cat_manual|cancel)$")],
            TX_CAT_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_cat_new_input)],
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
    app.add_handler(CallbackQueryHandler(tx_cb, pattern=r"^tx:.*$"))
    app.add_handler(tx_conv)

    # reports conversation
    rp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(rp_cb, pattern=r"^rp:(sum:(today|month)|range)$")],
        states={
            RP_RANGE_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, rp_range_start)],
            RP_RANGE_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, rp_range_end)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="rp_conv",
        persistent=False,
    )
    app.add_handler(CallbackQueryHandler(rp_cb, pattern=r"^rp:(sum:(today|month)|range)$"))
    app.add_handler(rp_conv)

    # admin conversation
    adm_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_cb, pattern=r"^ad:add$")],
        states={
            ADM_ADD_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_uid)],
            ADM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_name)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="adm_conv",
        persistent=False,
    )
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^ad:.*$"))
    app.add_handler(adm_conv)

    # categories conversation
    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:add:(work_in|work_out|personal_out)$")],
        states={CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_add_name)]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        name="cat_conv",
        persistent=False,
    )
    app.add_handler(CallbackQueryHandler(cats_cb, pattern=r"^ct:.*$"))
    app.add_handler(cat_conv)

    # unknown
    app.add_handler(MessageHandler(filters.ALL, unknown), group=99)

    return app


def main() -> None:
    app = build_app()
    logger.info("%s started. TZ=%s DB=%s", PROJECT_NAME, "Asia/Tehran", DB_PATH)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
