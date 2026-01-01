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

TZ = pytz.timezone("Asia/Tehran")

PROJECT_NAME = "KasbBook"
DB_PATH = f"{PROJECT_NAME}.db"

# =========================
# Access Modes
# =========================
ACCESS_ADMIN_ONLY = "admin_only"
ACCESS_ALLOWED_USERS = "allowed_users"
ACCESS_PUBLIC = "public"

# =========================
# Transaction Types
# =========================
WORK_IN = "work_in"
WORK_OUT = "work_out"
PERSONAL_OUT = "personal_out"
INSTALLMENT_NAME = "قسط"

TTYPE_LABEL = {
    WORK_IN: "ورودی 💼",
    WORK_OUT: "خروجی 🧾",
    PERSONAL_OUT: "خروجی شخصی 👤",
}

# =========================
# Conversation States
# =========================
(
    ST_GREG_DATE,
    ST_JAL_DATE,

    ST_ADD_PICK_CATEGORY,    # انتخاب نوع از دکمه‌ها
    ST_ADD_NEW_CATEGORY,     # اگر کاربر خواست نوع جدید بسازه
    ST_ADD_AMOUNT,
    ST_ADD_DESC,

    ST_ITEM_EDIT_VALUE,

    ST_CAT_ADD_VALUE,
    ST_CAT_DEL_CONFIRM,

    ST_ADMIN_ADD_ID,
    ST_ADMIN_ADD_NAME,

    ST_DB_IMPORT_FILE,
    ST_BACKUP_HOURS,
    ST_BACKUP_TARGET,
) = range(14)

# =========================
# Utils
# =========================
def ncomma(x: int) -> str:
    try:
        return f"{int(x):,}"
    except Exception:
        return str(x)

def now_utc() -> str:
    return datetime.utcnow().isoformat()

def safe_username(u) -> str:
    return f"@{u}" if u else "ندارد"

def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

# =========================
# DB Init
# =========================
def db_init():
    c = conn()
    cur = c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
      k TEXT PRIMARY KEY,
      v TEXT NOT NULL
    );
    """)

    # admins list (besides primary admin)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
      user_id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      added_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
      owner_user_id INTEGER NOT NULL,
      actor_user_id INTEGER NOT NULL,
      date_g TEXT NOT NULL,
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
      owner_user_id INTEGER NOT NULL,
      grp TEXT NOT NULL CHECK(grp IN ('work_in','work_out','personal_out')),
      name TEXT NOT NULL,
      is_locked INTEGER NOT NULL DEFAULT 0
    );
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_cat_scope_owner_grp_name ON categories(scope, owner_user_id, grp, name);")

    def set_default(k, v):
        cur.execute("INSERT OR IGNORE INTO settings(k, v) VALUES(?,?)", (k, v))

    set_default("access_mode", ACCESS_ADMIN_ONLY)     # default: admin only
    set_default("share_enabled", "0")                 # default: off

    set_default("backup_enabled", "0")                # 0/1
    set_default("backup_hours", "24")
    set_default("backup_target_id", str(ADMIN_CHAT_ID))

    c.commit()
    c.close()

def cfg_get(k: str) -> str:
    c = conn()
    row = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    c.close()
    return row["v"] if row else ""

def cfg_set(k: str, v: str):
    c = conn()
    c.execute(
        "INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (k, v),
    )
    c.commit()
    c.close()

# =========================
# Access / Admins
# =========================
def admin_add(user_id: int, name: str):
    c = conn()
    c.execute("INSERT OR REPLACE INTO admins(user_id, name, added_at) VALUES(?,?,?)", (user_id, name, now_utc()))
    c.commit()
    c.close()

def admin_remove(user_id: int):
    c = conn()
    c.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    c.commit()
    c.close()

def admin_list() -> List[Tuple[int, str]]:
    c = conn()
    rows = c.execute("SELECT user_id, name FROM admins ORDER BY name ASC").fetchall()
    c.close()
    return [(int(r["user_id"]), r["name"]) for r in rows]

def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_CHAT_ID:
        return True
    c = conn()
    row = c.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,)).fetchone()
    c.close()
    return row is not None

def access_denied_text(user) -> str:
    return (
        "❌ شما هنوز دسترسی لازم را ندارید.\n\n"
        f"🆔 آیدی عددی شما: {user.id}\n"
        f"👤 یوزرنیم شما: {safe_username(user.username)}\n\n"
        "این پیام را برای ادمین اصلی ارسال کنید تا شما را اضافه کند ✅\n"
        f"ادمین اصلی: @{ADMIN_USERNAME}"
    )

def has_access(user_id: int) -> bool:
    mode = cfg_get("access_mode")
    if mode == ACCESS_PUBLIC:
        return True
    if mode == ACCESS_ALLOWED_USERS:
        return is_admin(user_id)
    # admin_only
    return is_admin(user_id)

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
# Scope logic (single DB)
# =========================
def current_scope(user_id: int) -> Tuple[str, int]:
    mode = cfg_get("access_mode")
    share_enabled = (cfg_get("share_enabled") == "1")

    if mode == ACCESS_PUBLIC:
        return ("private", user_id)

    if mode == ACCESS_ALLOWED_USERS and share_enabled:
        return ("shared", ADMIN_CHAT_ID)

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
# Date helpers
# =========================
def today_g() -> str:
    return datetime.now(TZ).date().isoformat()

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

def pretty_date(g: str) -> str:
    try:
        gg = datetime.strptime(g, "%Y-%m-%d").date()
        j = jdatetime.date.fromgregorian(date=gg)
        return f"{g}  |  شمسی: {j.year:04d}-{j.month:02d}-{j.day:02d}"
    except Exception:
        return g

# =========================
# Data ops
# =========================
def add_tx(actor_user_id: int, date_g: str, ttype: str, category: str, amount: int, desc: str):
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
    return True, "حذف شد ✅"

# =========================
# Calculations
# =========================
def daily_sums(user_id: int, date_g: str) -> Dict[str, int]:
    rows = get_day_txs(user_id, date_g)
    work_in = sum(r["amount"] for r in rows if r["ttype"] == WORK_IN)
    work_out = sum(r["amount"] for r in rows if r["ttype"] == WORK_OUT)

    personal_wo_inst = sum(r["amount"] for r in rows if r["ttype"] == PERSONAL_OUT and r["category"] != INSTALLMENT_NAME)
    installment = sum(r["amount"] for r in rows if r["ttype"] == PERSONAL_OUT and r["category"] == INSTALLMENT_NAME)

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
    personal_wo_inst = sum(r["amount"] for r in rows if r["ttype"] == PERSONAL_OUT and r["category"] != INSTALLMENT_NAME)
    installment = sum(r["amount"] for r in rows if r["ttype"] == PERSONAL_OUT and r["category"] == INSTALLMENT_NAME)

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
# Backup helpers
# =========================
def make_backup_filename() -> str:
    # KasbBook_backup_YYYY-MM-DD_HH-MM.db
    return f"{PROJECT_NAME}_backup_{datetime.now(TZ).strftime('%Y-%m-%d_%H-%M')}.db"

def is_sqlite_file(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(16)
        return head.startswith(b"SQLite format 3")
    except Exception:
        return False

async def send_backup_file(bot, chat_id: int):
    backup_name = make_backup_filename()
    shutil.copyfile(DB_PATH, backup_name)
    try:
        await bot.send_document(chat_id=chat_id, document=InputFile(backup_name))
    finally:
        try:
            os.remove(backup_name)
        except Exception:
            pass

def schedule_or_cancel_backup_job(app: Application):
    for job in app.job_queue.get_jobs_by_name("auto_backup"):
        job.schedule_removal()

    if cfg_get("backup_enabled") != "1":
        return

    try:
        hours = int(cfg_get("backup_hours") or "24")
        if hours <= 0:
            hours = 24
    except Exception:
        hours = 24

    async def job_callback(context: ContextTypes.DEFAULT_TYPE):
        try:
            target_id = int(cfg_get("backup_target_id") or str(ADMIN_CHAT_ID))
        except Exception:
            target_id = ADMIN_CHAT_ID
        await send_backup_file(context.bot, target_id)

    app.job_queue.run_repeating(job_callback, interval=hours * 3600, first=hours * 3600, name="auto_backup")

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
        [InlineKeyboardButton("📅 ثبت برای امروز", callback_data="tx:date:today")],
        [InlineKeyboardButton("📆 انتخاب تاریخ میلادی", callback_data="tx:date:greg")],
        [InlineKeyboardButton("🗓 انتخاب تاریخ شمسی", callback_data="tx:date:jal")],
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="m:home")],
    ])

def kb_skip_desc() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭ رد کردن توضیحات", callback_data="add:skip_desc")]])

def kb_day_menu(date_g: str, day_rows: List[sqlite3.Row]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []

    # دکمه‌های افزودن
    buttons.append([
        InlineKeyboardButton("➕ ورودی", callback_data=f"add:{WORK_IN}:{date_g}"),
        InlineKeyboardButton("➖ خروجی", callback_data=f"add:{WORK_OUT}:{date_g}"),
        InlineKeyboardButton("👤 شخصی", callback_data=f"add:{PERSONAL_OUT}:{date_g}"),
    ])

    rows_by_type: Dict[str, List[sqlite3.Row]] = {WORK_IN: [], WORK_OUT: [], PERSONAL_OUT: []}
    for r in day_rows[:200]:
        rows_by_type[r["ttype"]].append(r)

    def section(title: str, ttype: str):
        buttons.append([InlineKeyboardButton(f"— {title} —", callback_data="noop")])
        items = rows_by_type.get(ttype, [])
        if not items:
            buttons.append([InlineKeyboardButton("هنوز چیزی ثبت نشده 🙂", callback_data="noop")])
            return
        for r in items[:60]:
            cb = f"item:open:{r['id']}:{date_g}"
            # تلاش برای 70/30 با طول متن
            left = f"🔹 {r['category']}"
            right = f"💰 {ncomma(r['amount'])}"
            buttons.append([
                InlineKeyboardButton(left, callback_data=cb),
                InlineKeyboardButton(right, callback_data=cb),
            ])

    section("ورودی 💼", WORK_IN)
    section("خروجی 🧾", WORK_OUT)
    section("خروجی شخصی 👤", PERSONAL_OUT)

    buttons.append([InlineKeyboardButton("↩️ تغییر تاریخ", callback_data="m:tx")])
    buttons.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="m:home")])
    return InlineKeyboardMarkup(buttons)

def kb_item_actions(tx_id: int, date_g: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ ویرایش نوع", callback_data=f"item:edit:category:{tx_id}:{date_g}"),
            InlineKeyboardButton("✏️ ویرایش مبلغ", callback_data=f"item:edit:amount:{tx_id}:{date_g}"),
        ],
        [InlineKeyboardButton("✏️ ویرایش توضیحات", callback_data=f"item:edit:description:{tx_id}:{date_g}")],
        [InlineKeyboardButton("🗑 حذف تراکنش", callback_data=f"item:delete:{tx_id}:{date_g}")],
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
            InlineKeyboardButton("📥 ریزِ ورودی‌ها", callback_data=f"rep:detail:{WORK_IN}:{year}:{month}"),
            InlineKeyboardButton("📤 ریزِ خروجی‌ها", callback_data=f"rep:detail:{WORK_OUT}:{year}:{month}"),
        ],
        [InlineKeyboardButton("👤 ریزِ خروجی شخصی", callback_data=f"rep:detail:{PERSONAL_OUT}:{year}:{month}")],
        [InlineKeyboardButton("↩️ انتخاب ماه", callback_data="m:rep")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="m:home")],
    ])

def kb_settings(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🧩 مدیریت نوع‌ها", callback_data="set:cats")],
        [InlineKeyboardButton("🛡 مدیریت دسترسی و ادمین‌ها", callback_data="set:access")],
    ]
    if user_id == ADMIN_CHAT_ID:
        buttons.append([InlineKeyboardButton("🗄 دیتابیس", callback_data="set:db")])
    buttons.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="m:home")])
    return InlineKeyboardMarkup(buttons)

def kb_access_menu() -> InlineKeyboardMarkup:
    mode = cfg_get("access_mode")
    mode_txt = {
        ACCESS_ADMIN_ONLY: "فقط ادمین‌ها 🔒",
        ACCESS_ALLOWED_USERS: "ادمین‌های مجاز ✅",
        ACCESS_PUBLIC: "همگانی 🌍",
    }.get(mode, mode)

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔎 حالت فعلی: {mode_txt}", callback_data="noop")],
        [InlineKeyboardButton("🔒 فقط ادمین‌ها", callback_data=f"acc:set:{ACCESS_ADMIN_ONLY}")],
        [InlineKeyboardButton("✅ ادمین‌های مجاز", callback_data=f"acc:set:{ACCESS_ALLOWED_USERS}")],
        [InlineKeyboardButton("🌍 همگانی", callback_data=f"acc:set:{ACCESS_PUBLIC}")],
        [InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="acc:admins")],
        [InlineKeyboardButton("🔁 اشتراک اطلاعات بین ادمین‌ها", callback_data="acc:share:toggle")],
        [InlineKeyboardButton("↩️ بازگشت", callback_data="m:set")],
    ])

def kb_admins_manage() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("➕ اضافه کردن ادمین", callback_data="adm:add")],
    ]
    # لیست ادمین‌ها
    for uid, name in admin_list()[:60]:
        buttons.append([
            InlineKeyboardButton(f"{name} ({uid})", callback_data="noop"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"adm:del:{uid}"),
        ])
    buttons.append([InlineKeyboardButton("↩️ بازگشت", callback_data="set:access")])
    return InlineKeyboardMarkup(buttons)

def kb_cats_groups() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ورودی کار 💼", callback_data=f"cat:grp:{WORK_IN}")],
        [InlineKeyboardButton("خروجی کار 🧾", callback_data=f"cat:grp:{WORK_OUT}")],
        [InlineKeyboardButton("خروجی شخصی 👤", callback_data=f"cat:grp:{PERSONAL_OUT}")],
        [InlineKeyboardButton("↩️ بازگشت", callback_data="m:set")],
    ])

def kb_cat_list_manage(user_id: int, grp: str) -> InlineKeyboardMarkup:
    cats = list_categories(user_id, grp)
    buttons: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("➕ اضافه کردن نوع", callback_data=f"cat:add:{grp}")],
    ]
    for c in cats[:80]:
        if c == INSTALLMENT_NAME and grp == PERSONAL_OUT:
            buttons.append([InlineKeyboardButton(f"{c} (قفل)", callback_data="noop")])
            continue
        buttons.append([
            InlineKeyboardButton(c, callback_data="noop"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"cat:del:{grp}:{c}"),
        ])
    buttons.append([InlineKeyboardButton("↩️ بازگشت", callback_data="set:cats")])
    return InlineKeyboardMarkup(buttons)

def kb_db_admin() -> InlineKeyboardMarkup:
    enabled = (cfg_get("backup_enabled") == "1")
    hours = cfg_get("backup_hours") or "24"
    target = cfg_get("backup_target_id") or str(ADMIN_CHAT_ID)
    txt = "روشن ✅" if enabled else "خاموش ❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 گرفتن بکاپ", callback_data="db:backup")],
        [InlineKeyboardButton("📥 وارد کردن بکاپ", callback_data="db:import")],
        [InlineKeyboardButton(f"⏱ بکاپ خودکار: {txt}", callback_data="db:auto:toggle")],
        [InlineKeyboardButton(f"⚙️ تنظیم بکاپ خودکار (هر {hours} ساعت | مقصد {target})", callback_data="db:auto:config")],
        [InlineKeyboardButton("↩️ بازگشت", callback_data="m:set")],
    ])

def kb_pick_category(user_id: int, grp: str, date_g: str) -> InlineKeyboardMarkup:
    cats = list_categories(user_id, grp)
    buttons: List[List[InlineKeyboardButton]] = []
    # دکمه‌های نوع
    for i in range(0, min(len(cats), 24), 2):
        row = [InlineKeyboardButton(cats[i], callback_data=f"add:cat:{grp}:{date_g}:{cats[i]}")]
        if i + 1 < min(len(cats), 24):
            row.append(InlineKeyboardButton(cats[i+1], callback_data=f"add:cat:{grp}:{date_g}:{cats[i+1]}"))
        buttons.append(row)

    buttons.append([InlineKeyboardButton("➕ افزودن نوع جدید", callback_data=f"add:newcat:{grp}:{date_g}")])
    buttons.append([InlineKeyboardButton("↩️ بازگشت", callback_data=f"day:open:{date_g}")])
    return InlineKeyboardMarkup(buttons)

# =========================
# Screens
# =========================
def day_text(user_id: int, date_g: str) -> str:
    ds = daily_sums(user_id, date_g)
    dt = datetime.strptime(date_g, "%Y-%m-%d").date()
    y, m = dt.year, dt.month
    ms = month_sums(user_id, y, m)

    scope, _ = current_scope(user_id)
    scope_txt = "مشترک ✅" if scope == "shared" else "خصوصی 🔒"

    return (
        f"📅 تاریخ انتخاب‌شده:\n{pretty_date(date_g)}\n\n"
        f"🗂 وضعیت داده‌ها: {scope_txt}\n\n"
        f"📌 جمع‌بندی روزانه\n"
        f"📥 ورودی روز: {ncomma(ds['income'])} تومان\n"
        f"📤 خروجی روز: {ncomma(ds['out'])} تومان\n"
        f"💵 درآمد روز (ورودی-خروجی): {ncomma(ds['net'])} تومان\n"
        f"👤 خروجی شخصی (بدون قسط): {ncomma(ds['personal_wo_inst'])} تومان\n"
        f"💰 پس‌انداز روز: {ncomma(ds['saving'])} تومان\n"
        f"🧾 قسط امروز: {ncomma(ds['installment'])} تومان\n\n"
        f"📌 جمع‌بندی ماه میلادی {m:02d}/{y}\n"
        f"📥 ورودی ماه: {ncomma(ms['income'])} تومان\n"
        f"📤 خروجی ماه: {ncomma(ms['out'])} تومان\n"
        f"💵 درآمد ماه: {ncomma(ms['net'])} تومان\n"
        f"👤 خروجی شخصی ماه (بدون قسط): {ncomma(ms['personal_wo_inst'])} تومان\n"
        f"💰 پس‌انداز ماه: {ncomma(ms['saving'])} تومان\n"
        f"🧾 جمع قسط ماه: {ncomma(ms['installment'])} تومان\n"
    )

# =========================
# Handlers
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_init()
    if not await guard(update):
        return
    await update.message.reply_text(
        f"سلام 👋\nبه ربات {PROJECT_NAME} خوش اومدی ✅\n\n"
        "از منوی زیر انتخاب کن:",
        reply_markup=kb_main()
    )

async def on_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()

    if q.data == "m:home":
        await q.edit_message_text("🏠 منوی اصلی:", reply_markup=kb_main())
        return

    if q.data == "m:tx":
        await q.edit_message_text("📌 بخش تراکنش‌ها\n\nلطفاً تاریخ را انتخاب کن:", reply_markup=kb_tx_date())
        return

    if q.data == "m:rep":
        year = datetime.now(TZ).year
        await q.edit_message_text("📊 گزارش‌ها\n\nماه مورد نظر را انتخاب کن:", reply_markup=kb_reports_year(year))
        return

    if q.data == "m:set":
        await q.edit_message_text("⚙️ تنظیمات:\n\nیکی از گزینه‌ها را انتخاب کن 👇", reply_markup=kb_settings(q.from_user.id))
        return

# ---- Transactions date selection
async def on_tx_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()

    if q.data == "tx:date:today":
        await open_day(q, today_g())
        return ConversationHandler.END

    if q.data == "tx:date:greg":
        await q.edit_message_text(
            "📆 لطفاً تاریخ میلادی را با فرمت زیر ارسال کن:\n"
            "مثال: 2026-01-01\n\n"
            "✍️ منتظر پیام شما هستم...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="m:tx")]])
        )
        return ST_GREG_DATE

    if q.data == "tx:date:jal":
        await q.edit_message_text(
            "🗓 لطفاً تاریخ شمسی را با فرمت زیر ارسال کن:\n"
            "مثال: 1404-10-11\n\n"
            "✍️ منتظر پیام شما هستم...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="m:tx")]])
        )
        return ST_JAL_DATE

    return ConversationHandler.END

async def open_day(q, date_g: str):
    user_id = q.from_user.id
    rows = get_day_txs(user_id, date_g)
    await q.edit_message_text(day_text(user_id, date_g), reply_markup=kb_day_menu(date_g, rows))

async def send_day_message(update: Update, date_g: str):
    user_id = update.effective_user.id
    rows = get_day_txs(user_id, date_g)
    await update.message.reply_text(day_text(user_id, date_g), reply_markup=kb_day_menu(date_g, rows))

async def on_greg_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    txt = (update.message.text or "").strip()
    if not gregorian_validate(txt):
        await update.message.reply_text("⚠️ فرمت تاریخ درست نیست.\nمثال صحیح: 2026-01-01")
        return ST_GREG_DATE
    await send_day_message(update, txt)
    return ConversationHandler.END

async def on_jal_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    txt = (update.message.text or "").strip()
    g = jalali_to_gregorian(txt)
    if not g:
        await update.message.reply_text("⚠️ تاریخ شمسی یا فرمت اشتباه است.\nمثال: 1404-10-11")
        return ST_JAL_DATE
    await send_day_message(update, g)
    return ConversationHandler.END

async def on_day_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, date_g = q.data.split(":", 2)
    await open_day(q, date_g)

# ---- Add transaction (pick category buttons)
async def on_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    _, ttype, date_g = q.data.split(":", 2)

    context.user_data.clear()
    context.user_data["add_ttype"] = ttype
    context.user_data["add_date_g"] = date_g

    await q.edit_message_text(
        f"✅ افزودن {TTYPE_LABEL[ttype]}\n\n"
        "لطفاً نوع تراکنش را از دکمه‌های زیر انتخاب کن 👇",
        reply_markup=kb_pick_category(q.from_user.id, ttype, date_g)
    )
    return ST_ADD_PICK_CATEGORY

async def on_add_pick_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()

    # add:cat:{grp}:{date}:{name}
    parts = q.data.split(":", 4)
    if len(parts) == 5 and parts[0] == "add" and parts[1] == "cat":
        grp, date_g, name = parts[2], parts[3], parts[4]
        context.user_data["add_category"] = name
        await q.edit_message_text(
            f"✅ نوع انتخاب شد: {name}\n\n"
            "💰 حالا مبلغ را فقط به صورت عدد ارسال کن.\n"
            "مثال: 50000\n\n"
            "📌 واحد: تومان",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data=f"day:open:{date_g}")]])
        )
        return ST_ADD_AMOUNT

    # add:newcat:{grp}:{date}
    if q.data.startswith("add:newcat:"):
        _, _, grp, date_g = q.data.split(":", 3)
        context.user_data["add_ttype"] = grp
        context.user_data["add_date_g"] = date_g
        await q.edit_message_text(
            "➕ افزودن نوع جدید\n\n"
            "لطفاً نام نوع جدید را ارسال کن.\n"
            "مثال: VPN",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data=f"day:open:{date_g}")]])
        )
        return ST_ADD_NEW_CATEGORY

    return ConversationHandler.END

async def on_add_new_category_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("⚠️ نام نوع نمی‌تواند خالی باشد. دوباره بفرست 🙂")
        return ST_ADD_NEW_CATEGORY

    grp = context.user_data.get("add_ttype")
    date_g = context.user_data.get("add_date_g")
    add_category(update.effective_user.id, grp, name)
    context.user_data["add_category"] = name

    await update.message.reply_text(
        f"✅ نوع «{name}» اضافه شد.\n\n"
        "💰 حالا مبلغ را فقط به صورت عدد ارسال کن.\n"
        "مثال: 50000\n\n"
        "📌 واحد: تومان"
    )
    return ST_ADD_AMOUNT

async def on_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    txt = (update.message.text or "").strip().replace(",", "")
    if not txt.isdigit():
        await update.message.reply_text("⚠️ مبلغ معتبر نیست.\nمثال صحیح: 50000\n\n📌 فقط عدد (تومان) بفرست.")
        return ST_ADD_AMOUNT

    context.user_data["add_amount"] = int(txt)
    await update.message.reply_text(
        "📝 اگر توضیحی داری ارسال کن.\n"
        "اگر توضیح لازم نیست، دکمه «رد کردن توضیحات» را بزن 👇",
        reply_markup=kb_skip_desc()
    )
    return ST_ADD_DESC

async def on_skip_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    context.user_data["add_desc"] = ""
    await finalize_add_from_context(q.from_user.id, q, context)
    return ConversationHandler.END

async def on_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    context.user_data["add_desc"] = (update.message.text or "").strip()
    user_id = update.effective_user.id
    date_g = context.user_data["add_date_g"]
    await finalize_add_text(user_id, update, context, date_g)
    return ConversationHandler.END

async def finalize_add_text(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE, date_g: str):
    ttype = context.user_data["add_ttype"]
    cat = context.user_data["add_category"]
    amt = context.user_data["add_amount"]
    desc = context.user_data.get("add_desc", "")

    add_tx(user_id, date_g, ttype, cat, amt, desc)
    await update.message.reply_text("✅ ثبت شد و به لیست اضافه گردید 🌟")
    await send_day_message(update, date_g)

async def finalize_add_from_context(user_id: int, q, context: ContextTypes.DEFAULT_TYPE):
    date_g = context.user_data["add_date_g"]
    ttype = context.user_data["add_ttype"]
    cat = context.user_data["add_category"]
    amt = context.user_data["add_amount"]
    desc = context.user_data.get("add_desc", "")

    add_tx(user_id, date_g, ttype, cat, amt, desc)
    rows = get_day_txs(user_id, date_g)
    await q.edit_message_text("✅ ثبت شد 🌟\n\n" + day_text(user_id, date_g), reply_markup=kb_day_menu(date_g, rows))

# ---- Item open/edit/delete
async def on_item_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, tx_id, date_g = q.data.split(":", 3)

    row = get_tx(q.from_user.id, int(tx_id))
    if not row:
        await q.edit_message_text("⚠️ تراکنش پیدا نشد.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ بازگشت", callback_data=f"day:open:{date_g}")]
        ]))
        return

    desc = row["description"] or "—"
    await q.edit_message_text(
        "ℹ️ اطلاعات تراکنش\n\n"
        f"📌 دسته‌بندی: {row['category']}\n"
        f"💰 مبلغ: {ncomma(row['amount'])} تومان\n"
        f"📝 توضیحات: {desc}\n"
        f"📅 تاریخ: {pretty_date(row['date_g'])}\n",
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
    await q.edit_message_text("🗑 تراکنش حذف شد.\n\n" + day_text(q.from_user.id, date_g), reply_markup=kb_day_menu(date_g, rows))

async def on_item_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    _, _, field, tx_id, date_g = q.data.split(":", 4)

    context.user_data.clear()
    context.user_data["edit_field"] = field
    context.user_data["edit_tx_id"] = int(tx_id)
    context.user_data["edit_date_g"] = date_g

    label = {"category": "نوع/دسته", "amount": "مبلغ", "description": "توضیحات"}[field]
    msg = (
        f"✏️ ویرایش {label}\n\n"
        "لطفاً مقدار جدید را ارسال کن 👇"
    )
    if field == "amount":
        msg += "\n\n📌 فقط عدد (تومان) بفرست. مثال: 50000"

    await q.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data=f"item:open:{tx_id}:{date_g}")]])
    )
    return ST_ITEM_EDIT_VALUE

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
            await update.message.reply_text("⚠️ مبلغ معتبر نیست. فقط عدد بفرست. مثال: 50000")
            return ST_ITEM_EDIT_VALUE
        value = int(t)
    else:
        value = txt

    update_tx_field(user_id, tx_id, field, value)
    await update.message.reply_text("✅ ویرایش انجام شد 🌟")
    await send_day_message(update, date_g)
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
        f"📊 گزارش ماه {m:02d}/{y}\n"
        f"⏳ بازه: {ms['start']} تا {ms['end']}\n\n"
        f"📥 جمع ورودی‌ها: {ncomma(ms['income'])} تومان\n"
        f"📤 جمع خروجی‌ها: {ncomma(ms['out'])} تومان\n"
        f"💵 درآمد ماه: {ncomma(ms['net'])} تومان\n"
        f"👤 خروجی شخصی (بدون قسط): {ncomma(ms['personal_wo_inst'])} تومان\n"
        f"💰 پس‌انداز (بدون قسط): {ncomma(ms['saving'])} تومان\n"
        f"🧾 جمع قسط ماه: {ncomma(ms['installment'])} تومان\n"
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
        WORK_IN: "📥 ریزِ ورودی‌ها (بر اساس نوع)",
        WORK_OUT: "📤 ریزِ خروجی‌ها (بر اساس نوع)",
        PERSONAL_OUT: "👤 ریزِ خروجی شخصی (بر اساس نوع)",
    }[grp]

    lines = [f"{title}\nماه {m:02d}/{y}\n"]
    if not items:
        lines.append("هنوز داده‌ای برای این ماه ثبت نشده 🙂")
    else:
        for cat, s in items:
            lines.append(f"• {cat}: {ncomma(s)} تومان")
        if grp == PERSONAL_OUT:
            lines.append("\nℹ️ قسط جدا حساب می‌شود و از «شخصی/پس‌انداز» کم نمی‌شود.")

    await q.edit_message_text("\n".join(lines), reply_markup=kb_report_detail(y, m))

# ---- Settings / Categories
async def on_set_cats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🧩 مدیریت نوع‌ها\n\nگروه موردنظر را انتخاب کن 👇", reply_markup=kb_cats_groups())

async def on_cat_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    _, _, grp = q.data.split(":", 2)
    await q.edit_message_text(f"🧩 نوع‌های {TTYPE_LABEL[grp]}\n\nاز لیست زیر مدیریت کن 👇", reply_markup=kb_cat_list_manage(q.from_user.id, grp))

async def on_cat_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    _, _, grp = q.data.split(":", 2)
    context.user_data.clear()
    context.user_data["cat_grp"] = grp
    await q.edit_message_text(
        f"➕ افزودن نوع برای {TTYPE_LABEL[grp]}\n\n"
        "لطفاً نام نوع جدید را ارسال کن.\nمثال: VPN",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data=f"cat:grp:{grp}")]])
    )
    return ST_CAT_ADD_VALUE

async def on_cat_add_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    grp = context.user_data.get("cat_grp")
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("⚠️ نام نوع خالی است. دوباره ارسال کن.")
        return ST_CAT_ADD_VALUE
    add_category(update.effective_user.id, grp, name)
    await update.message.reply_text("✅ نوع جدید اضافه شد 🌟")
    # برگشت به لیست
    await update.message.reply_text(f"لیست نوع‌های {TTYPE_LABEL[grp]}:", reply_markup=kb_cat_list_manage(update.effective_user.id, grp))
    return ConversationHandler.END

async def on_cat_del_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    # cat:del:grp:name
    _, _, grp, name = q.data.split(":", 3)
    okk, msg = del_category(q.from_user.id, grp, name)
    await q.edit_message_text((("✅ " if okk else "⚠️ ") + msg) + "\n\n" + f"نوع‌های {TTYPE_LABEL[grp]}:", reply_markup=kb_cat_list_manage(q.from_user.id, grp))

# ---- Settings / Access & Admins
async def on_access_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        await q.edit_message_text("⛔ این بخش فقط برای ادمین اصلی فعال است.", reply_markup=kb_settings(q.from_user.id))
        return
    await q.edit_message_text("🛡 مدیریت دسترسی و ادمین‌ها:", reply_markup=kb_access_menu())

async def on_access_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    _, _, mode = q.data.split(":", 2)
    cfg_set("access_mode", mode)
    await q.edit_message_text("✅ حالت دسترسی ذخیره شد.", reply_markup=kb_access_menu())

async def on_share_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    enabled = (cfg_get("share_enabled") == "1")
    cfg_set("share_enabled", "0" if enabled else "1")
    await q.edit_message_text(
        "🔁 اشتراک اطلاعات بین ادمین‌ها\n\n"
        f"وضعیت فعلی: {'روشن ✅' if (cfg_get('share_enabled')=='1') else 'خاموش ❌'}\n\n"
        "✅ روشن: همه روی یک دیتابیس مشترک کار می‌کنن.\n"
        "❌ خاموش: هر نفر دیتای خصوصی خودش رو می‌بینه.",
        reply_markup=kb_access_menu()
    )

async def on_admins_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    await q.edit_message_text("👥 مدیریت ادمین‌ها:", reply_markup=kb_admins_manage())

async def on_admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END
    context.user_data.clear()
    await q.edit_message_text(
        "➕ افزودن ادمین جدید\n\n"
        "لطفاً آیدی عددی فرد را ارسال کن (فقط عدد) 👇",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="acc:admins")]])
    )
    return ST_ADMIN_ADD_ID

async def on_admin_add_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    if update.effective_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END

    txt = (update.message.text or "").strip()
    if not txt.isdigit():
        await update.message.reply_text("⚠️ فقط عدد ارسال کن. مثال: 123456789")
        return ST_ADMIN_ADD_ID

    context.user_data["new_admin_id"] = int(txt)
    await update.message.reply_text(
        "✅ خیلی خوب!\n\nحالا نام نمایشی ادمین را ارسال کن 👇\nمثال: علی"
    )
    return ST_ADMIN_ADD_NAME

async def on_admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    if update.effective_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("⚠️ نام خالیه. دوباره ارسال کن.")
        return ST_ADMIN_ADD_NAME

    uid = int(context.user_data["new_admin_id"])
    admin_add(uid, name)
    await update.message.reply_text("✅ ادمین اضافه شد 🌟")
    await update.message.reply_text("لیست ادمین‌ها:", reply_markup=kb_admins_manage())
    return ConversationHandler.END

async def on_admin_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    _, _, uid = q.data.split(":", 2)
    uid = int(uid)
    admin_remove(uid)
    await q.edit_message_text("🗑 حذف شد.\n\nلیست ادمین‌ها:", reply_markup=kb_admins_manage())

# ---- DB (admin only)
async def on_db_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        await q.edit_message_text("⛔ این بخش فقط برای ادمین اصلی است.", reply_markup=kb_settings(q.from_user.id))
        return
    await q.edit_message_text("🗄 مدیریت دیتابیس:", reply_markup=kb_db_admin())

async def on_db_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return
    await send_backup_file(context.bot, q.from_user.id)
    await q.edit_message_text("✅ بکاپ ارسال شد.", reply_markup=kb_db_admin())

async def on_db_import_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END

    await q.edit_message_text(
        "📥 وارد کردن بکاپ\n\n"
        "لطفاً فایل بکاپ دیتابیس با پسوند .db را ارسال کن.\n"
        "⚠️ توجه: با این کار دیتابیس فعلی جایگزین می‌شود.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="set:db")]])
    )
    return ST_DB_IMPORT_FILE

async def on_db_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    if update.effective_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END

    doc = update.message.document
    if not doc or not (doc.file_name or "").lower().endswith(".db"):
        await update.message.reply_text("⚠️ لطفاً فقط فایل دیتابیس با پسوند .db ارسال کن.")
        return ST_DB_IMPORT_FILE

    tmp_name = f"import_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.db"
    tgfile = await doc.get_file()
    await tgfile.download_to_drive(custom_path=tmp_name)

    if not is_sqlite_file(tmp_name):
        try:
            os.remove(tmp_name)
        except Exception:
            pass
        await update.message.reply_text("⚠️ این فایل SQLite معتبر نیست.")
        return ConversationHandler.END

    bak_name = f"{DB_PATH}.bak_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}"
    try:
        if os.path.exists(DB_PATH):
            shutil.copyfile(DB_PATH, bak_name)
        shutil.copyfile(tmp_name, DB_PATH)
        db_init()
    finally:
        try:
            os.remove(tmp_name)
        except Exception:
            pass

    schedule_or_cancel_backup_job(context.application)
    await update.message.reply_text("✅ بکاپ با موفقیت وارد شد و دیتابیس بروزرسانی گردید 🌟")
    return ConversationHandler.END

async def on_db_auto_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return

    enabled = (cfg_get("backup_enabled") == "1")
    cfg_set("backup_enabled", "0" if enabled else "1")
    schedule_or_cancel_backup_job(context.application)
    await q.edit_message_text("✅ تنظیم بکاپ خودکار بروزرسانی شد.", reply_markup=kb_db_admin())

async def on_db_auto_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END

    await q.edit_message_text(
        "⏱ تنظیم بکاپ خودکار\n\n"
        "هر چند ساعت یک‌بار بکاپ ارسال شود؟\n"
        "مثال: 6\n\n"
        "✍️ فقط عدد ارسال کن.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="set:db")]])
    )
    return ST_BACKUP_HOURS

async def on_backup_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    if update.effective_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END

    txt = (update.message.text or "").strip()
    if not txt.isdigit():
        await update.message.reply_text("⚠️ فقط عدد ارسال کن. مثال: 6")
        return ST_BACKUP_HOURS

    hours = int(txt)
    if hours <= 0 or hours > 720:
        await update.message.reply_text("⚠️ عدد منطقی بفرست (بین 1 تا 720).")
        return ST_BACKUP_HOURS

    cfg_set("backup_hours", str(hours))
    await update.message.reply_text(
        f"✅ خیلی خوب! هر {hours} ساعت تنظیم شد.\n\n"
        "حالا آیدی عددی مقصد بکاپ را ارسال کن.\n"
        f"اگر می‌خوای پیش‌فرض ادمین باشد، همین را بفرست: {ADMIN_CHAT_ID}"
    )
    return ST_BACKUP_TARGET

async def on_backup_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return ConversationHandler.END
    if update.effective_user.id != ADMIN_CHAT_ID:
        return ConversationHandler.END

    txt = (update.message.text or "").strip()
    if not txt.isdigit():
        await update.message.reply_text("⚠️ فقط آیدی عددی بفرست (عدد).")
        return ST_BACKUP_TARGET

    cfg_set("backup_target_id", str(int(txt)))
    schedule_or_cancel_backup_job(context.application)
    await update.message.reply_text("✅ مقصد بکاپ ذخیره شد 🌟", reply_markup=kb_db_admin())
    return ConversationHandler.END

async def on_noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()

# =========================
# Build app
# =========================
def build_app() -> Application:
    db_init()
    app = Application.builder().token(BOT_TOKEN).build()
    schedule_or_cancel_backup_job(app)

    # ✅ Conversation handler first (so it catches states)
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(on_tx_date, pattern=r"^tx:date:(today|greg|jal)$"),
            CallbackQueryHandler(on_add_start, pattern=r"^add:(work_in|work_out|personal_out):\d{4}-\d{2}-\d{2}$"),
            CallbackQueryHandler(on_item_edit_start, pattern=r"^item:edit:(category|amount|description):\d+:\d{4}-\d{2}-\d{2}$"),

            CallbackQueryHandler(on_cat_add_start, pattern=r"^cat:add:(work_in|work_out|personal_out)$"),
            CallbackQueryHandler(on_admin_add_start, pattern=r"^adm:add$"),

            CallbackQueryHandler(on_db_import_start, pattern=r"^db:import$"),
            CallbackQueryHandler(on_db_auto_config, pattern=r"^db:auto:config$"),
        ],
        states={
            ST_GREG_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_greg_date_input)],
            ST_JAL_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_jal_date_input)],

            ST_ADD_PICK_CATEGORY: [CallbackQueryHandler(on_add_pick_category, pattern=r"^(add:cat:|add:newcat:)")],
            ST_ADD_NEW_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_add_new_category_text)],
            ST_ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_add_amount)],
            ST_ADD_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_add_desc),
                CallbackQueryHandler(on_skip_desc, pattern=r"^add:skip_desc$"),
            ],

            ST_ITEM_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_item_edit_value)],

            ST_CAT_ADD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_cat_add_value)],

            ST_ADMIN_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_admin_add_id)],
            ST_ADMIN_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_admin_add_name)],

            ST_DB_IMPORT_FILE: [MessageHandler(filters.Document.ALL, on_db_import_file)],
            ST_BACKUP_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_backup_hours)],
            ST_BACKUP_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_backup_target)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
        per_message=True,
    )
    app.add_handler(conv)

    # commands
    app.add_handler(CommandHandler("start", cmd_start))

    # menus
    app.add_handler(CallbackQueryHandler(on_main_menu, pattern=r"^m:(home|tx|rep|set)$"))

    # day open & item ops
    app.add_handler(CallbackQueryHandler(on_day_open, pattern=r"^day:open:\d{4}-\d{2}-\d{2}$"))
    app.add_handler(CallbackQueryHandler(on_item_open, pattern=r"^item:open:\d+:\d{4}-\d{2}-\d{2}$"))
    app.add_handler(CallbackQueryHandler(on_item_delete, pattern=r"^item:delete:\d+:\d{4}-\d{2}-\d{2}$"))

    # reports
    app.add_handler(CallbackQueryHandler(on_reports_month, pattern=r"^rep:month:\d{4}:\d{1,2}$"))
    app.add_handler(CallbackQueryHandler(on_report_detail, pattern=r"^rep:detail:(work_in|work_out|personal_out):\d{4}:\d{1,2}$"))

    # settings cats
    app.add_handler(CallbackQueryHandler(on_set_cats, pattern=r"^set:cats$"))
    app.add_handler(CallbackQueryHandler(on_cat_group, pattern=r"^cat:grp:(work_in|work_out|personal_out)$"))
    app.add_handler(CallbackQueryHandler(on_cat_del_click, pattern=r"^cat:del:(work_in|work_out|personal_out):"))

    # access/admins
    app.add_handler(CallbackQueryHandler(on_access_menu, pattern=r"^set:access$"))
    app.add_handler(CallbackQueryHandler(on_access_set, pattern=r"^acc:set:(admin_only|allowed_users|public)$"))
    app.add_handler(CallbackQueryHandler(on_share_toggle, pattern=r"^acc:share:toggle$"))
    app.add_handler(CallbackQueryHandler(on_admins_menu, pattern=r"^acc:admins$"))
    app.add_handler(CallbackQueryHandler(on_admin_del, pattern=r"^adm:del:\d+$"))

    # db
    app.add_handler(CallbackQueryHandler(on_db_menu, pattern=r"^set:db$"))
    app.add_handler(CallbackQueryHandler(on_db_backup, pattern=r"^db:backup$"))
    app.add_handler(CallbackQueryHandler(on_db_auto_toggle, pattern=r"^db:auto:toggle$"))

    app.add_handler(CallbackQueryHandler(on_noop, pattern=r"^noop$"))
    return app

def main():
    app = build_app()
    print(f"{PROJECT_NAME} running... DB={DB_PATH}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
