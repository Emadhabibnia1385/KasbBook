import os
import re
import sqlite3
import shutil
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple

import pytz
import jdatetime
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =========================
# ENV / Config
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0").strip() or "0")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip().lstrip("@")

if not BOT_TOKEN or ADMIN_CHAT_ID == 0 or not ADMIN_USERNAME:
    raise RuntimeError("ENV not set. Please set BOT_TOKEN, ADMIN_CHAT_ID, ADMIN_USERNAME in .env")

TZ = pytz.timezone("America/Los_Angeles")

PROJECT_NAME = "KasbBook"
DB_PATH = f"{PROJECT_NAME}.db"

# =========================
# Access Modes
# =========================
ACCESS_ADMIN_ONLY = "admin_only"
ACCESS_ALLOWED_USERS = "allowed_users"
ACCESS_PUBLIC = "public"

# Share toggle meaning:
# - only relevant in ACCESS_ALLOWED_USERS
# - share_enabled=1 => all allowed users see/save into SHARED SCOPE
# - share_enabled=0 => each allowed user is private scope

# =========================
# Transaction Types
# =========================
WORK_IN = "work_in"
WORK_OUT = "work_out"
PERSONAL_OUT = "personal_out"
INSTALLMENT_NAME = "قسط"

# =========================
# Conversation States
# =========================
(
    ST_GREG_DATE,
    ST_JAL_DATE,
    ST_ADD_CATEGORY,
    ST_ADD_AMOUNT,
    ST_ADD_DESC,
    ST_EDIT_VALUE,
    ST_ADD_ALLOWED_ID,
    ST_CAT_DEL_VALUE,
) = range(8)

# =========================
# DB Init (Single DB)
# =========================
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def now_utc() -> str:
    return datetime.utcnow().isoformat()

def db_init():
    c = conn()
    cur = c.cursor()

    # global settings + allowed list
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
      k TEXT PRIMARY KEY,
      v TEXT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS allowed_users (
      user_id INTEGER PRIMARY KEY,
      added_at TEXT NOT NULL
    );
    """)

    # data tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
      owner_user_id INTEGER NOT NULL,       -- private: user_id , shared: ADMIN_CHAT_ID (or fixed)
      actor_user_id INTEGER NOT NULL,       -- who created it (for audit)
      date_g TEXT NOT NULL,                 -- YYYY-MM-DD (Gregorian)
      ttype TEXT NOT NULL CHECK(ttype IN ('work_in','work_out','personal_out')),
      category TEXT NOT NULL,
      amount INTEGER NOT NULL CHECK(amount >= 0),
      description TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date ON transactions(scope, owner_user_id, date_g);")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
      owner_user_id INTEGER NOT NULL,       -- private: user_id , shared: ADMIN_CHAT_ID
      grp TEXT NOT NULL CHECK(grp IN ('work_in','work_out','personal_out')),
      name TEXT NOT NULL,
      is_locked INTEGER NOT NULL DEFAULT 0
    );
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_cat_scope_owner_grp_name ON categories(scope, owner_user_id, grp, name);")

    c.commit()

    # defaults
    def set_default(k, v):
        cur.execute("INSERT OR IGNORE INTO settings(k, v) VALUES(?,?)", (k, v))

    set_default("access_mode", ACCESS_ADMIN_ONLY)  # default: admin only
    set_default("share_enabled", "0")              # default: off
    c.commit()
    c.close()

def cfg_get(k: str) -> str:
    c = conn()
    row = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    c.close()
    return row["v"] if row else ""

def cfg_set(k: str, v: str):
    c = conn()
    c.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
    c.commit()
    c.close()

def allowed_add(user_id: int):
    c = conn()
    c.execute("INSERT OR IGNORE INTO allowed_users(user_id, added_at) VALUES(?,?)", (user_id, now_utc()))
    c.commit()
    c.close()

def allowed_remove(user_id: int):
    c = conn()
    c.execute("DELETE FROM allowed_users WHERE user_id=?", (user_id,))
    c.commit()
    c.close()

def allowed_list() -> List[int]:
    c = conn()
    rows = c.execute("SELECT user_id FROM allowed_users ORDER BY user_id ASC").fetchall()
    c.close()
    return [int(r["user_id"]) for r in rows]

def is_allowed(user_id: int) -> bool:
    if user_id == ADMIN_CHAT_ID:
        return True
    c = conn()
    row = c.execute("SELECT user_id FROM allowed_users WHERE user_id=?", (user_id,)).fetchone()
    c.close()
    return row is not None

# =========================
# Date helpers
# =========================
def today_g() -> str:
    return datetime.now(TZ).date().isoformat()

def pretty_date(g: str) -> str:
    try:
        gg = datetime.strptime(g, "%Y-%m-%d").date()
        j = jdatetime.date.fromgregorian(date=gg)
        return f"{g} | شمسی: {j.year:04d}-{j.month:02d}-{j.day:02d}"
    except Exception:
        return g

def gregorian_validate(g: str) -> bool:
    try:
        datetime.strptime(g, "%Y-%m-%d")
        return True
    except Exception:
        return False

def jalali_to_gregorian(jal_str: str) -> Optional[str]:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", jal_str.strip())
    if not m:
        return None
    jy, jm, jd = map(int, m.groups())
    try:
        g = jdatetime.date(jy, jm, jd).togregorian()
        return g.isoformat()
    except Exception:
        return None

def safe_username(u) -> str:
    return f"@{u}" if u else "ندارد"

# =========================
# Scope logic (THIS is the key)
# =========================
def current_scope(user_id: int) -> Tuple[str, int]:
    """
    Returns (scope, owner_user_id) for this user based on access_mode/share_enabled.
    - public: always private per-user
    - admin_only: admin uses private (or can be shared, but simplest: private)
    - allowed_users:
        - share_enabled=1 => shared scope owned by ADMIN_CHAT_ID
        - share_enabled=0 => private scope per-user
    """
    mode = cfg_get("access_mode")
    share_enabled = (cfg_get("share_enabled") == "1")

    if mode == ACCESS_PUBLIC:
        return ("private", user_id)

    if mode == ACCESS_ALLOWED_USERS and share_enabled:
        return ("shared", ADMIN_CHAT_ID)

    # default: private per user
    return ("private", user_id)

def ensure_installment(scope: str, owner_user_id: int):
    c = conn()
    c.execute(
        "INSERT OR IGNORE INTO categories(scope, owner_user_id, grp, name, is_locked) VALUES(?,?,?,?,1)",
        (scope, owner_user_id, PERSONAL_OUT, INSTALLMENT_NAME),
    )
    c.commit()
    c.close()

# =========================
# Data ops (single DB)
# =========================
def add_tx(actor_user_id: int, date_g: str, ttype: str, category: str, amount: int, desc: Optional[str]):
    scope, owner = current_scope(actor_user_id)
    ensure_installment(scope, owner)

    c = conn()
    n = now_utc()
    c.execute(
        """INSERT INTO transactions(scope, owner_user_id, actor_user_id, date_g, ttype, category, amount, description, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (scope, owner, actor_user_id, date_g, ttype, category, amount, desc, n, n),
    )
    c.commit()
    c.close()

def get_day_txs(user_id: int, date_g: str) -> List[sqlite3.Row]:
    scope, owner = current_scope(user_id)
    ensure_installment(scope, owner)

    c = conn()
    rows = c.execute(
        """SELECT * FROM transactions
           WHERE scope=? AND owner_user_id=? AND date_g=?
           ORDER BY id DESC""",
        (scope, owner, date_g),
    ).fetchall()
    c.close()
    return rows

def get_tx(user_id: int, tx_id: int) -> Optional[sqlite3.Row]:
    scope, owner = current_scope(user_id)
    c = conn()
    row = c.execute(
        "SELECT * FROM transactions WHERE scope=? AND owner_user_id=? AND id=?",
        (scope, owner, tx_id),
    ).fetchone()
    c.close()
    return row

def update_tx_field(user_id: int, tx_id: int, field: str, value):
    assert field in ("category", "amount", "description")
    scope, owner = current_scope(user_id)
    c = conn()
    c.execute(
        f"UPDATE transactions SET {field}=?, updated_at=? WHERE scope=? AND owner_user_id=? AND id=?",
        (value, now_utc(), scope, owner, tx_id),
    )
    c.commit()
    c.close()

def delete_tx(user_id: int, tx_id: int):
    scope, owner = current_scope(user_id)
    c = conn()
    c.execute("DELETE FROM transactions WHERE scope=? AND owner_user_id=? AND id=?", (scope, owner, tx_id))
    c.commit()
    c.close()

def list_categories(user_id: int, grp: str) -> List[str]:
    scope, owner = current_scope(user_id)
    ensure_installment(scope, owner)

    c = conn()
    rows = c.execute(
        """SELECT name FROM categories
           WHERE scope=? AND owner_user_id=? AND grp=?
           ORDER BY is_locked DESC, name ASC""",
        (scope, owner, grp),
    ).fetchall()
    c.close()
    return [r["name"] for r in rows]

def add_category(user_id: int, grp: str, name: str):
    scope, owner = current_scope(user_id)
    ensure_installment(scope, owner)

    c = conn()
    c.execute(
        "INSERT OR IGNORE INTO categories(scope, owner_user_id, grp, name, is_locked) VALUES(?,?,?,?,0)",
        (scope, owner, grp, name),
    )
    c.commit()
    c.close()

def del_category(user_id: int, grp: str, name: str) -> Tuple[bool, str]:
    scope, owner = current_scope(user_id)
    ensure_installment(scope, owner)

    c = conn()
    row = c.execute(
        "SELECT is_locked FROM categories WHERE scope=? AND owner_user_id=? AND grp=? AND name=?",
        (scope, owner, grp, name),
    ).fetchone()
    if row is None:
        c.close()
        return False, "این نوع پیدا نشد."
    if int(row["is_locked"]) == 1:
        c.close()
        return False, "این نوع قفل است و حذف نمی‌شود (قسط)."
    c.execute(
        "DELETE FROM categories WHERE scope=? AND owner_user_id=? AND grp=? AND name=?",
        (scope, owner, grp, name),
    )
    c.commit()
    c.close()
    return True, "حذف شد."

# =========================
# Calculations
# =========================
def daily_sums(user_id: int, date_g: str) -> Dict[str, int]:
    rows = get_day_txs(user_id, date_g)
    work_in = sum(r["amount"] for r in rows if r["ttype"] == WORK_IN)
    work_out = sum(r["amount"] for r in rows if r["ttype"] == WORK_OUT)

    personal_wo_inst = sum(
        r["amount"] for r in rows if r["ttype"] == PERSONAL_OUT and r["category"] != INSTALLMENT_NAME
    )
    installment = sum(
        r["amount"] for r in rows if r["ttype"] == PERSONAL_OUT and r["category"] == INSTALLMENT_NAME
    )

    income = work_in
    out_total = work_out
    net = income - out_total
    saving = net - personal_wo_inst

    return {
        "income": income,
        "out": out_total,
        "net": net,
        "personal_wo_inst": personal_wo_inst,
        "installment": installment,
        "saving": saving,
    }

def month_range(year: int, month: int) -> Tuple[str, str]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()

def month_sums(user_id: int, year: int, month: int) -> Dict[str, int]:
    scope, owner = current_scope(user_id)
    start, end = month_range(year, month)

    c = conn()
    rows = c.execute(
        """SELECT * FROM transactions
           WHERE scope=? AND owner_user_id=? AND date_g BETWEEN ? AND ?""",
        (scope, owner, start, end),
    ).fetchall()
    c.close()

    work_in = sum(r["amount"] for r in rows if r["ttype"] == WORK_IN)
    work_out = sum(r["amount"] for r in rows if r["ttype"] == WORK_OUT)
    personal_wo_inst = sum(
        r["amount"] for r in rows if r["ttype"] == PERSONAL_OUT and r["category"] != INSTALLMENT_NAME
    )
    installment = sum(
        r["amount"] for r in rows if r["ttype"] == PERSONAL_OUT and r["category"] == INSTALLMENT_NAME
    )

    income = work_in
    out_total = work_out
    net = income - out_total
    saving = net - personal_wo_inst

    return {
        "income": income,
        "out": out_total,
        "net": net,
        "personal_wo_inst": personal_wo_inst,
        "installment": installment,
        "saving": saving,
        "start": start,
        "end": end,
    }

def month_breakdown_by_category(user_id: int, year: int, month: int, grp: str) -> List[Tuple[str, int]]:
    scope, owner = current_scope(user_id)
    start, end = month_range(year, month)
    c = conn()
    rows = c.execute(
        """SELECT category, SUM(amount) AS s
           FROM transactions
           WHERE scope=? AND owner_user_id=? AND ttype=? AND date_g BETWEEN ? AND ?
           GROUP BY category
           ORDER BY s DESC""",
        (scope, owner, grp, start, end),
    ).fetchall()
    c.close()
    return [(r["category"], int(r["s"] or 0)) for r in rows]

# =========================
# Access Control
# =========================
def access_denied_text(user) -> str:
    return (
        "❌ شما هنوز به عنوان ادمین ثبت نشده‌اید.\n\n"
        f"🆔 آیدی عددی شما: {user.id}\n"
        f"👤 یوزرنیم شما: {safe_username(user.username)}\n\n"
        "این پیام را برای ادمین اصلی ارسال کنید تا شما را اضافه کند.\n"
        f"ادمین اصلی: @{ADMIN_USERNAME}"
    )

def has_access(user_id: int) -> bool:
    mode = cfg_get("access_mode")
    if user_id == ADMIN_CHAT_ID:
        return True
    if mode == ACCESS_PUBLIC:
        return True
    if mode == ACCESS_ALLOWED_USERS:
        return is_allowed(user_id)
    return False  # admin_only

async def guard(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if has_access(user.id):
        return True
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(access_denied_text(user))
    else:
        await update.message.reply_text(access_denied_text(user))
    return False

# =========================
# Keyboards
# =========================
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 تراکنش‌ها", callback_data="m:tx")],
        [InlineKeyboardButton("📊 گزارش‌ها", callback_data="m:rep")],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="m:set")],
    ])

def kb_tx_date() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 امروز", callback_data="tx:date:today")],
        [InlineKeyboardButton("📆 تاریخ میلادی", callback_data="tx:date:greg")],
        [InlineKeyboardButton("🗓 تاریخ شمسی", callback_data="tx:date:jal")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="m:home")],
    ])

def kb_skip_desc() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭ اسکیپ توضیحات", callback_data="add:skip_desc")]])

def kb_day_menu(date_g: str, day_rows: List[sqlite3.Row]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("➕ افزودن ورودی کار", callback_data=f"add:{WORK_IN}:{date_g}"),
            InlineKeyboardButton("➖ افزودن خروجی کار", callback_data=f"add:{WORK_OUT}:{date_g}"),
        ],
        [InlineKeyboardButton("👤 افزودن خروجی شخصی", callback_data=f"add:{PERSONAL_OUT}:{date_g}")],
    ]
    for r in day_rows[:40]:
        title = f"{r['category']} | {r['amount']}"
        buttons.append([InlineKeyboardButton(title, callback_data=f"item:open:{r['id']}:{date_g}")])
    buttons.append([InlineKeyboardButton("↩️ انتخاب تاریخ", callback_data="m:tx")])
    buttons.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="m:home")])
    return InlineKeyboardMarkup(buttons)

def kb_item_actions(tx_id: int, date_g: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ ویرایش نوع", callback_data=f"item:edit:category:{tx_id}:{date_g}"),
            InlineKeyboardButton("✏️ ویرایش هزینه", callback_data=f"item:edit:amount:{tx_id}:{date_g}"),
        ],
        [InlineKeyboardButton("✏️ ویرایش توضیحات", callback_data=f"item:edit:description:{tx_id}:{date_g}")],
        [InlineKeyboardButton("🗑 حذف", callback_data=f"item:delete:{tx_id}:{date_g}")],
        [InlineKeyboardButton("↩️ بازگشت", callback_data=f"day:open:{date_g}")],
    ])

def kb_reports_year(year: int) -> InlineKeyboardMarkup:
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    rows = []
    for i in range(0, 12, 3):
        row = []
        for m in range(i+1, i+4):
            row.append(InlineKeyboardButton(f"{months[m-1]} {year}", callback_data=f"rep:month:{year}:{m}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="m:home")])
    return InlineKeyboardMarkup(rows)

def kb_report_detail(year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("گزارش ورودی‌ها", callback_data=f"rep:detail:{WORK_IN}:{year}:{month}"),
            InlineKeyboardButton("گزارش خروجی‌ها", callback_data=f"rep:detail:{WORK_OUT}:{year}:{month}"),
        ],
        [InlineKeyboardButton("گزارش خروجی شخصی", callback_data=f"rep:detail:{PERSONAL_OUT}:{year}:{month}")],
        [InlineKeyboardButton("↩️ ماه‌ها", callback_data="m:rep")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="m:home")],
    ])

def kb_settings(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🧩 تعیین نوع‌ها", callback_data="set:cats")],
        [InlineKeyboardButton("🛡 تعیین دسترسی افراد به ربات", callback_data="set:access")],
    ]
    if user_id == ADMIN_CHAT_ID:
        buttons.append([InlineKeyboardButton("🗄 دیتابیس", callback_data="set:db")])
    buttons.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="m:home")])
    return InlineKeyboardMarkup(buttons)

def kb_access_menu() -> InlineKeyboardMarkup:
    mode = cfg_get("access_mode")
    mode_txt = {
        ACCESS_ADMIN_ONLY: "فقط ادمین",
        ACCESS_ALLOWED_USERS: "اعضای مجاز",
        ACCESS_PUBLIC: "همگانی",
    }.get(mode, mode)

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"حالت فعلی: {mode_txt}", callback_data="noop")],
        [InlineKeyboardButton("فقط ادمین", callback_data=f"acc:set:{ACCESS_ADMIN_ONLY}")],
        [InlineKeyboardButton("اعضای مجاز", callback_data=f"acc:set:{ACCESS_ALLOWED_USERS}")],
        [InlineKeyboardButton("همگانی", callback_data=f"acc:set:{ACCESS_PUBLIC}")],
        [InlineKeyboardButton("↩️ تنظیمات", callback_data="m:set")],
    ])

def kb_allowed_users_menu() -> InlineKeyboardMarkup:
    share_enabled = (cfg_get("share_enabled") == "1")
    share_txt = "روشن ✅" if share_enabled else "خاموش ❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 مدیریت افراد", callback_data="acc:users")],
        [InlineKeyboardButton(f"🔁 اشتراک اطلاعات بین افراد: {share_txt}", callback_data="acc:share:toggle")],
        [InlineKeyboardButton("↩️ دسترسی‌ها", callback_data="set:access")],
    ])

def kb_allowed_manage() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن فرد", callback_data="acc:users:add")],
        [InlineKeyboardButton("➖ حذف فرد", callback_data="acc:users:del")],
        [InlineKeyboardButton("📋 لیست افراد", callback_data="acc:users:list")],
        [InlineKeyboardButton("↩️ اعضای مجاز", callback_data="acc:allowed:menu")],
    ])

def kb_cats_groups() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ورودی کار", callback_data=f"cat:grp:{WORK_IN}")],
        [InlineKeyboardButton("خروجی کار", callback_data=f"cat:grp:{WORK_OUT}")],
        [InlineKeyboardButton("خروجی شخصی", callback_data=f"cat:grp:{PERSONAL_OUT}")],
        [InlineKeyboardButton("↩️ تنظیمات", callback_data="m:set")],
    ])

def kb_cat_actions(grp: str) -> InlineKeyboardMarkup:
    title = {"work_in":"ورودی کار","work_out":"خروجی کار","personal_out":"خروجی شخصی"}[grp]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"➕ افزودن نوع ({title})", callback_data=f"cat:add:{grp}")],
        [InlineKeyboardButton(f"🗑 حذف نوع ({title})", callback_data=f"cat:del:{grp}")],
        [InlineKeyboardButton(f"📋 لیست نوع‌ها ({title})", callback_data=f"cat:list:{grp}")],
        [InlineKeyboardButton("↩️ گروه‌ها", callback_data="set:cats")],
    ])

def kb_db_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 بکاپ/اکسپورت DB", callback_data="db:export")],
        [InlineKeyboardButton("↩️ تنظیمات", callback_data="m:set")],
    ])

# =========================
# Screens
# =========================
def day_text(user_id: int, date_g: str) -> str:
    ds = daily_sums(user_id, date_g)
    dt = datetime.strptime(date_g, "%Y-%m-%d").date()
    y, m = dt.year, dt.month
    ms = month_sums(user_id, y, m)

    scope, owner = current_scope(user_id)
    scope_txt = "مشترک ✅" if scope == "shared" else "خصوصی 🔒"

    return (
        f"📅 تاریخ: {pretty_date(date_g)}\n"
        f"🗂 حالت اطلاعات: {scope_txt}\n\n"
        "📌 جمع‌های روزانه\n"
        f"ورودی کل روز: {ds['income']}\n"
        f"خروجی کل روز: {ds['out']}\n"
        f"درآمد (ورودی-خروجی): {ds['net']}\n"
        f"خروجی شخصی (بدون قسط): {ds['personal_wo_inst']}\n"
        f"پس‌انداز: {ds['saving']}\n"
        f"قسط امروز: {ds['installment']}\n\n"
        f"📌 جمع‌های ماه (میلادی) {m:02d}/{y}\n"
        f"ورودی ماه: {ms['income']}\n"
        f"خروجی ماه: {ms['out']}\n"
        f"درآمد ماه: {ms['net']}\n"
        f"خروجی شخصی ماه (بدون قسط): {ms['personal_wo_inst']}\n"
        f"پس‌انداز ماه: {ms['saving']}\n"
        f"جمع قسط ماه: {ms['installment']}\n"
    )

# =========================
# Handlers
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_init()
    if not await guard(update):
        return
    await update.message.reply_text(f"سلام! ✅ {PROJECT_NAME}\nاز منو انتخاب کن:", reply_markup=kb_main())

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()

    if q.data == "m:home":
        await q.edit_message_text("منوی اصلی:", reply_markup=kb_main())
        return

    if q.data == "m:tx":
        await q.edit_message_text("📌 تراکنش‌ها — انتخاب تاریخ:", reply_markup=kb_tx_date())
        return

    if q.data == "m:rep":
        year = datetime.now(TZ).year
        await q.edit_message_text("📊 گزارش‌ها — انتخاب ماه:", reply_markup=kb_reports_year(year))
        return

    if q.data == "m:set":
        await q.edit_message_text("⚙️ تنظیمات:", reply_markup=kb_settings(q.from_user.id))
        return

async def on_tx_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()

    if q.data == "tx:date:today":
        d = today_g()
        return await open_day(q, d)

    if q.data == "tx:date:greg":
        await q.edit_message_text("تاریخ میلادی را وارد کن (YYYY-MM-DD):", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ بازگشت", callback_data="m:tx")]
        ]))
        return ST_GREG_DATE

    if q.data == "tx:date:jal":
        await q.edit_message_text("تاریخ شمسی را وارد کن (YYYY-MM-DD):\nمثال: 1404-10-11", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ بازگشت", callback_data="m:tx")]
        ]))
        return ST_JAL_DATE

    return ConversationHandler.END

async def open_day(q, date_g: str):
    user_id = q.from_user.id
    rows = get_day_txs(user_id, date_g)
    await q.edit_message_text(day_text(user_id, date_g), reply_markup=kb_day_menu(date_g, rows))

async def send_day(update: Update, date_g: str):
    user_id = update.effective_user.id
    rows = get_day_txs(user_id, date_g)
    await update.message.reply_text(day_text(user_id, date_g), reply_markup=kb_day_menu(date_g, rows))

async def on_greg_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    txt = (update.message.text or "").strip()
    if not gregorian_validate(txt):
        await update.message.reply_text("فرمت اشتباهه. مثال: 2026-01-01")
        return ST_GREG_DATE
    await send_day(update, txt)
    return ConversationHandler.END

async def on_jal_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    txt = (update.message.text or "").strip()
    g = jalali_to_gregorian(txt)
    if not g:
        await update.message.reply_text("فرمت یا تاریخ شمسی اشتباهه. مثال: 1404-10-11")
        return ST_JAL_DATE
    await send_day(update, g)
    return ConversationHandler.END

async def on_day_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, date_g = q.data.split(":", 2)
    await open_day(q, date_g)

# ---- Add flow
async def on_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    _, ttype, date_g = q.data.split(":", 2)
    context.user_data["add_ttype"] = ttype
    context.user_data["add_date_g"] = date_g
    label = {"work_in":"ورودی کار","work_out":"خروجی کار","personal_out":"خروجی شخصی"}[ttype]
    await q.edit_message_text(
        f"✅ افزودن {label}\n\nنوع را وارد کن (مثلاً VPN):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data=f"day:open:{date_g}")]])
    )
    return ST_ADD_CATEGORY

async def on_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    cat = (update.message.text or "").strip()
    if not cat:
        await update.message.reply_text("نوع نمی‌تواند خالی باشد.")
        return ST_ADD_CATEGORY
    context.user_data["add_category"] = cat
    await update.message.reply_text("مبلغ را وارد کن (فقط عدد):")
    return ST_ADD_AMOUNT

async def on_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    txt = (update.message.text or "").strip().replace(",", "")
    if not txt.isdigit():
        await update.message.reply_text("عدد معتبر نیست. مثال: 50000")
        return ST_ADD_AMOUNT
    context.user_data["add_amount"] = int(txt)
    await update.message.reply_text("توضیحات را وارد کن یا اسکیپ بزن:", reply_markup=kb_skip_desc())
    return ST_ADD_DESC

async def on_skip_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    context.user_data["add_desc"] = ""
    return await finalize_add(q, context)

async def on_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    context.user_data["add_desc"] = (update.message.text or "").strip()
    user_id = update.effective_user.id
    date_g = context.user_data["add_date_g"]
    ttype = context.user_data["add_ttype"]
    cat = context.user_data["add_category"]
    amt = context.user_data["add_amount"]
    desc = context.user_data.get("add_desc", "")
    add_tx(user_id, date_g, ttype, cat, amt, desc)
    await update.message.reply_text("✅ ثبت شد.")
    await send_day(update, date_g)
    return ConversationHandler.END

async def finalize_add(q, context: ContextTypes.DEFAULT_TYPE):
    user_id = q.from_user.id
    date_g = context.user_data["add_date_g"]
    ttype = context.user_data["add_ttype"]
    cat = context.user_data["add_category"]
    amt = context.user_data["add_amount"]
    desc = context.user_data.get("add_desc", "")
    add_tx(user_id, date_g, ttype, cat, amt, desc)
    rows = get_day_txs(user_id, date_g)
    await q.edit_message_text("✅ ثبت شد.\n\n" + day_text(user_id, date_g), reply_markup=kb_day_menu(date_g, rows))
    return ConversationHandler.END

# ---- Item
async def on_item_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, tx_id, date_g = q.data.split(":", 3)
    row = get_tx(q.from_user.id, int(tx_id))
    if not row:
        await q.edit_message_text("تراکنش پیدا نشد.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ بازگشت", callback_data=f"day:open:{date_g}")]
        ]))
        return
    tlabel = {"work_in":"ورودی کار","work_out":"خروجی کار","personal_out":"خروجی شخصی"}[row["ttype"]]
    desc = row["description"] or "—"
    await q.edit_message_text(
        f"ℹ️ اطلاعات تراکنش\n\n"
        f"نوع: {tlabel}\n"
        f"دسته: {row['category']}\n"
        f"مبلغ: {row['amount']}\n"
        f"توضیحات: {desc}\n"
        f"تاریخ: {pretty_date(row['date_g'])}\n",
        reply_markup=kb_item_actions(int(tx_id), date_g),
    )

async def on_item_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, tx_id, date_g = q.data.split(":", 3)
    delete_tx(q.from_user.id, int(tx_id))
    rows = get_day_txs(q.from_user.id, date_g)
    await q.edit_message_text("🗑 حذف شد.\n\n" + day_text(q.from_user.id, date_g), reply_markup=kb_day_menu(date_g, rows))

async def on_item_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    _, _, field, tx_id, date_g = q.data.split(":", 4)
    context.user_data["edit_field"] = field
    context.user_data["edit_tx_id"] = int(tx_id)
    context.user_data["edit_date_g"] = date_g
    label = {"category":"نوع/دسته", "amount":"هزینه/مبلغ", "description":"توضیحات"}[field]
    await q.edit_message_text(
        f"✏️ ویرایش {label}\n\nمقدار جدید را وارد کن:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data=f"item:open:{tx_id}:{date_g}")]])
    )
    return ST_EDIT_VALUE

async def on_item_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    user_id = update.effective_user.id
    field = context.user_data["edit_field"]
    tx_id = context.user_data["edit_tx_id"]
    date_g = context.user_data["edit_date_g"]
    txt = (update.message.text or "").strip()
    if field == "amount":
        t = txt.replace(",", "")
        if not t.isdigit():
            await update.message.reply_text("عدد معتبر نیست. مثال: 50000")
            return ST_EDIT_VALUE
        value = int(t)
    else:
        value = txt
    update_tx_field(user_id, tx_id, field, value)
    await update.message.reply_text("✅ ویرایش شد.")
    await send_day(update, date_g)
    return ConversationHandler.END

# ---- Reports
async def on_reports_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, y, m = q.data.split(":")
    y = int(y); m = int(m)
    ms = month_sums(q.from_user.id, y, m)
    text = (
        f"📊 گزارش ماه {m:02d}/{y}\n({ms['start']} تا {ms['end']})\n\n"
        f"جمع ورودی‌ها: {ms['income']}\n"
        f"جمع خروجی‌ها: {ms['out']}\n"
        f"درآمد ماه: {ms['net']}\n"
        f"جمع خروجی شخصی (بدون قسط): {ms['personal_wo_inst']}\n"
        f"پس‌انداز (بدون قسط): {ms['saving']}\n"
        f"جمع قسط این ماه: {ms['installment']}\n"
    )
    await q.edit_message_text(text, reply_markup=kb_report_detail(y, m))

async def on_report_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, grp, y, m = q.data.split(":")
    y = int(y); m = int(m)
    items = month_breakdown_by_category(q.from_user.id, y, m, grp)
    title = {
        WORK_IN: "گزارش ورودی‌ها (به تفکیک نوع)",
        WORK_OUT: "گزارش خروجی‌ها (به تفکیک نوع)",
        PERSONAL_OUT: "گزارش خروجی شخصی (به تفکیک نوع)",
    }[grp]
    lines = [f"📌 {title} — {m:02d}/{y}\n"]
    if not items:
        lines.append("داده‌ای ثبت نشده.")
    else:
        for cat, s in items:
            lines.append(f"- {cat}: {s}")
        if grp == PERSONAL_OUT:
            lines.append("\nℹ️ قسط جدا حساب می‌شود (در جمع شخصی/پس‌انداز لحاظ نمی‌شود).")
    await q.edit_message_text("\n".join(lines), reply_markup=kb_report_detail(y, m))

# ---- Settings / Access
async def on_set_cats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🧩 تعیین نوع‌ها — انتخاب گروه:", reply_markup=kb_cats_groups())

async def on_cat_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, grp = q.data.split(":", 2)
    context.user_data["cat_grp"] = grp
    await q.edit_message_text("انتخاب عملیات:", reply_markup=kb_cat_actions(grp))

async def on_cat_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, grp = q.data.split(":", 2)
    cats = list_categories(q.from_user.id, grp)
    title = {"work_in":"ورودی کار","work_out":"خروجی کار","personal_out":"خروجی شخصی"}[grp]
    msg = f"📋 لیست نوع‌ها ({title}):\n" + ("\n".join(f"- {c}" for c in cats) if cats else "خالی")
    await q.edit_message_text(msg, reply_markup=kb_cat_actions(grp))

async def on_cat_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    _, _, grp = q.data.split(":", 2)
    context.user_data["cat_grp"] = grp
    await q.edit_message_text("نام نوع جدید را وارد کن:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ بازگشت", callback_data=f"cat:grp:{grp}")]
    ]))
    return ST_EDIT_VALUE

async def on_cat_add_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    grp = context.user_data["cat_grp"]
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("نام نمی‌تواند خالی باشد.")
        return ST_EDIT_VALUE
    add_category(update.effective_user.id, grp, name)
    await update.message.reply_text("✅ اضافه شد.", reply_markup=kb_cat_actions(grp))
    return ConversationHandler.END

async def on_cat_del_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    _, _, grp = q.data.split(":", 2)
    context.user_data["cat_grp"] = grp
    await q.edit_message_text("نام نوعی که می‌خوای حذف کنی را وارد کن:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ بازگشت", callback_data=f"cat:grp:{grp}")]
    ]))
    return ST_CAT_DEL_VALUE

async def on_cat_del_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    grp = context.user_data["cat_grp"]
    name = (update.message.text or "").strip()
    ok, msg = del_category(update.effective_user.id, grp, name)
    await update.message.reply_text(("✅ " if ok else "⚠️ ") + msg, reply_markup=kb_cat_actions(grp))
    return ConversationHandler.END

async def on_access_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        await q.edit_message_text("این بخش فقط برای ادمین اصلی است.", reply_markup=kb_settings(q.from_user.id))
        return
    await q.edit_message_text("🛡 تعیین دسترسی افراد:", reply_markup=kb_access_menu())

async def on_access_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    _, _, mode = q.data.split(":", 2)
    cfg_set("access_mode", mode)
    if mode == ACCESS_ALLOWED_USERS:
        await q.edit_message_text("✅ حالت روی «اعضای مجاز» تنظیم شد.", reply_markup=kb_allowed_users_menu())
    else:
        await q.edit_message_text("✅ تغییر کرد.", reply_markup=kb_access_menu())

async def on_allowed_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    await q.edit_message_text("اعضای مجاز:", reply_markup=kb_allowed_users_menu())

async def on_allowed_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    await q.edit_message_text("👥 مدیریت افراد:", reply_markup=kb_allowed_manage())

async def on_allowed_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    ids = allowed_list()
    txt = "📋 لیست افراد مجاز:\n" + ("\n".join(f"- {i}" for i in ids) if ids else "خالی")
    await q.edit_message_text(txt, reply_markup=kb_allowed_manage())

async def on_allowed_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END
    context.user_data["allow_action"] = "add"
    await q.edit_message_text("🆔 آیدی عددی فرد را بفرست (فقط عدد):", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ بازگشت", callback_data="acc:users")]
    ]))
    return ST_ADD_ALLOWED_ID

async def on_allowed_del_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END
    context.user_data["allow_action"] = "del"
    await q.edit_message_text("🆔 آیدی عددی فرد را برای حذف بفرست (فقط عدد):", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ بازگشت", callback_data="acc:users")]
    ]))
    return ST_ADD_ALLOWED_ID

async def on_allowed_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    if update.effective_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END
    txt = (update.message.text or "").strip()
    if not txt.isdigit():
        await update.message.reply_text("فقط عدد بفرست.")
        return ST_ADD_ALLOWED_ID
    uid = int(txt)
    action = context.user_data.get("allow_action")
    if action == "add":
        allowed_add(uid)
        await update.message.reply_text("✅ اضافه شد.", reply_markup=kb_allowed_manage())
    else:
        allowed_remove(uid)
        await update.message.reply_text("✅ حذف شد.", reply_markup=kb_allowed_manage())
    return ConversationHandler.END

async def on_share_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    enabled = (cfg_get("share_enabled") == "1")
    cfg_set("share_enabled", "0" if enabled else "1")
    share_enabled = (cfg_get("share_enabled") == "1")
    msg = (
        "🔁 اشتراک اطلاعات بین افراد\n\n"
        f"وضعیت: {'روشن ✅' if share_enabled else 'خاموش ❌'}\n\n"
        "روشن: همه روی دیتای مشترک کار می‌کنند.\n"
        "خاموش: هر نفر دیتای خصوصی خودش را می‌بیند."
    )
    await q.edit_message_text(msg, reply_markup=kb_allowed_users_menu())

# ---- DB export (admin only)
async def on_db_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        await q.edit_message_text("این بخش فقط برای ادمین اصلی است.", reply_markup=kb_settings(q.from_user.id))
        return
    await q.edit_message_text("🗄 دیتابیس (فقط ادمین):", reply_markup=kb_db_admin())

async def on_db_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    backup_name = f"{PROJECT_NAME}_backup_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copyfile(DB_PATH, backup_name)
    await q.message.reply_document(document=InputFile(backup_name), caption=f"✅ بکاپ: {backup_name}")
    try:
        os.remove(backup_name)
    except Exception:
        pass
    await q.edit_message_text("اکسپورت انجام شد ✅", reply_markup=kb_db_admin())

async def on_noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()

# =========================
# App setup
# =========================
def build_app() -> Application:
    db_init()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))

    app.add_handler(CallbackQueryHandler(on_menu, pattern=r"^m:(home|tx|rep|set)$"))
    app.add_handler(CallbackQueryHandler(on_tx_date, pattern=r"^tx:date:(today|greg|jal)$"))
    app.add_handler(CallbackQueryHandler(on_day_open, pattern=r"^day:open:\d{4}-\d{2}-\d{2}$"))

    app.add_handler(CallbackQueryHandler(on_add_start, pattern=r"^add:(work_in|work_out|personal_out):\d{4}-\d{2}-\d{2}$"))
    app.add_handler(CallbackQueryHandler(on_skip_desc, pattern=r"^add:skip_desc$"))

    app.add_handler(CallbackQueryHandler(on_item_open, pattern=r"^item:open:\d+:\d{4}-\d{2}-\d{2}$"))
    app.add_handler(CallbackQueryHandler(on_item_delete, pattern=r"^item:delete:\d+:\d{4}-\d{2}-\d{2}$"))
    app.add_handler(CallbackQueryHandler(on_item_edit_start, pattern=r"^item:edit:(category|amount|description):\d+:\d{4}-\d{2}-\d{2}$"))

    app.add_handler(CallbackQueryHandler(on_reports_month, pattern=r"^rep:month:\d{4}:\d{1,2}$"))
    app.add_handler(CallbackQueryHandler(on_report_detail, pattern=r"^rep:detail:(work_in|work_out|personal_out):\d{4}:\d{1,2}$"))

    app.add_handler(CallbackQueryHandler(on_set_cats, pattern=r"^set:cats$"))
    app.add_handler(CallbackQueryHandler(on_cat_group, pattern=r"^cat:grp:(work_in|work_out|personal_out)$"))
    app.add_handler(CallbackQueryHandler(on_cat_list, pattern=r"^cat:list:(work_in|work_out|personal_out)$"))
    app.add_handler(CallbackQueryHandler(on_cat_add_start, pattern=r"^cat:add:(work_in|work_out|personal_out)$"))
    app.add_handler(CallbackQueryHandler(on_cat_del_start, pattern=r"^cat:del:(work_in|work_out|personal_out)$"))

    app.add_handler(CallbackQueryHandler(on_access_menu, pattern=r"^set:access$"))
    app.add_handler(CallbackQueryHandler(on_access_set, pattern=r"^acc:set:(admin_only|allowed_users|public)$"))
    app.add_handler(CallbackQueryHandler(on_allowed_menu, pattern=r"^acc:allowed:menu$"))
    app.add_handler(CallbackQueryHandler(on_allowed_users, pattern=r"^acc:users$"))
    app.add_handler(CallbackQueryHandler(on_allowed_list, pattern=r"^acc:users:list$"))
    app.add_handler(CallbackQueryHandler(on_allowed_add_start, pattern=r"^acc:users:add$"))
    app.add_handler(CallbackQueryHandler(on_allowed_del_start, pattern=r"^acc:users:del$"))
    app.add_handler(CallbackQueryHandler(on_share_toggle, pattern=r"^acc:share:toggle$"))

    app.add_handler(CallbackQueryHandler(on_db_menu, pattern=r"^set:db$"))
    app.add_handler(CallbackQueryHandler(on_db_export, pattern=r"^db:export$"))

    app.add_handler(CallbackQueryHandler(on_noop, pattern=r"^noop$"))

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(on_tx_date, pattern=r"^tx:date:(greg|jal)$"),
            CallbackQueryHandler(on_add_start, pattern=r"^add:(work_in|work_out|personal_out):\d{4}-\d{2}-\d{2}$"),
            CallbackQueryHandler(on_item_edit_start, pattern=r"^item:edit:(category|amount|description):\d+:\d{4}-\d{2}-\d{2}$"),
            CallbackQueryHandler(on_cat_add_start, pattern=r"^cat:add:(work_in|work_out|personal_out)$"),
            CallbackQueryHandler(on_cat_del_start, pattern=r"^cat:del:(work_in|work_out|personal_out)$"),
            CallbackQueryHandler(on_allowed_add_start, pattern=r"^acc:users:add$"),
            CallbackQueryHandler(on_allowed_del_start, pattern=r"^acc:users:del$"),
        ],
        states={
            ST_GREG_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_greg_date_input)],
            ST_JAL_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_jal_date_input)],

            ST_ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_add_category)],
            ST_ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_add_amount)],
            ST_ADD_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_add_desc),
                CallbackQueryHandler(on_skip_desc, pattern=r"^add:skip_desc$"),
            ],

            ST_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_item_edit_value)],
            ST_ADD_ALLOWED_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_allowed_id_input)],
            ST_CAT_DEL_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_cat_del_value)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )
    app.add_handler(conv)

    return app

def main():
    app = build_app()
    print(f"{PROJECT_NAME} bot running with single DB: {DB_PATH}")
    app.run_polling()

if __name__ == "__main__":
    main()
