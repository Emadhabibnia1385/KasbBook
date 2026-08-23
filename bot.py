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
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List, Dict, Set, Iterator, Callable

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
SEARCH_PAGE_SIZE = 10        # search results per page
LOAN_PAGE_SIZE = 10          # loans per page
BUDGET_PAGE_SIZE = 10        # budgets per page
DEBT_PAGE_SIZE = 10          # debts per page

DEFAULT_CURRENCY = "تومان"

# Guard rails for public mode, where anyone can start the bot.
PUBLIC_MAX_TX_PER_DAY = 300
PUBLIC_MAX_CATEGORIES = 200

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
CB_LN = "ln"    # loans / installments
CB_RC = "rc"    # recurring transactions
CB_SR = "sr"    # search
CB_CU = "cu"    # currency
CB_BG = "bg"    # budgets
CB_DT = "dt"    # debts and receivables
CB_TR = "tr"    # trend chart
CB_RM = "rm"    # reminders and digest

# Job name
JOB_BACKUP = "kasbbook_auto_backup"
JOB_RECURRING = "kasbbook_recurring"
JOB_DIGEST = "kasbbook_digest"

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

# httpx logs the full request URL at INFO, and for Telegram that URL contains
# the bot token — which would put the token in plaintext in journalctl on every
# single API call. These libraries stay at WARNING so nothing leaks into logs.
for _noisy in ("httpx", "httpcore", "telegram.vendor", "apscheduler"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

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

# Bump this when BASE_SCHEMA changes, and add a matching entry to MIGRATIONS.
SCHEMA_VERSION = 4

# The shape a brand-new database is created with. Everything is IF NOT EXISTS,
# so running it against an older database is a no-op — widening an existing
# table is the migrations' job, not this script's.
BASE_SCHEMA = """
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
    ttype TEXT NOT NULL CHECK(ttype IN ('work_in','work_out','personal_in','personal_out')),
    category TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount>=0),
    description TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    loan_id INTEGER NULL,
    receipt_file_id TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date
    ON transactions(scope, owner_user_id, date_g);
CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date_type
    ON transactions(scope, owner_user_id, date_g, ttype);
CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date_type_cat
    ON transactions(scope, owner_user_id, date_g, ttype, category);
CREATE INDEX IF NOT EXISTS idx_tx_loan
    ON transactions(loan_id);

CREATE TABLE IF NOT EXISTS categories(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
    owner_user_id INTEGER NOT NULL,
    grp TEXT NOT NULL CHECK(grp IN ('work_in','work_out','personal_in','personal_out')),
    name TEXT NOT NULL,
    is_locked INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cat_scope_owner_grp_name
    ON categories(scope, owner_user_id, grp, name);

CREATE TABLE IF NOT EXISTS loans(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
    owner_user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    installment_amount INTEGER NOT NULL CHECK(installment_amount>=0),
    installment_count INTEGER NOT NULL CHECK(installment_count>0),
    start_date_g TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_loans_owner
    ON loans(scope, owner_user_id, is_active);

CREATE TABLE IF NOT EXISTS recurring(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
    owner_user_id INTEGER NOT NULL,
    ttype TEXT NOT NULL CHECK(ttype IN ('work_in','work_out','personal_in','personal_out')),
    category TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount>=0),
    description TEXT NULL,
    period TEXT NOT NULL CHECK(period IN ('daily','weekly','monthly')),
    next_run_g TEXT NOT NULL,
    last_run_g TEXT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recurring_due
    ON recurring(is_active, next_run_g);

CREATE TABLE IF NOT EXISTS budgets(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
    owner_user_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('group','category')),
    target TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount>0),
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_target
    ON budgets(scope, owner_user_id, kind, target);

CREATE TABLE IF NOT EXISTS debts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
    owner_user_id INTEGER NOT NULL,
    person TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('owed_to_me','i_owe')),
    amount INTEGER NOT NULL CHECK(amount>=0),
    note TEXT NULL,
    due_date_g TEXT NULL,
    settled_at TEXT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_debts_open
    ON debts(scope, owner_user_id, settled_at);
"""

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None

def _table_sql(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return str(row["sql"]) if row and row["sql"] else ""

def _columns(conn: sqlite3.Connection, table: str) -> Set[str]:
    return {str(r["name"]) for r in conn.execute(f"PRAGMA table_info({table})")}

# --- migrations ------------------------------------------------------------
# Each one must be safe to run twice: a half-applied upgrade should be able to
# resume rather than corrupt.

def _m2_personal_income(conn: sqlite3.Connection) -> None:
    """Widen the ttype/grp CHECK constraints to allow personal income.

    SQLite cannot alter a CHECK constraint in place, so both tables are rebuilt.
    """
    if "personal_in" not in _table_sql(conn, "transactions"):
        conn.executescript(
            """
            BEGIN;
            CREATE TABLE transactions_v2(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
                owner_user_id INTEGER NOT NULL,
                actor_user_id INTEGER NOT NULL,
                date_g TEXT NOT NULL,
                ttype TEXT NOT NULL CHECK(ttype IN ('work_in','work_out','personal_in','personal_out')),
                category TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK(amount>=0),
                description TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO transactions_v2(
                id, scope, owner_user_id, actor_user_id, date_g, ttype,
                category, amount, description, created_at, updated_at)
            SELECT
                id, scope, owner_user_id, actor_user_id, date_g, ttype,
                category, amount, description, created_at, updated_at
            FROM transactions;
            DROP TABLE transactions;
            ALTER TABLE transactions_v2 RENAME TO transactions;
            CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date
                ON transactions(scope, owner_user_id, date_g);
            CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date_type
                ON transactions(scope, owner_user_id, date_g, ttype);
            CREATE INDEX IF NOT EXISTS idx_tx_scope_owner_date_type_cat
                ON transactions(scope, owner_user_id, date_g, ttype, category);
            COMMIT;
            """
        )

    if "personal_in" not in _table_sql(conn, "categories"):
        conn.executescript(
            """
            BEGIN;
            CREATE TABLE categories_v2(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
                owner_user_id INTEGER NOT NULL,
                grp TEXT NOT NULL CHECK(grp IN ('work_in','work_out','personal_in','personal_out')),
                name TEXT NOT NULL,
                is_locked INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO categories_v2(id, scope, owner_user_id, grp, name, is_locked)
            SELECT id, scope, owner_user_id, grp, name, is_locked FROM categories;
            DROP TABLE categories;
            ALTER TABLE categories_v2 RENAME TO categories;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_cat_scope_owner_grp_name
                ON categories(scope, owner_user_id, grp, name);
            COMMIT;
            """
        )

def _m3_loans_recurring(conn: sqlite3.Connection) -> None:
    """Add the loan and recurring-transaction tables, and link payments to loans."""
    # The tables themselves come from BASE_SCHEMA (IF NOT EXISTS); only the new
    # column on an existing transactions table needs doing here.
    if "loan_id" not in _columns(conn, "transactions"):
        conn.execute("ALTER TABLE transactions ADD COLUMN loan_id INTEGER NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_loan ON transactions(loan_id)")

def _m4_budgets_debts_receipts(conn: sqlite3.Connection) -> None:
    """Add budgets and debts (both come from BASE_SCHEMA) plus receipt storage."""
    if "receipt_file_id" not in _columns(conn, "transactions"):
        conn.execute("ALTER TABLE transactions ADD COLUMN receipt_file_id TEXT NULL")

MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (2, "personal income type", _m2_personal_income),
    (3, "loans and recurring transactions", _m3_loans_recurring),
    (4, "budgets, debts and receipts", _m4_budgets_debts_receipts),
]

def _detect_version(conn: sqlite3.Connection) -> int:
    # No transactions table yet means a brand-new file: BASE_SCHEMA will create
    # it at the current version, so there is nothing to migrate.
    if not _table_exists(conn, "transactions"):
        return SCHEMA_VERSION
    if not _table_exists(conn, "settings"):
        return 1

    row = conn.execute("SELECT v FROM settings WHERE k='schema_version'").fetchone()
    if not row:
        return 1  # pre-versioning database
    try:
        return int(row["v"])
    except (TypeError, ValueError):
        return 1

def init_db() -> None:
    # A restore swaps the file underneath us, so drop anything cached from it.
    _SETTINGS_CACHE.clear()
    _INSTALLMENT_READY.clear()

    with db() as conn:
        current = _detect_version(conn)

    # Never migrate without a copy to fall back to.
    if current < SCHEMA_VERSION and os.path.exists(DB_PATH):
        stamp = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
        path = save_disk_backup(f"kasbbook_premigration_v{current}_{stamp}.db", make_backup_bytes())
        logger.info("Schema %s -> %s; pre-migration snapshot: %s", current, SCHEMA_VERSION, path)

    with db() as conn:
        # Migrations first: BASE_SCHEMA describes the finished shape, and some of
        # it (the loan_id index) cannot be created until a migration has widened
        # the old table. Applying it afterwards makes it a reconciliation pass
        # that is correct for both a fresh file and an upgraded one.
        for version, description, migrate in MIGRATIONS:
            if current < version:
                logger.info("Applying migration %s (%s)", version, description)
                migrate(conn)
                current = version

        conn.executescript(BASE_SCHEMA)

        conn.execute(
            "INSERT INTO settings(k,v) VALUES('schema_version',?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (str(SCHEMA_VERSION),),
        )

        def _ensure_setting(key: str, default: str) -> None:
            if conn.execute("SELECT 1 FROM settings WHERE k=?", (key,)).fetchone() is None:
                conn.execute("INSERT INTO settings(k,v) VALUES(?,?)", (key, default))

        _ensure_setting("access_mode", ACCESS_ADMIN_ONLY)
        _ensure_setting("share_enabled", "0")
        _ensure_setting("currency", DEFAULT_CURRENCY)

        # Proactive notifications
        _ensure_setting("digest_enabled", "0")            # 0/1
        _ensure_setting("digest_hour", "21")              # local hour, 0-23
        _ensure_setting("loan_reminder_enabled", "0")     # 0/1
        _ensure_setting("loan_reminder_days", "3")        # days of warning

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

# =========================
# Input parsing
# =========================
# Persian and Arabic-Indic digits are what people actually type on a phone
# keyboard, so every numeric field normalises them before doing anything else.
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def to_ascii_digits(s: str) -> str:
    return (s or "").translate(_DIGIT_MAP)

# Longest first: "میلیون" must win over "م".
_AMOUNT_UNITS: List[Tuple[str, int]] = [
    ("میلیارد", 1_000_000_000),
    ("میلیون", 1_000_000),
    ("هزار", 1_000),
    ("b", 1_000_000_000),
    ("m", 1_000_000),
    ("k", 1_000),
    ("م", 1_000_000),
    ("ک", 1_000),
    ("ه", 1_000),
]

def parse_amount(s: str) -> Optional[int]:
    """Parse an amount the way a person types it: ۲۵۰ک, 1.2m, 250,000, 2 میلیون."""
    t = to_ascii_digits(s or "").strip()
    if not t:
        return None

    for junk in (",", "،", "٬", " ", "‌", "٬"):
        t = t.replace(junk, "")
    t = t.replace("٫", ".").replace("/", ".")

    multiplier = 1
    low = t.lower()
    for suffix, factor in _AMOUNT_UNITS:
        # len check keeps a bare "k" from parsing as 1000
        if low.endswith(suffix) and len(low) > len(suffix):
            t = t[: len(t) - len(suffix)]
            multiplier = factor
            break

    if not re.fullmatch(r"\d+(\.\d+)?", t):
        return None

    return int(round(float(t) * multiplier))

def parse_date_any(s: str) -> Optional[str]:
    """
    Accept any reasonable way of writing a date and return Gregorian ISO.

    Jalali or Gregorian is decided by the year, not the separator: no Gregorian
    date the bot will ever see falls below 1500, and no Jalali one reaches it.
    """
    t = to_ascii_digits(s or "").strip()
    if not t:
        return None

    low = t.lower()
    today = datetime.now(TZ).date()
    if low in ("امروز", "today"):
        return today.strftime("%Y-%m-%d")
    if low in ("دیروز", "yesterday"):
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    if low in ("فردا", "tomorrow"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if not m:
        return None

    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))

    if y >= 1500:
        try:
            date(y, mo, d)
        except ValueError:
            return None
        return f"{y:04d}-{mo:02d}-{d:02d}"

    try:
        return jdatetime.date(y, mo, d).togregorian().strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None

def now_ts() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def today_g() -> str:
    return datetime.now(TZ).date().strftime("%Y-%m-%d")

def g_to_j(g_yyyy_mm_dd: str) -> str:
    y, m, d = map(int, g_yyyy_mm_dd.split("-"))
    jd = jdatetime.date.fromgregorian(date=date(y, m, d))
    return f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}"

# Both entry points accept either calendar; the labels are only a hint about
# which one the user probably meant to type.
def parse_gregorian(s: str) -> Optional[str]:
    return parse_date_any(s)

def parse_jalali_to_g(s: str) -> Optional[str]:
    return parse_date_any(s)

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

def within_quota(scope: str, owner: int, kind: str) -> Tuple[bool, str]:
    """
    Guard rails for public mode, where anyone who finds the bot can write to it.

    Admin-only mode is unrestricted: those users were added on purpose.
    """
    try:
        if get_setting("access_mode") != ACCESS_PUBLIC:
            return (True, "")
    except Exception:
        return (True, "")

    with db() as conn:
        if kind == "tx":
            used = int(conn.execute(
                "SELECT COUNT(*) AS c FROM transactions "
                "WHERE scope=? AND owner_user_id=? AND date_g=?",
                (scope, owner, today_g()),
            ).fetchone()["c"])
            if used >= PUBLIC_MAX_TX_PER_DAY:
                return (False, f"سقف روزانه {PUBLIC_MAX_TX_PER_DAY} تراکنش پر شده است.")

        elif kind == "cat":
            used = int(conn.execute(
                "SELECT COUNT(*) AS c FROM categories WHERE scope=? AND owner_user_id=?",
                (scope, owner),
            ).fetchone()["c"])
            if used >= PUBLIC_MAX_CATEGORIES:
                return (False, f"سقف {PUBLIC_MAX_CATEGORIES} دسته پر شده است.")

    return (True, "")

def find_categories_by_name(scope: str, owner: int, name: str) -> List[sqlite3.Row]:
    """Every category with this exact name, across all four groups."""
    cleaned = (name or "").strip()
    if not cleaned:
        return []
    with db() as conn:
        return list(conn.execute(
            """
            SELECT id, grp, name FROM categories
            WHERE scope=? AND owner_user_id=? AND name=? COLLATE NOCASE
            ORDER BY grp
            """,
            (scope, owner, cleaned),
        ).fetchall())

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
    """Bare grouped number — for buttons, CSV and anywhere a unit would not fit."""
    return f"{int(n):,}"

def currency() -> str:
    try:
        return get_setting("currency") or DEFAULT_CURRENCY
    except Exception:
        return DEFAULT_CURRENCY

def fmt_money(n: int) -> str:
    """Amount with the configured unit — for anything a person reads as money."""
    return f"{fmt_num(n)} {currency()}"

def currency_kb() -> InlineKeyboardMarkup:
    cur = currency()
    rows = []
    for name in ("تومان", "ریال"):
        mark = " ✅" if cur == name else ""
        rows.append([(f"{name}{mark}", f"{CB_CU}:set:{name}")])
    rows.append([("✏️ واحد دلخواه", f"{CB_CU}:custom")])
    rows.append([("⬅️ بازگشت", f"{CB_M}:st")])
    return ikb(rows)

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
    rows = [
        [("🧩 مدیریت دسته‌ها", f"{CB_ST}:cats")],
        [("📄 اقساط و وام‌ها", f"{CB_LN}:panel")],
        [("🤝 طلب و بدهی", f"{CB_DT}:panel")],
        [("🎯 بودجه‌ها", f"{CB_BG}:panel")],
        [("🔁 تراکنش‌های تکرارشونده", f"{CB_RC}:panel")],
        [("🔔 یادآورها", f"{CB_RM}:panel")],
        [("💱 واحد پول", f"{CB_ST}:cur")],
    ]
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
            [("💵 درآمد شخصی", f"{CB_CT}:grp:personal_in")],
            [("👤 هزینه شخصی", f"{CB_CT}:grp:personal_out")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )

def grp_label(grp: str) -> str:
    return {
        "work_in": "💰 درآمد کاری",
        "work_out": "🏢 هزینه کاری",
        "personal_in": "💵 درآمد شخصی",
        "personal_out": "👤 هزینه شخصی",
    }.get(grp, grp)

def ttype_label(ttype: str) -> str:
    return {
        "work_in": "درآمد کاری",
        "work_out": "هزینه کاری",
        "personal_in": "درآمد شخصی",
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

CU_CUSTOM = 0
SR_QUERY = 0
RG_START, RG_END = range(2)
LN_TITLE, LN_AMOUNT, LN_COUNT, LN_START = range(4)
BG_PICK, BG_CATNAME, BG_AMOUNT = range(3)
DT_PERSON, DT_DIR, DT_AMOUNT, DT_NOTE, DT_DUE = range(5)
RM_HOUR, RM_DAYS = range(2)
RCP_WAIT = 0
RC_TTYPE, RC_CAT, RC_AMOUNT, RC_DESC, RC_PERIOD, RC_START = range(6)

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
    if action == "cur":
        await safe_edit(q, rtl(f"💱 واحد پول\n\nواحد فعلی: {currency()}"), reply_markup=currency_kb())
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
    if grp not in ("work_in", "work_out", "personal_in", "personal_out"):
        await update.effective_chat.send_message(rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)

    ok, why = within_quota(scope, owner, "cat")
    if not ok:
        await update.effective_chat.send_message(rtl(f"⛔ {why}"))
        context.user_data.clear()
        return ConversationHandler.END

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
            [("💵 درآمد شخصی", f"{CB_TX}:tt:personal_in")],
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
    if ttype not in ("work_in", "work_out", "personal_in", "personal_out"):
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
    if ttype not in ("work_in", "work_out", "personal_in", "personal_out"):
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
        if ttype not in ("work_in", "work_out", "personal_in", "personal_out") or not gdate:
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
    if ttype not in ("work_in", "work_out", "personal_in", "personal_out") or not gdate:
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
    if ttype not in ("work_in", "work_out", "personal_in", "personal_out") or not gdate:
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

    if ttype not in ("work_in", "work_out", "personal_in", "personal_out") or not date_g_ or not category or amount is None:
        await update.effective_chat.send_message(rtl("خطا: اطلاعات ناقص است."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)

    ok, why = within_quota(scope, owner, "tx")
    if not ok:
        await update.effective_chat.send_message(rtl(f"⛔ {why}"))
        context.user_data.clear()
        return ConversationHandler.END

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

    done = "✅ ثبت شد."
    warning = budget_warning(scope, owner, ttype, category, date_g_)
    if warning:
        done += f"\n\n{warning}"

    await update.effective_chat.send_message(rtl(done), reply_markup=tx_menu())
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
def daily_list_text(scope: str, owner: int, gdate: str) -> str:
    ensure_installment(scope, owner)
    s = sums_for_range(scope, owner, gdate, gdate, inclusive_end=True)

    lines = [
        f"📅 {gdate}  |  {g_to_j(gdate)}",
        "",
        "📊 گزارش روز",
        f"💰 درآمد کاری: {fmt_money(s['income'])}",
        f"🏢 هزینه کاری: {fmt_money(s['work_out'])}",
        f"➖ خالص کاری: {fmt_money(s['net'])}",
    ]
    if s["personal_in"]:
        lines.append(f"💵 درآمد شخصی: {fmt_money(s['personal_in'])}")
    lines += [
        f"📄 قسط پرداختی: {fmt_money(s['installment'])}",
        f"👤 هزینه شخصی (بدون قسط): {fmt_money(s['personal'])}",
        f"💾 پس‌انداز عملیاتی: {fmt_money(s['savings_operational'])}",
        f"💾 پس‌انداز نهایی: {fmt_money(s['savings_final'])}",
    ]
    return rtl("\n".join(lines))

def _short_add_labels() -> Tuple[str, ...]:
    return ("درآمد کاری", "هزینه کاری", "درآمد شخصی", "هزینه شخصی")

def _section_title(ttype: str) -> str:
    return {
        "work_in": "— لیست درآمد کاری —",
        "work_out": "— لیست هزینه کاری —",
        "personal_in": "— لیست درآمد شخصی —",
        "personal_out": "— لیست هزینه های شخصی —",
    }[ttype]

SECTION_ORDER: Tuple[str, ...] = ("work_in", "work_out", "personal_in", "personal_out")

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

def normalize_pages(raw) -> Tuple[int, ...]:
    """Coerce callback data / stored state into one page number per section."""
    n = len(SECTION_ORDER)
    try:
        p = [max(0, int(x)) for x in raw]
    except (TypeError, ValueError):
        return tuple([0] * n)
    p = (p + [0] * n)[:n]
    return tuple(p)

def current_pages(context: ContextTypes.DEFAULT_TYPE) -> Tuple[int, ...]:
    """
    Which page of the daily list the user is looking at.

    Kept in chat_data rather than user_data, because the edit conversations call
    user_data.clear() mid-flow and would otherwise reset the list to page 1.
    """
    return normalize_pages(context.chat_data.get("dl_pages", ()))

def remember_pages(context: ContextTypes.DEFAULT_TYPE, pages) -> Tuple[int, ...]:
    p = normalize_pages(pages)
    context.chat_data["dl_pages"] = p
    return p

def daily_back_cb(gdate: str, pages) -> str:
    """Back-to-daily-list callback that returns to the page the user was on."""
    p = normalize_pages(pages)
    return f"{CB_DL}:page:{gdate}:" + ":".join(str(x) for x in p)

def daily_rows_kb(
    scope: str,
    owner: int,
    gdate: str,
    pages: Tuple[int, ...] = (),
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
        return f"{CB_DL}:page:{gdate}:" + ":".join(str(x) for x in nxt)

    rows: List[List[InlineKeyboardButton]] = []

    labels = _short_add_labels()
    rows.append(
        [
            InlineKeyboardButton(labels[i], callback_data=f"{CB_DL}:add:{gdate}:{ttype}")
            for i, ttype in enumerate(SECTION_ORDER)
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
            pages = remember_pages(context, ())
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
        pages = remember_pages(context, data[3:] if act == "page" else ())
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

def tx_view_kb(
    gdate: str,
    tx_id: int,
    back_cb: Optional[str] = None,
    has_receipt: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [("🏷 ویرایش دسته", f"{CB_DTX}:cat:{gdate}:{tx_id}")],
        [("💵 ویرایش مبلغ", f"{CB_DTX}:amt:{gdate}:{tx_id}")],
        [("📝 ویرایش توضیحات", f"{CB_DTX}:desc:{gdate}:{tx_id}")],
        [("📅 ویرایش تاریخ", f"{CB_DTX}:date:{gdate}:{tx_id}")],
    ]
    if has_receipt:
        rows.append([
            ("🧾 دیدن رسید", f"{CB_DTX}:rcpv:{gdate}:{tx_id}"),
            ("❌ حذف رسید", f"{CB_DTX}:rcpd:{gdate}:{tx_id}"),
        ])
    else:
        rows.append([("🧾 افزودن رسید", f"{CB_DTX}:rcp:{gdate}:{tx_id}")])

    rows.append([("🗑 حذف", f"{CB_DTX}:del:{gdate}:{tx_id}")])
    rows.append([("⬅️ بازگشت", back_cb or f"{CB_DL}:show:{gdate}")])
    return ikb(rows)

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

    has_receipt = bool(tx["receipt_file_id"])

    if act == "open":
        await safe_edit(q, tx_detail_text(tx), reply_markup=tx_view_kb(gdate, tx_id, back_cb, has_receipt))
        return ConversationHandler.END

    if act == "rcpv":
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=str(tx["receipt_file_id"]),
                caption=rtl(f"🧾 رسید — {tx['category']} | {fmt_money(int(tx['amount']))}"),
            )
        except Exception:
            # It may have been sent as a file rather than a photo.
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=str(tx["receipt_file_id"]),
                caption=rtl("🧾 رسید"),
            )
        return ConversationHandler.END

    if act == "rcpd":
        async with DB_LOCK:
            set_receipt(scope, owner, tx_id, None)
        tx2 = get_tx(scope, owner, tx_id)
        await safe_edit(q, tx_detail_text(tx2, "🧾 رسید حذف شد."),
                        reply_markup=tx_view_kb(gdate, tx_id, back_cb, False))
        return ConversationHandler.END

    if act == "rcp":
        context.user_data.clear()
        context.user_data["receipt_tx_id"] = tx_id
        context.user_data["receipt_gdate"] = gdate
        await safe_edit(q, rtl(
            "🧾 عکس یا فایل رسید را بفرست.\n\nبرای انصراف /cancel بزن."
        ))
        return RCP_WAIT

    if act == "undo":
        snap = context.chat_data.get("deleted_tx")
        if not snap or int(snap.get("id", -1)) != tx_id:
            await q.answer("چیزی برای بازگرداندن نیست.", show_alert=True)
            return ConversationHandler.END

        async with DB_LOCK:
            restore_tx(snap)
        context.chat_data.pop("deleted_tx", None)

        await safe_edit(q,
            daily_list_text(scope, owner, gdate),
            reply_markup=daily_rows_kb(scope, owner, gdate, current_pages(context)),
        )
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
        # Keep a copy so the delete can be taken back — people mis-tap.
        context.chat_data["deleted_tx"] = snapshot_tx(tx)

        async with DB_LOCK:
            with db() as conn:
                conn.execute(
                    "DELETE FROM transactions WHERE id=? AND scope=? AND owner_user_id=?",
                    (tx_id, scope, owner),
                )
                conn.commit()

        pages = current_pages(context)
        base = daily_rows_kb(scope, owner, gdate, pages)
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("↩️ بازگرداندن حذف", callback_data=f"{CB_DTX}:undo:{gdate}:{tx_id}")]]
            + list(base.inline_keyboard)
        )
        await safe_edit(q, daily_list_text(scope, owner, gdate), reply_markup=kb)
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
                        reply_markup=tx_view_kb(gdate, tx_id, back_cb, has_receipt),
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
            reply_markup=tx_view_kb(gdate, tx_id, back_cb, has_receipt),
        )
        return ConversationHandler.END

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=tx_view_kb(gdate, tx_id, back_cb, has_receipt))
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
    pages = remember_pages(context, ())
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
    inclusive_end: bool = False,
) -> Dict[str, int]:
    """Totals for a period; omit both bounds for an all-time total."""
    ensure_installment(scope, owner)

    where = "scope=? AND owner_user_id=?"
    params: List = [INSTALLMENT_NAME, INSTALLMENT_NAME, scope, owner]
    if start_g is not None:
        where += " AND date_g>=?"
        params.append(start_g)
    if end_g_exclusive is not None:
        where += " AND date_g<=?" if inclusive_end else " AND date_g<?"
        params.append(end_g_exclusive)

    with db() as conn:
        row = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN ttype='work_in' THEN amount ELSE 0 END),0) AS income,
                COALESCE(SUM(CASE WHEN ttype='work_out' THEN amount ELSE 0 END),0) AS work_out,
                COALESCE(SUM(CASE WHEN ttype='personal_in' THEN amount ELSE 0 END),0) AS personal_in,
                COALESCE(SUM(CASE WHEN ttype='personal_out' AND category=? THEN amount ELSE 0 END),0) AS installment,
                COALESCE(SUM(CASE WHEN ttype='personal_out' AND category<>? THEN amount ELSE 0 END),0) AS personal
            FROM transactions
            WHERE {where}
            """,
            tuple(params),
        ).fetchone()

    income = int(row["income"])
    work_out = int(row["work_out"])
    personal_in = int(row["personal_in"])
    installment = int(row["installment"])
    personal = int(row["personal"])

    net = income - work_out
    # Personal income counts towards what is left over, but not towards the
    # health of the business itself — so it lands here, not in `net`.
    savings_operational = net + personal_in - personal
    savings_final = savings_operational - installment

    return {
        "income": income,
        "work_out": work_out,
        "net": net,
        "personal_in": personal_in,
        "installment": installment,
        "personal": personal,
        "savings_operational": savings_operational,
        "savings_final": savings_final,
    }

def count_transactions(
    scope: str,
    owner: int,
    start_g: Optional[str] = None,
    end_g_exclusive: Optional[str] = None,
) -> int:
    where = "scope=? AND owner_user_id=?"
    params: List = [scope, owner]
    if start_g is not None:
        where += " AND date_g>=?"
        params.append(start_g)
    if end_g_exclusive is not None:
        where += " AND date_g<?"
        params.append(end_g_exclusive)

    with db() as conn:
        return int(conn.execute(
            f"SELECT COUNT(*) AS c FROM transactions WHERE {where}", tuple(params)
        ).fetchone()["c"])

def sums_all(scope: str, owner: int) -> Dict[str, int]:
    return sums_for_range(scope, owner)

def report_lines(title: str, s: Dict[str, int], extra: Optional[str] = None) -> str:
    lines = [
        title,
        "",
        f"💰 درآمد کاری: {fmt_money(s['income'])}",
        f"🏢 هزینه کاری: {fmt_money(s['work_out'])}",
        f"➖ خالص کاری: {fmt_money(s['net'])}",
        "",
    ]
    if s.get("personal_in"):
        lines.append(f"💵 درآمد شخصی: {fmt_money(s['personal_in'])}")
    lines += [
        f"📄 قسط پرداختی: {fmt_money(s['installment'])}",
        f"👤 هزینه شخصی (بدون قسط): {fmt_money(s['personal'])}",
        "",
        f"💾 پس‌انداز عملیاتی: {fmt_money(s['savings_operational'])}",
        f"💾 پس‌انداز نهایی: {fmt_money(s['savings_final'])}",
    ]
    if extra:
        lines += ["", extra]
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

    if kind == "r" and len(parts) >= 3:
        # The spec carries an inclusive end date because that is what the user
        # typed; SQL wants it exclusive, so it is shifted here.
        s_g, e_g = parts[1], parts[2]
        try:
            e_ex = (datetime.strptime(e_g, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            return ("a", "کلی", None, None)
        return (f"r:{s_g}:{e_g}", f"{g_to_j(s_g)} تا {g_to_j(e_g)}", s_g, e_ex)

    return ("a", "کلی", None, None)

def period_extra_kb(spec: str) -> List[List[tuple]]:
    return [
        [("🏷 تفکیک دسته‌ها", f"{CB_RP}:bd:{spec}")],
        [("📥 خروجی CSV", f"{CB_RP}:csv:{spec}")],
    ]

def report_root_kb(years: List[int]) -> InlineKeyboardMarkup:
    rows: List[List[tuple]] = period_extra_kb("a")
    rows.append([("🔎 جست‌وجو", f"{CB_SR}:new"), ("📆 بازهٔ دلخواه", f"{CB_RP}:range")])
    rows.append([("📉 روند ماهانه", f"{CB_TR}:show:savings_final:6")])

    this_s, this_e = week_range_g(0)
    last_s, last_e = week_range_g(1)
    rows.append([
        ("🗓 این هفته", f"{CB_RP}:r:{this_s}:{this_e}"),
        ("🗓 هفتهٔ گذشته", f"{CB_RP}:r:{last_s}:{last_e}"),
    ])

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

def range_report_kb(s_g: str, e_g: str) -> InlineKeyboardMarkup:
    rows: List[List[tuple]] = period_extra_kb(f"r:{s_g}:{e_g}")
    rows.append([("📆 بازهٔ دیگر", f"{CB_RP}:range")])
    rows.append([("⬅️ بازگشت", f"{CB_RP}:root")])
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
        extra = comparison_lines(scope, owner, f"y:{jy}")
        await safe_edit(q, report_lines(f"📊 گزارش سال {jy}", s, extra), reply_markup=report_year_kb(jy))
        return

    if act == "m":
        jy, jm = int(parts[2]), int(parts[3])
        start, end = j_month_range_g(jy, jm)
        s = sums_for_range(scope, owner, start, end)
        title = f"📊 گزارش {jmonth_name(jm)} {jy}"
        extra = comparison_lines(scope, owner, f"m:{jy}:{jm:02d}")
        await safe_edit(q, report_lines(title, s, extra), reply_markup=report_month_kb(jy, jm))
        return

    if act == "r":
        s_g, e_g = parts[2], parts[3]
        _, title, start, end = parse_period(["r", s_g, e_g])
        s = sums_for_range(scope, owner, start, end)
        await safe_edit(q, report_lines(f"📊 گزارش {title}", s), reply_markup=range_report_kb(s_g, e_g))
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
# Weeks
# =========================
def week_range_g(offset: int = 0) -> Tuple[str, str]:
    """Inclusive [start, end] of a week, counting from Saturday like the Iranian week."""
    today = datetime.now(TZ).date()
    since_saturday = (today.weekday() + 2) % 7
    start = today - timedelta(days=since_saturday + 7 * offset)
    return (start.strftime("%Y-%m-%d"), (start + timedelta(days=6)).strftime("%Y-%m-%d"))

# =========================
# Budgets
# =========================
def set_budget(scope: str, owner: int, kind: str, target: str, amount: int) -> None:
    """One budget per target: setting it again updates the limit."""
    with db() as conn:
        conn.execute(
            """
            INSERT INTO budgets(scope, owner_user_id, kind, target, amount, created_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(scope, owner_user_id, kind, target)
            DO UPDATE SET amount=excluded.amount
            """,
            (scope, owner, kind, target.strip(), int(amount), now_ts()),
        )

def delete_budget(scope: str, owner: int, budget_id: int) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM budgets WHERE id=? AND scope=? AND owner_user_id=?",
            (budget_id, scope, owner),
        )

def list_budgets(scope: str, owner: int) -> List[sqlite3.Row]:
    with db() as conn:
        return list(conn.execute(
            "SELECT * FROM budgets WHERE scope=? AND owner_user_id=? ORDER BY kind, target COLLATE NOCASE",
            (scope, owner),
        ).fetchall())

def budget_status(scope: str, owner: int, jy: int, jm: int) -> List[Dict]:
    """How much of each budget the given Jalali month has used."""
    budgets = list_budgets(scope, owner)
    if not budgets:
        return []

    start, end = j_month_range_g(jy, jm)
    out: List[Dict] = []

    with db() as conn:
        for b in budgets:
            kind = str(b["kind"])
            target = str(b["target"])
            column = "ttype" if kind == "group" else "category"
            row = conn.execute(
                f"""
                SELECT COALESCE(SUM(amount),0) AS spent
                FROM transactions
                WHERE scope=? AND owner_user_id=? AND date_g>=? AND date_g<? AND {column}=?
                """,
                (scope, owner, start, end, target),
            ).fetchone()

            limit = int(b["amount"])
            spent = int(row["spent"])
            out.append({
                "id": int(b["id"]),
                "kind": kind,
                "target": target,
                "label": grp_label(target) if kind == "group" else target,
                "limit": limit,
                "spent": spent,
                "remaining": limit - spent,
                "percent": round(spent * 100 / limit) if limit else 0,
            })

    return out

def _bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, round(percent * width / 100)))
    return "█" * filled + "░" * (width - filled)

def budgets_text(
    scope: str,
    owner: int,
    jy: Optional[int] = None,
    jm: Optional[int] = None,
    page: int = 0,
) -> str:
    if jy is None or jm is None:
        jy, jm, _ = g_to_j_parts(today_g())

    rows = budget_status(scope, owner, jy, jm)
    if not rows:
        return rtl(
            "🎯 بودجه‌ها\n\n"
            "هنوز بودجه‌ای تعیین نشده.\n"
            "برای یک دسته یا کل یک گروه سقف ماهانه بگذار تا ربات هشدار بدهد."
        )

    page = max(0, min(page, max(0, (len(rows) - 1) // BUDGET_PAGE_SIZE)))
    window = rows[page * BUDGET_PAGE_SIZE:(page + 1) * BUDGET_PAGE_SIZE]

    lines = [f"🎯 بودجه‌های {jmonth_name(jm)} {jy}", ""]
    for r in window:
        flag = "⛔" if r["spent"] > r["limit"] else ("⚠️" if r["percent"] >= 80 else "✅")
        lines.append(
            f"{flag} {r['label']}\n"
            f"  {_bar(r['percent'])} {r['percent']}%\n"
            f"  {fmt_money(r['spent'])} از {fmt_money(r['limit'])}"
        )
        if r["remaining"] < 0:
            lines.append(f"  بیش از سقف: {fmt_money(-r['remaining'])}")

    over = [r for r in rows if r["spent"] > r["limit"]]
    if over:
        lines += ["", f"⛔ {len(over)} بودجه از سقف رد شده."]
    return rtl("\n".join(lines))

def budgets_kb(scope: str, owner: int, page: int = 0) -> InlineKeyboardMarkup:
    budgets = list_budgets(scope, owner)
    page = max(0, min(page, max(0, (len(budgets) - 1) // BUDGET_PAGE_SIZE)))
    window = budgets[page * BUDGET_PAGE_SIZE:(page + 1) * BUDGET_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("➕ تعیین بودجه", callback_data=f"{CB_BG}:add")]
    ]

    for b in window:
        label = grp_label(str(b["target"])) if str(b["kind"]) == "group" else str(b["target"])
        rows.append([
            InlineKeyboardButton(label[:24], callback_data=f"{CB_BG}:noop"),
            InlineKeyboardButton("🗑", callback_data=f"{CB_BG}:del:{b['id']}"),
        ])

    nav = page_nav_row(f"{CB_BG}:page:", page, len(budgets), BUDGET_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_M}:st")])
    return InlineKeyboardMarkup(rows)

def budget_warning(scope: str, owner: int, ttype: str, category: str, gdate: str) -> Optional[str]:
    """A one-line nudge when a just-recorded expense crosses a budget."""
    jy, jm, _ = g_to_j_parts(gdate)
    for r in budget_status(scope, owner, jy, jm):
        hit = (r["kind"] == "group" and r["target"] == ttype) or \
              (r["kind"] == "category" and r["target"] == category)
        if not hit:
            continue
        if r["spent"] > r["limit"]:
            return f"⛔ بودجهٔ «{r['label']}» {fmt_money(r['spent'] - r['limit'])} رد شد."
        if r["percent"] >= 80:
            return f"⚠️ {r['percent']}% از بودجهٔ «{r['label']}» مصرف شده."
    return None

# =========================
# Debts and receivables
# =========================
DEBT_LABELS = {"owed_to_me": "طلب من", "i_owe": "بدهی من"}

def create_debt(
    scope: str,
    owner: int,
    person: str,
    direction: str,
    amount: int,
    note: Optional[str],
    due_date_g: Optional[str],
) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO debts(scope, owner_user_id, person, direction, amount,
                              note, due_date_g, settled_at, created_at)
            VALUES(?,?,?,?,?,?,?,NULL,?)
            """,
            (scope, owner, person.strip(), direction, int(amount),
             (note or None), due_date_g, now_ts()),
        )
        return int(cur.lastrowid)

def settle_debt(scope: str, owner: int, debt_id: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE debts SET settled_at=? WHERE id=? AND scope=? AND owner_user_id=?",
            (now_ts(), debt_id, scope, owner),
        )

def delete_debt(scope: str, owner: int, debt_id: int) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM debts WHERE id=? AND scope=? AND owner_user_id=?",
            (debt_id, scope, owner),
        )

def list_debts(scope: str, owner: int, include_settled: bool = False) -> List[sqlite3.Row]:
    where = "scope=? AND owner_user_id=?"
    if not include_settled:
        where += " AND settled_at IS NULL"
    with db() as conn:
        return list(conn.execute(
            f"SELECT * FROM debts WHERE {where} ORDER BY settled_at IS NOT NULL, due_date_g IS NULL, due_date_g, id DESC",
            (scope, owner),
        ).fetchall())

def debt_totals(scope: str, owner: int) -> Dict[str, int]:
    """Only open debts count: a settled one is history, not a position."""
    with db() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN direction='owed_to_me' THEN amount ELSE 0 END),0) AS owed_to_me,
                COALESCE(SUM(CASE WHEN direction='i_owe' THEN amount ELSE 0 END),0) AS i_owe
            FROM debts
            WHERE scope=? AND owner_user_id=? AND settled_at IS NULL
            """,
            (scope, owner),
        ).fetchone()

    owed = int(row["owed_to_me"])
    mine = int(row["i_owe"])
    return {"owed_to_me": owed, "i_owe": mine, "net": owed - mine}

def debts_text(
    scope: str,
    owner: int,
    page: int = 0,
    include_settled: bool = False,
) -> str:
    debts = list_debts(scope, owner, include_settled)
    totals = debt_totals(scope, owner)

    if not debts:
        return rtl(
            "🤝 طلب و بدهی\n\n"
            "چیزی ثبت نشده.\n"
            "نسیه‌ها و قرض‌ها را اینجا نگه دار — روی گزارش‌های درآمد اثر نمی‌گذارند."
        )

    page = max(0, min(page, max(0, (len(debts) - 1) // DEBT_PAGE_SIZE)))
    window = debts[page * DEBT_PAGE_SIZE:(page + 1) * DEBT_PAGE_SIZE]

    lines = [
        "🤝 طلب و بدهی",
        "",
        f"📥 طلب من: {fmt_money(totals['owed_to_me'])}",
        f"📤 بدهی من: {fmt_money(totals['i_owe'])}",
        f"⚖️ خالص: {fmt_money(totals['net'])}",
        "",
    ]
    for d in window:
        mark = "✅ " if d["settled_at"] else ""
        arrow = "📥" if str(d["direction"]) == "owed_to_me" else "📤"
        line = f"{mark}{arrow} {d['person']}: {fmt_money(int(d['amount']))}"
        if d["due_date_g"]:
            line += f"\n  سررسید: {g_to_j(str(d['due_date_g']))}"
        if d["note"]:
            line += f"\n  {str(d['note'])[:40]}"
        lines.append(line)

    return rtl("\n".join(lines))

def debts_kb(scope: str, owner: int, page: int = 0) -> InlineKeyboardMarkup:
    debts = list_debts(scope, owner)
    page = max(0, min(page, max(0, (len(debts) - 1) // DEBT_PAGE_SIZE)))
    window = debts[page * DEBT_PAGE_SIZE:(page + 1) * DEBT_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("➕ ثبت طلب/بدهی", callback_data=f"{CB_DT}:add")]
    ]

    for d in window:
        rows.append([
            InlineKeyboardButton(str(d["person"])[:20], callback_data=f"{CB_DT}:noop"),
            InlineKeyboardButton("✅ تسویه", callback_data=f"{CB_DT}:settle:{d['id']}"),
            InlineKeyboardButton("🗑", callback_data=f"{CB_DT}:del:{d['id']}"),
        ])

    nav = page_nav_row(f"{CB_DT}:page:", page, len(debts), DEBT_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🗂 شامل تسویه‌شده‌ها", callback_data=f"{CB_DT}:all")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_M}:st")])
    return InlineKeyboardMarkup(rows)

# =========================
# Monthly trend
# =========================
TREND_METRICS = {
    "income": "درآمد کاری",
    "work_out": "هزینه کاری",
    "net": "خالص کاری",
    "savings_final": "پس‌انداز نهایی",
}

def monthly_trend(scope: str, owner: int, months: int, metric: str) -> List[Tuple[str, int]]:
    """The last N Jalali months of one metric, oldest first."""
    jy, jm, _ = g_to_j_parts(today_g())
    out: List[Tuple[str, int]] = []

    for back in range(months - 1, -1, -1):
        total = (jy * 12 + (jm - 1)) - back
        y, m = divmod(total, 12)
        m += 1
        s = sums_for_range(scope, owner, *j_month_range_g(y, m))
        out.append((f"{jmonth_name(m)} {y}", int(s.get(metric, 0))))

    return out

def trend_text(scope: str, owner: int, metric: str, months: int) -> str:
    data = monthly_trend(scope, owner, months, metric)
    label = TREND_METRICS.get(metric, metric)

    peak = max((abs(v) for _, v in data), default=0)
    lines = [f"📉 روند {label} — {months} ماه اخیر", ""]

    if not peak:
        lines.append("در این بازه عددی ثبت نشده.")
        return rtl("\n".join(lines))

    for name, value in data:
        width = max(1, round(abs(value) * 12 / peak)) if value else 0
        bar = "█" * width if width else "▏"
        sign = "−" if value < 0 else ""
        lines.append(f"{name}: {sign}{fmt_num(abs(value))}\n{bar}")

    return rtl("\n".join(lines))

def trend_kb(metric: str, months: int) -> InlineKeyboardMarkup:
    rows: List[List[tuple]] = []

    buf: List[tuple] = []
    for key, name in TREND_METRICS.items():
        mark = " ✅" if key == metric else ""
        buf.append((f"{name}{mark}", f"{CB_TR}:show:{key}:{months}"))
        if len(buf) == 2:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)

    rows.append([
        (f"۶ ماه{' ✅' if months == 6 else ''}", f"{CB_TR}:show:{metric}:6"),
        (f"۱۲ ماه{' ✅' if months == 12 else ''}", f"{CB_TR}:show:{metric}:12"),
    ])
    rows.append([("⬅️ بازگشت", f"{CB_RP}:root")])
    return ikb(rows)

# =========================
# Receipts
# =========================
def set_receipt(scope: str, owner: int, tx_id: int, file_id: Optional[str]) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE transactions SET receipt_file_id=?, updated_at=? "
            "WHERE id=? AND scope=? AND owner_user_id=?",
            (file_id, now_ts(), tx_id, scope, owner),
        )

# =========================
# Undo a deletion
# =========================
TX_SNAPSHOT_FIELDS = (
    "id", "scope", "owner_user_id", "actor_user_id", "date_g", "ttype",
    "category", "amount", "description", "created_at", "updated_at",
    "loan_id", "receipt_file_id",
)

def snapshot_tx(row: sqlite3.Row) -> Dict:
    """Everything needed to put a deleted transaction back exactly as it was."""
    return {f: row[f] for f in TX_SNAPSHOT_FIELDS}

def restore_tx(snap: Dict) -> int:
    """Re-insert a snapshotted transaction, keeping its original id."""
    cols = ", ".join(TX_SNAPSHOT_FIELDS)
    marks = ", ".join("?" for _ in TX_SNAPSHOT_FIELDS)
    with db() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO transactions({cols}) VALUES({marks})",
            tuple(snap[f] for f in TX_SNAPSHOT_FIELDS),
        )
    return int(snap["id"])

# =========================
# Reminders and daily digest
# =========================
def loan_due_dates(loan: sqlite3.Row) -> List[str]:
    start = str(loan["start_date_g"])
    return [add_jalali_months(start, i) for i in range(int(loan["installment_count"]))]

def next_unpaid_due(scope: str, owner: int, loan: sqlite3.Row) -> Optional[str]:
    """
    The date of the next installment still owed.

    Payments are counted, not matched to specific dates, so the Nth payment
    simply clears the Nth due date.
    """
    paid = loan_progress(scope, owner, loan)["paid_count"]
    dues = loan_due_dates(loan)
    return dues[paid] if paid < len(dues) else None

def upcoming_loan_reminders(days_ahead: Optional[int] = None) -> List[Dict]:
    """Loans whose next installment falls within the warning window."""
    try:
        if get_setting("loan_reminder_enabled") != "1":
            return []
        window = days_ahead if days_ahead is not None else int(get_setting("loan_reminder_days"))
    except Exception:
        return []

    today = datetime.now(TZ).date()
    cutoff = (today + timedelta(days=max(0, window))).strftime("%Y-%m-%d")

    with db() as conn:
        loans = list(conn.execute("SELECT * FROM loans WHERE is_active=1").fetchall())

    out: List[Dict] = []
    for loan in loans:
        due = next_unpaid_due(str(loan["scope"]), int(loan["owner_user_id"]), loan)
        if due and due <= cutoff:
            out.append({
                "scope": str(loan["scope"]),
                "owner": int(loan["owner_user_id"]),
                "loan": loan,
                "due": due,
            })
    return out

def digest_text(scope: str, owner: int) -> str:
    parts = [daily_list_text(scope, owner, today_g())]

    totals = debt_totals(scope, owner)
    if totals["owed_to_me"] or totals["i_owe"]:
        parts.append(rtl(
            f"🤝 طلب: {fmt_money(totals['owed_to_me'])} | "
            f"بدهی: {fmt_money(totals['i_owe'])}"
        ))

    jy, jm, _ = g_to_j_parts(today_g())
    over = [b for b in budget_status(scope, owner, jy, jm) if b["spent"] > b["limit"]]
    if over:
        names = "، ".join(b["label"] for b in over[:3])
        parts.append(rtl(f"⛔ بودجهٔ رد شده: {names}"))

    return "\n\n".join(parts)

def reminders_kb() -> InlineKeyboardMarkup:
    digest_on = get_setting("digest_enabled") == "1"
    loan_on = get_setting("loan_reminder_enabled") == "1"
    hour = get_setting("digest_hour")
    days = get_setting("loan_reminder_days")

    return ikb([
        [(f"📊 خلاصهٔ روزانه: {'روشن ✅' if digest_on else 'خاموش ❌'}", f"{CB_RM}:tog:digest")],
        [(f"🕘 ساعت ارسال: {hour}", f"{CB_RM}:hour")],
        [(f"📄 یادآور قسط: {'روشن ✅' if loan_on else 'خاموش ❌'}", f"{CB_RM}:tog:loan")],
        [(f"⏳ چند روز قبل: {days}", f"{CB_RM}:days")],
        [("⬅️ بازگشت", f"{CB_M}:st")],
    ])

def reminders_text() -> str:
    return (
        "🔔 یادآورها\n\n"
        "خلاصهٔ روزانه هر شب وضعیت همان روز را می‌فرستد.\n"
        "یادآور قسط، قبل از سررسید هر قسط خبر می‌دهد."
    )

async def digest_job(ctx) -> None:
    """Runs hourly; sends what is due this hour and nothing twice."""
    try:
        now = datetime.now(TZ)
        stamp = now.strftime("%Y-%m-%d")
        app = ctx.application

        if get_setting("digest_enabled") == "1":
            try:
                hour = int(get_setting("digest_hour"))
            except (TypeError, ValueError):
                hour = 21

            if now.hour == hour and app.bot_data.get("digest_sent_on") != stamp:
                app.bot_data["digest_sent_on"] = stamp
                scope, owner = resolve_scope_owner(PRIMARY_ADMIN_USER_ID)
                try:
                    await ctx.bot.send_message(PRIMARY_ADMIN_USER_ID, digest_text(scope, owner))
                except Exception as e:
                    logger.warning("Digest send failed: %s", e)

        if app.bot_data.get("loan_reminded_on") != stamp:
            due = upcoming_loan_reminders()
            if due:
                app.bot_data["loan_reminded_on"] = stamp
                lines = ["🔔 یادآور قسط", ""]
                for item in due:
                    lines.append(
                        f"• {item['loan']['title']}: "
                        f"{fmt_money(int(item['loan']['installment_amount']))} "
                        f"— {g_to_j(item['due'])}"
                    )
                try:
                    await ctx.bot.send_message(PRIMARY_ADMIN_USER_ID, rtl("\n".join(lines)))
                except Exception as e:
                    logger.warning("Loan reminder send failed: %s", e)

    except Exception as e:
        logger.exception("Digest job failed: %s", e)

def schedule_digest_job(app: Application) -> None:
    try:
        for j in app.job_queue.get_jobs_by_name(JOB_DIGEST):
            j.schedule_removal()
    except Exception:
        pass

    app.job_queue.run_repeating(
        callback=digest_job, interval=3600, first=60, name=JOB_DIGEST
    )

# =========================
# Period comparison
# =========================
def previous_period(spec: str) -> Optional[str]:
    """The period immediately before this one, or None for all-time."""
    if spec.startswith("y:"):
        try:
            return f"y:{int(spec[2:]) - 1}"
        except ValueError:
            return None

    if spec.startswith("m:"):
        parts = spec.split(":")
        if len(parts) < 3:
            return None
        try:
            jy, jm = int(parts[1]), int(parts[2])
        except ValueError:
            return None
        return f"m:{jy - 1}:12" if jm == 1 else f"m:{jy}:{jm - 1:02d}"

    return None

def _delta_line(label: str, before: int, after: int) -> str:
    diff = after - before
    arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "▬")
    pct = f"{round(diff * 100 / abs(before)):+d}%" if before else "—"
    return f"{arrow} {label}: {pct} ({diff:+,})"

def comparison_lines(scope: str, owner: int, spec: str) -> Optional[str]:
    """A short 'versus last period' block, or None when there is nothing to compare."""
    prev_spec = previous_period(spec)
    if not prev_spec:
        return None

    _, prev_title, ps, pe = parse_period(prev_spec.split(":"))
    prev = sums_for_range(scope, owner, ps, pe)
    if not any(prev[k] for k in ("income", "work_out", "personal", "installment", "personal_in")):
        return None

    _, _, cs, ce = parse_period(spec.split(":"))
    cur = sums_for_range(scope, owner, cs, ce)

    lines = [f"📈 نسبت به {prev_title}:"]
    for key, label in (
        ("income", "درآمد کاری"),
        ("work_out", "هزینه کاری"),
        ("savings_final", "پس‌انداز نهایی"),
    ):
        lines.append(_delta_line(label, prev[key], cur[key]))
    return "\n".join(lines)

# =========================
# Search
# =========================
def search_transactions(
    scope: str,
    owner: int,
    query: str,
    start_g: Optional[str],
    end_g_exclusive: Optional[str],
    page: int,
    per_page: int,
) -> Tuple[List[sqlite3.Row], int]:
    """Matching transactions for one page, plus the total number of matches."""
    needle = f"%{(query or '').strip()}%"

    where = (
        "scope=? AND owner_user_id=? "
        "AND (category LIKE ? OR IFNULL(description,'') LIKE ?)"
    )
    params: List = [scope, owner, needle, needle]
    if start_g is not None:
        where += " AND date_g>=?"
        params.append(start_g)
    if end_g_exclusive is not None:
        where += " AND date_g<?"
        params.append(end_g_exclusive)

    with db() as conn:
        total = int(conn.execute(
            f"SELECT COUNT(*) AS c FROM transactions WHERE {where}", tuple(params)
        ).fetchone()["c"])

        rows = list(conn.execute(
            f"""
            SELECT * FROM transactions
            WHERE {where}
            ORDER BY date_g DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params) + (per_page, max(0, page) * per_page),
        ).fetchall())

    return rows, total

def search_results_text(query: str, rows: List[sqlite3.Row], total: int, page: int) -> str:
    if not total:
        return rtl(f"🔎 «{query}»\n\nچیزی پیدا نشد.")

    lines = [f"🔎 «{query}» — {total} نتیجه", ""]
    for r in rows:
        note = (r["description"] or "").strip()
        note = f" — {note[:30]}" if note else ""
        lines.append(
            f"• {g_to_j(str(r['date_g']))} | {ttype_label(str(r['ttype']))}"
            f"\n  {r['category']}: {fmt_money(int(r['amount']))}{note}"
        )

    matched_sum = sum(int(r["amount"]) for r in rows)
    lines += ["", f"جمع این صفحه: {fmt_money(matched_sum)}"]
    return rtl("\n".join(lines))

def search_results_kb(query: str, spec: str, page: int, total: int) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    nav = page_nav_row(f"{CB_SR}:p:", page, total, SEARCH_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🔎 جست‌وجوی جدید", callback_data=f"{CB_SR}:new")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_RP}:root")])
    return InlineKeyboardMarkup(rows)

# =========================
# Loans / installments
# =========================
def add_jalali_months(g_date: str, months: int) -> str:
    """Shift a date by whole Jalali months, clamping onto short months."""
    jy, jm, jd = g_to_j_parts(g_date)
    total = (jy * 12 + (jm - 1)) + months
    ny, nm = divmod(total, 12)
    nm += 1

    day = jd
    while day > 1:
        try:
            return j_to_g_str(ny, nm, day)
        except (ValueError, TypeError):
            day -= 1
    return j_to_g_str(ny, nm, 1)

def create_loan(
    scope: str,
    owner: int,
    title: str,
    installment_amount: int,
    installment_count: int,
    start_date_g: str,
) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO loans(scope, owner_user_id, title, installment_amount,
                              installment_count, start_date_g, is_active, created_at)
            VALUES(?,?,?,?,?,?,1,?)
            """,
            (scope, owner, title.strip(), int(installment_amount),
             int(installment_count), start_date_g, now_ts()),
        )
        return int(cur.lastrowid)

def get_loan(scope: str, owner: int, loan_id: int) -> Optional[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM loans WHERE id=? AND scope=? AND owner_user_id=?",
            (loan_id, scope, owner),
        ).fetchone()

def list_loans(scope: str, owner: int) -> List[sqlite3.Row]:
    with db() as conn:
        return list(conn.execute(
            "SELECT * FROM loans WHERE scope=? AND owner_user_id=? ORDER BY is_active DESC, id DESC",
            (scope, owner),
        ).fetchall())

def loan_progress(scope: str, owner: int, loan: sqlite3.Row) -> Dict[str, int]:
    with db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS total
            FROM transactions
            WHERE scope=? AND owner_user_id=? AND loan_id=?
            """,
            (scope, owner, int(loan["id"])),
        ).fetchone()

    paid_count = int(row["cnt"])
    paid_amount = int(row["total"])
    per = int(loan["installment_amount"])
    count = int(loan["installment_count"])
    remaining_count = max(0, count - paid_count)

    return {
        "paid_count": paid_count,
        "paid_amount": paid_amount,
        "total_count": count,
        "total_amount": per * count,
        "remaining_count": remaining_count,
        "remaining_amount": remaining_count * per,
        "percent": round(paid_count * 100 / count) if count else 0,
        "end_date_g": add_jalali_months(str(loan["start_date_g"]), max(0, count - 1)),
    }

def record_loan_payment(
    scope: str,
    owner: int,
    actor: int,
    loan_id: int,
    date_g: Optional[str] = None,
) -> Optional[int]:
    """Book one installment as a personal expense linked back to its loan."""
    loan = get_loan(scope, owner, loan_id)
    if not loan:
        return None

    ensure_installment(scope, owner)
    when = date_g or today_g()
    ts = now_ts()

    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO transactions(
                scope, owner_user_id, actor_user_id, date_g, ttype, category,
                amount, description, created_at, updated_at, loan_id)
            VALUES(?,?,?,?,'personal_out',?,?,?,?,?,?)
            """,
            (scope, owner, actor, when, INSTALLMENT_NAME,
             int(loan["installment_amount"]), str(loan["title"]), ts, ts, loan_id),
        )
        return int(cur.lastrowid)

def delete_loan(scope: str, owner: int, loan_id: int) -> None:
    """Forget the loan but keep its payments — they are real money that moved."""
    with db() as conn:
        conn.execute(
            "UPDATE transactions SET loan_id=NULL WHERE loan_id=? AND scope=? AND owner_user_id=?",
            (loan_id, scope, owner),
        )
        conn.execute(
            "DELETE FROM loans WHERE id=? AND scope=? AND owner_user_id=?",
            (loan_id, scope, owner),
        )

def loans_text(scope: str, owner: int, page: int = 0) -> str:
    loans = list_loans(scope, owner)
    if not loans:
        return rtl(
            "📄 اقساط و وام‌ها\n\n"
            "هنوز وامی ثبت نشده.\n"
            "با «➕ افزودن وام» می‌تونی یکی اضافه کنی تا ربات بگه چند قسط مانده."
        )

    page = max(0, min(page, max(0, (len(loans) - 1) // LOAN_PAGE_SIZE)))
    window = loans[page * LOAN_PAGE_SIZE:(page + 1) * LOAN_PAGE_SIZE]

    lines = [f"📄 اقساط و وام‌ها — {len(loans)} مورد", ""]
    total_remaining = 0
    for loan in loans:
        total_remaining += loan_progress(scope, owner, loan)["remaining_amount"]

    for loan in window:
        p = loan_progress(scope, owner, loan)
        state = "" if int(loan["is_active"]) else " (بسته)"
        lines.append(
            f"• {loan['title']}{state}\n"
            f"  {p['paid_count']} از {p['total_count']} پرداخت شده ({p['percent']}%)\n"
            f"  باقی‌مانده: {fmt_money(p['remaining_amount'])}"
        )

    lines += ["", f"مجموع باقی‌ماندهٔ همهٔ وام‌ها: {fmt_money(total_remaining)}"]
    return rtl("\n".join(lines))

def loans_kb(scope: str, owner: int, page: int = 0) -> InlineKeyboardMarkup:
    loans = list_loans(scope, owner)
    page = max(0, min(page, max(0, (len(loans) - 1) // LOAN_PAGE_SIZE)))
    window = loans[page * LOAN_PAGE_SIZE:(page + 1) * LOAN_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("➕ افزودن وام", callback_data=f"{CB_LN}:add")]
    ]

    for loan in window:
        p = loan_progress(scope, owner, loan)
        rows.append([
            InlineKeyboardButton(
                f"{loan['title']} — {p['remaining_count']} قسط",
                callback_data=f"{CB_LN}:open:{loan['id']}",
            )
        ])

    nav = page_nav_row(f"{CB_LN}:page:", page, len(loans), LOAN_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_M}:st")])
    return InlineKeyboardMarkup(rows)

def loan_detail_text(scope: str, owner: int, loan_id: int) -> str:
    loan = get_loan(scope, owner, loan_id)
    if not loan:
        return rtl("این وام پیدا نشد.")

    p = loan_progress(scope, owner, loan)
    lines = [
        f"📄 {loan['title']}",
        "",
        f"💵 مبلغ هر قسط: {fmt_money(int(loan['installment_amount']))}",
        f"🔢 تعداد اقساط: {p['total_count']}",
        f"💰 مبلغ کل: {fmt_money(p['total_amount'])}",
        "",
        f"✅ پرداخت‌شده: {p['paid_count']} قسط ({fmt_money(p['paid_amount'])})",
        f"⏳ باقی‌مانده: {p['remaining_count']} قسط ({fmt_money(p['remaining_amount'])})",
        f"📊 پیشرفت: {p['percent']}%",
        "",
        f"🗓 شروع: {g_to_j(str(loan['start_date_g']))}",
        f"🏁 آخرین قسط: {g_to_j(p['end_date_g'])}",
    ]
    return rtl("\n".join(lines))

def loan_detail_kb(loan_id: int) -> InlineKeyboardMarkup:
    return ikb([
        [("✅ ثبت پرداخت قسط", f"{CB_LN}:pay:{loan_id}")],
        [("🗑 حذف وام", f"{CB_LN}:del:{loan_id}")],
        [("⬅️ بازگشت", f"{CB_LN}:panel")],
    ])

# =========================
# Recurring transactions
# =========================
PERIOD_LABELS = {"daily": "روزانه", "weekly": "هفتگی", "monthly": "ماهانه"}

def next_run_after(period: str, g_date: str) -> str:
    if period == "daily":
        base = datetime.strptime(g_date, "%Y-%m-%d").date()
        return (base + timedelta(days=1)).strftime("%Y-%m-%d")
    if period == "weekly":
        base = datetime.strptime(g_date, "%Y-%m-%d").date()
        return (base + timedelta(days=7)).strftime("%Y-%m-%d")
    return add_jalali_months(g_date, 1)

def create_recurring(
    scope: str,
    owner: int,
    ttype: str,
    category: str,
    amount: int,
    description: Optional[str],
    period: str,
    next_run_g: str,
) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO recurring(scope, owner_user_id, ttype, category, amount,
                                  description, period, next_run_g, is_active, created_at)
            VALUES(?,?,?,?,?,?,?,?,1,?)
            """,
            (scope, owner, ttype, category.strip(), int(amount),
             (description or None), period, next_run_g, now_ts()),
        )
        return int(cur.lastrowid)

def list_recurring(scope: str, owner: int) -> List[sqlite3.Row]:
    with db() as conn:
        return list(conn.execute(
            "SELECT * FROM recurring WHERE scope=? AND owner_user_id=? ORDER BY is_active DESC, id DESC",
            (scope, owner),
        ).fetchall())

def toggle_recurring(scope: str, owner: int, rid: int) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE recurring SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END
            WHERE id=? AND scope=? AND owner_user_id=?
            """,
            (rid, scope, owner),
        )

def delete_recurring(scope: str, owner: int, rid: int) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM recurring WHERE id=? AND scope=? AND owner_user_id=?",
            (rid, scope, owner),
        )

def run_due_recurring(until_g: Optional[str] = None) -> int:
    """
    Materialise every rule that has come due, catching up on missed periods.

    Returns how many transactions were created. Safe to call repeatedly: a rule
    only fires for dates it has not already produced.
    """
    cutoff = until_g or today_g()
    created = 0

    with db() as conn:
        rules = list(conn.execute(
            "SELECT * FROM recurring WHERE is_active=1 AND next_run_g<=?", (cutoff,)
        ).fetchall())

        for rule in rules:
            when = str(rule["next_run_g"])
            fired = 0

            # A hard stop, so a corrupt next_run_g can never spin forever.
            while when <= cutoff and fired < 400:
                ts = now_ts()
                conn.execute(
                    """
                    INSERT INTO transactions(
                        scope, owner_user_id, actor_user_id, date_g, ttype, category,
                        amount, description, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (rule["scope"], rule["owner_user_id"], rule["owner_user_id"], when,
                     rule["ttype"], rule["category"], int(rule["amount"]),
                     rule["description"], ts, ts),
                )
                created += 1
                fired += 1
                when = next_run_after(str(rule["period"]), when)

            conn.execute(
                "UPDATE recurring SET next_run_g=?, last_run_g=? WHERE id=?",
                (when, cutoff, int(rule["id"])),
            )

    if created:
        logger.info("Recurring rules created %s transaction(s) up to %s", created, cutoff)
    return created

async def recurring_job(ctx) -> None:
    try:
        run_due_recurring()
    except Exception as e:
        logger.exception("Recurring job failed: %s", e)

def schedule_recurring_job(app: Application) -> None:
    try:
        for j in app.job_queue.get_jobs_by_name(JOB_RECURRING):
            j.schedule_removal()
    except Exception:
        pass

    # Hourly, so a restart or a clock change cannot skip a day entirely.
    app.job_queue.run_repeating(
        callback=recurring_job, interval=3600, first=30, name=JOB_RECURRING
    )

def recurring_text(scope: str, owner: int, page: int = 0) -> str:
    rules = list_recurring(scope, owner)
    if not rules:
        return rtl(
            "🔁 تراکنش‌های تکرارشونده\n\n"
            "هنوز قاعده‌ای ثبت نشده.\n"
            "چیزهایی مثل اجاره یا حقوق را یک بار تعریف کن تا خودکار ثبت شوند."
        )

    page = max(0, min(page, max(0, (len(rules) - 1) // LOAN_PAGE_SIZE)))
    window = rules[page * LOAN_PAGE_SIZE:(page + 1) * LOAN_PAGE_SIZE]

    lines = [f"🔁 تراکنش‌های تکرارشونده — {len(rules)} مورد", ""]
    for r in window:
        state = "فعال ✅" if int(r["is_active"]) else "متوقف ⏸"
        lines.append(
            f"• {r['category']} — {fmt_money(int(r['amount']))}\n"
            f"  {ttype_label(str(r['ttype']))} | {PERIOD_LABELS.get(str(r['period']), r['period'])} | {state}\n"
            f"  اجرای بعدی: {g_to_j(str(r['next_run_g']))}"
        )
    return rtl("\n".join(lines))

def recurring_kb(scope: str, owner: int, page: int = 0) -> InlineKeyboardMarkup:
    rules = list_recurring(scope, owner)
    page = max(0, min(page, max(0, (len(rules) - 1) // LOAN_PAGE_SIZE)))
    window = rules[page * LOAN_PAGE_SIZE:(page + 1) * LOAN_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("➕ افزودن قاعده", callback_data=f"{CB_RC}:add")]
    ]

    for r in window:
        toggle = "⏸" if int(r["is_active"]) else "▶️"
        rows.append([
            InlineKeyboardButton(f"{r['category']}", callback_data=f"{CB_RC}:noop"),
            InlineKeyboardButton(toggle, callback_data=f"{CB_RC}:tog:{r['id']}"),
            InlineKeyboardButton("🗑", callback_data=f"{CB_RC}:del:{r['id']}"),
        ])

    nav = page_nav_row(f"{CB_RC}:page:", page, len(rules), LOAN_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_M}:st")])
    return InlineKeyboardMarkup(rows)

# =========================
# Quick entry (free text)
# =========================
def parse_quick_entry(text: str) -> Optional[Dict]:
    """
    Read a one-line transaction: "فروش 250000", "اجاره 1.2م بابت مرداد".

    An optional leading date comes first. The amount splits the rest: what comes
    before it is the category (so multi-word names work), what comes after is the
    note. If the amount comes first, the next single word is the category.
    Returns None whenever the line is not clearly a transaction — a wrong guess
    here would silently record money that never moved.
    """
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return None

    tokens = raw.split()
    if len(tokens) < 2:
        return None

    date_g = None
    if len(tokens) > 2:
        maybe = parse_date_any(tokens[0])
        if maybe:
            date_g = maybe
            tokens = tokens[1:]

    if len(tokens) < 2:
        return None

    # Find the amount, preferring a two-token form like "250 هزار".
    idx, amount, span = -1, None, 1
    for i in range(len(tokens)):
        if i + 1 < len(tokens):
            pair = parse_amount(tokens[i] + tokens[i + 1])
            if pair is not None and parse_amount(tokens[i + 1]) is None:
                idx, amount, span = i, pair, 2
                break
        single = parse_amount(tokens[i])
        if single is not None:
            idx, amount, span = i, single, 1
            break

    if amount is None or idx < 0:
        return None

    before = tokens[:idx]
    after = tokens[idx + span:]

    if before:
        category = " ".join(before)
        description = " ".join(after) or None
    else:
        # Amount first: the very next word names the category.
        if not after:
            return None
        category = after[0]
        description = " ".join(after[1:]) or None

    if not category.strip():
        return None

    return {
        "date_g": date_g or today_g(),
        "category": category.strip(),
        "amount": amount,
        "description": description,
    }

def quick_group_kb() -> InlineKeyboardMarkup:
    rows = [[(grp_label(g), f"qe:g:{g}")] for g in SECTION_ORDER]
    rows.append([("↩️ انصراف", "qe:cancel")])
    return ikb(rows)

async def save_quick_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    entry: Dict,
    ttype: str,
    create_category: bool,
) -> None:
    user = update.effective_user
    scope, owner = resolve_scope_owner(user.id)

    ok, why = within_quota(scope, owner, "tx")
    if not ok:
        await update.effective_chat.send_message(rtl(f"⛔ {why}"))
        return

    if create_category:
        ok, why = within_quota(scope, owner, "cat")
        if not ok:
            await update.effective_chat.send_message(rtl(f"⛔ {why}"))
            return
        with db() as conn:
            try:
                conn.execute(
                    "INSERT INTO categories(scope, owner_user_id, grp, name, is_locked) VALUES(?,?,?,?,0)",
                    (scope, owner, ttype, entry["category"]),
                )
            except sqlite3.IntegrityError:
                pass

    ts = now_ts()
    async with DB_LOCK:
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO transactions(
                    scope, owner_user_id, actor_user_id, date_g, ttype, category,
                    amount, description, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (scope, owner, user.id, entry["date_g"], ttype, entry["category"],
                 int(entry["amount"]), entry["description"], ts, ts),
            )
            tx_id = int(cur.lastrowid)

    context.user_data.pop("quick_pending", None)
    gdate = entry["date_g"]
    lines = [
        "✅ ثبت شد.",
        "",
        f"📅 {gdate} ({g_to_j(gdate)})",
        f"🔖 {ttype_label(ttype)}",
        f"🏷 {entry['category']}",
        f"💵 {fmt_money(int(entry['amount']))}",
    ]
    if entry["description"]:
        lines.append(f"📝 {entry['description']}")

    warning = budget_warning(scope, owner, ttype, entry["category"], gdate)
    if warning:
        lines += ["", warning]

    kb = ikb([
        [("✏️ ویرایش", f"{CB_DTX}:open:{gdate}:{tx_id}")],
        [("📄 لیست همان روز", f"{CB_DL}:show:{gdate}")],
    ])
    await update.effective_chat.send_message(rtl("\n".join(lines)), reply_markup=kb)

async def quick_entry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Finish a quick entry whose category was unknown or ambiguous."""
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    parts = (q.data or "").split(":")
    pending = context.user_data.get("quick_pending")

    if parts[1] == "cancel" or not pending:
        context.user_data.pop("quick_pending", None)
        await safe_edit(q, rtl("↩️ لغو شد." if parts[1] == "cancel" else "این درخواست منقضی شده. دوباره بفرست."))
        return

    ttype = parts[2]
    if ttype not in SECTION_ORDER:
        await safe_edit(q, rtl("گروه نامعتبر."))
        return

    scope, owner = resolve_scope_owner(user.id)
    known = {str(r["grp"]) for r in find_categories_by_name(scope, owner, pending["category"])}

    await safe_edit(q, rtl("⏳ در حال ثبت..."))
    await save_quick_entry(update, context, pending, ttype, create_category=ttype not in known)

async def quick_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Catch plain text typed outside any conversation.

    Registered last in its group, so an active conversation always wins.
    """
    msg = update.message
    if not msg or not msg.text:
        return
    if update.effective_chat and update.effective_chat.type != "private":
        return

    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return

    entry = parse_quick_entry(msg.text)
    if not entry:
        await update.effective_chat.send_message(
            rtl(
                "❓ متوجه نشدم.\n\n"
                "برای ثبت سریع بنویس: «دسته مبلغ [توضیح]»\n"
                "مثال‌ها:\n"
                "• فروش 250000\n"
                "• اجاره ۱٫۲م بابت مرداد\n"
                "• 1405/05/31 خدمات ۵۰۰ک\n\n"
                "یا از منو استفاده کن:"
            ),
            reply_markup=main_menu(),
        )
        return

    scope, owner = resolve_scope_owner(user.id)
    matches = find_categories_by_name(scope, owner, entry["category"])

    if len(matches) == 1:
        await save_quick_entry(update, context, entry, str(matches[0]["grp"]), create_category=False)
        return

    context.user_data["quick_pending"] = entry
    if len(matches) > 1:
        prompt = (
            f"🏷 «{entry['category']}» در چند گروه وجود دارد.\n"
            f"💵 {fmt_money(int(entry['amount']))}\n\n"
            "کدام یک؟"
        )
    else:
        prompt = (
            f"🏷 دستهٔ «{entry['category']}» وجود ندارد.\n"
            f"💵 {fmt_money(int(entry['amount']))}\n\n"
            "در کدام گروه ساخته شود؟"
        )

    await update.effective_chat.send_message(rtl(prompt), reply_markup=quick_group_kb())

# =========================
# Currency handlers
# =========================
async def currency_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")

    if parts[1] == "custom":
        context.user_data.clear()
        await safe_edit(q, rtl("✏️ واحد پول دلخواه را بنویس (مثلاً: درهم):"))
        return CU_CUSTOM

    if parts[1] == "set":
        set_setting("currency", parts[2])
        await safe_edit(q, rtl(f"💱 واحد پول\n\nواحد فعلی: {currency()}"), reply_markup=currency_kb())
        return ConversationHandler.END

    await safe_edit(q, rtl("دستور ناشناخته."), reply_markup=currency_kb())
    return ConversationHandler.END

async def currency_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    name = (update.message.text or "").strip()
    if not name or len(name) > 12:
        await update.effective_chat.send_message(rtl("❌ یک واحد کوتاه بنویس (حداکثر ۱۲ نویسه):"))
        return CU_CUSTOM

    set_setting("currency", name)
    context.user_data.clear()
    await update.effective_chat.send_message(
        rtl(f"💱 واحد پول\n\nواحد فعلی: {currency()}"), reply_markup=currency_kb()
    )
    return ConversationHandler.END

# =========================
# Loan handlers
# =========================
async def loans_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    if act in ("panel", "page"):
        page = 0
        if act == "page":
            try:
                page = int(parts[2])
            except (IndexError, ValueError):
                page = 0
        await safe_edit(q, loans_text(scope, owner, page), reply_markup=loans_kb(scope, owner, page))
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        await safe_edit(q, rtl("📄 نام وام را بنویس (مثلاً: وام مسکن):"))
        return LN_TITLE

    loan_id = int(parts[2])

    if act == "open":
        await safe_edit(q, loan_detail_text(scope, owner, loan_id), reply_markup=loan_detail_kb(loan_id))
        return ConversationHandler.END

    if act == "pay":
        loan = get_loan(scope, owner, loan_id)
        if not loan:
            await safe_edit(q, loans_text(scope, owner), reply_markup=loans_kb(scope, owner))
            return ConversationHandler.END

        ok, why = within_quota(scope, owner, "tx")
        if not ok:
            await safe_edit(q, rtl(f"⛔ {why}"), reply_markup=loan_detail_kb(loan_id))
            return ConversationHandler.END

        async with DB_LOCK:
            record_loan_payment(scope, owner, user.id, loan_id)

        await safe_edit(q, loan_detail_text(scope, owner, loan_id), reply_markup=loan_detail_kb(loan_id))
        return ConversationHandler.END

    if act == "del":
        loan = get_loan(scope, owner, loan_id)
        if not loan:
            await safe_edit(q, loans_text(scope, owner), reply_markup=loans_kb(scope, owner))
            return ConversationHandler.END

        kb = ikb([
            [("🗑 بله، حذف کن", f"{CB_LN}:delok:{loan_id}")],
            [("↩️ انصراف", f"{CB_LN}:open:{loan_id}")],
        ])
        await safe_edit(q, rtl(
            f"⚠️ حذف وام «{loan['title']}»\n\n"
            "پرداخت‌های ثبت‌شده حذف نمی‌شوند و در گزارش‌ها می‌مانند؛\n"
            "فقط پیگیری تعداد اقساط از بین می‌رود.\n\n"
            "آیا مطمئنی؟"
        ), reply_markup=kb)
        return ConversationHandler.END

    if act == "delok":
        async with DB_LOCK:
            delete_loan(scope, owner, loan_id)
        await safe_edit(q, loans_text(scope, owner), reply_markup=loans_kb(scope, owner))
        return ConversationHandler.END

    await safe_edit(q, loans_text(scope, owner), reply_markup=loans_kb(scope, owner))
    return ConversationHandler.END

async def loan_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = (update.message.text or "").strip()
    if not title:
        await update.effective_chat.send_message(rtl("نام خالی است. دوباره بنویس:"))
        return LN_TITLE

    context.user_data["loan_title"] = title[:60]
    await update.effective_chat.send_message(rtl("💵 مبلغ هر قسط را بنویس (مثلاً ۲م یا 2000000):"))
    return LN_AMOUNT

async def loan_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount = parse_amount(update.message.text or "")
    if amount is None or amount <= 0:
        await update.effective_chat.send_message(rtl("❌ مبلغ نامعتبر است. دوباره:"))
        return LN_AMOUNT

    context.user_data["loan_amount"] = amount
    await update.effective_chat.send_message(rtl("🔢 تعداد کل اقساط را بنویس (مثلاً 24):"))
    return LN_COUNT

async def loan_count_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = to_ascii_digits(update.message.text or "").strip()
    if not re.fullmatch(r"\d{1,4}", raw) or int(raw) <= 0:
        await update.effective_chat.send_message(rtl("❌ فقط عدد بین ۱ تا ۹۹۹۹ وارد کن:"))
        return LN_COUNT

    context.user_data["loan_count"] = int(raw)
    await update.effective_chat.send_message(
        rtl("🗓 تاریخ اولین قسط را بنویس (شمسی یا میلادی) یا «امروز»:")
    )
    return LN_START

async def loan_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    start = parse_date_any(update.message.text or "")
    if not start:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. مثلاً 1404/05/01 یا «امروز»:"))
        return LN_START

    title = context.user_data.get("loan_title")
    amount = context.user_data.get("loan_amount")
    count = context.user_data.get("loan_count")
    if not title or amount is None or not count:
        await update.effective_chat.send_message(rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        create_loan(scope, owner, title, int(amount), int(count), start)

    context.user_data.clear()
    await update.effective_chat.send_message(
        loans_text(scope, owner), reply_markup=loans_kb(scope, owner)
    )
    return ConversationHandler.END

# =========================
# Recurring handlers
# =========================
def rc_ttype_kb() -> InlineKeyboardMarkup:
    rows = [[(grp_label(g), f"{CB_RC}:tt:{g}")] for g in SECTION_ORDER]
    rows.append([("↩️ انصراف", f"{CB_RC}:panel")])
    return ikb(rows)

def rc_period_kb() -> InlineKeyboardMarkup:
    rows = [[(PERIOD_LABELS[p], f"{CB_RC}:pr:{p}")] for p in ("monthly", "weekly", "daily")]
    rows.append([("↩️ انصراف", f"{CB_RC}:panel")])
    return ikb(rows)

async def recurring_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    if act in ("panel", "page"):
        page = 0
        if act == "page":
            try:
                page = int(parts[2])
            except (IndexError, ValueError):
                page = 0
        context.user_data.pop("rc_draft", None)
        await safe_edit(q, recurring_text(scope, owner, page), reply_markup=recurring_kb(scope, owner, page))
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        context.user_data["rc_draft"] = {}
        await safe_edit(q, rtl("🔁 نوع تراکنش تکرارشونده را انتخاب کن:"), reply_markup=rc_ttype_kb())
        return RC_TTYPE

    if act == "tog":
        async with DB_LOCK:
            toggle_recurring(scope, owner, int(parts[2]))
        await safe_edit(q, recurring_text(scope, owner), reply_markup=recurring_kb(scope, owner))
        return ConversationHandler.END

    if act == "del":
        kb = ikb([
            [("🗑 بله، حذف کن", f"{CB_RC}:delok:{parts[2]}")],
            [("↩️ انصراف", f"{CB_RC}:panel")],
        ])
        await safe_edit(q, rtl(
            "⚠️ حذف قاعدهٔ تکرارشونده\n\n"
            "تراکنش‌هایی که تا الان ساخته حذف نمی‌شوند.\n\n"
            "آیا مطمئنی؟"
        ), reply_markup=kb)
        return ConversationHandler.END

    if act == "delok":
        async with DB_LOCK:
            delete_recurring(scope, owner, int(parts[2]))
        await safe_edit(q, recurring_text(scope, owner), reply_markup=recurring_kb(scope, owner))
        return ConversationHandler.END

    await safe_edit(q, recurring_text(scope, owner), reply_markup=recurring_kb(scope, owner))
    return ConversationHandler.END

async def rc_ttype_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    ttype = (q.data or "").split(":")[2]
    if ttype not in SECTION_ORDER:
        await safe_edit(q, rtl("نوع نامعتبر."), reply_markup=rc_ttype_kb())
        return RC_TTYPE

    context.user_data.setdefault("rc_draft", {})["ttype"] = ttype
    await safe_edit(q, rtl(f"🏷 نام دسته را بنویس ({grp_label(ttype)}):"))
    return RC_CAT

async def rc_cat_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message(rtl("نام خالی است. دوباره:"))
        return RC_CAT

    context.user_data.setdefault("rc_draft", {})["category"] = name[:40]
    await update.effective_chat.send_message(rtl("💵 مبلغ را بنویس:"))
    return RC_AMOUNT

async def rc_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount = parse_amount(update.message.text or "")
    if amount is None:
        await update.effective_chat.send_message(rtl("❌ مبلغ نامعتبر است. دوباره:"))
        return RC_AMOUNT

    context.user_data.setdefault("rc_draft", {})["amount"] = amount
    await update.effective_chat.send_message(rtl("📝 توضیح (اختیاری) یا /skip:"))
    return RC_DESC

async def rc_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = (update.message.text or "").strip()
    context.user_data.setdefault("rc_draft", {})["description"] = desc or None
    await update.effective_chat.send_message(rtl("⏱ هر چند وقت تکرار شود؟"), reply_markup=rc_period_kb())
    return RC_PERIOD

async def rc_desc_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("rc_draft", {})["description"] = None
    await update.effective_chat.send_message(rtl("⏱ هر چند وقت تکرار شود؟"), reply_markup=rc_period_kb())
    return RC_PERIOD

async def rc_period_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    period = (q.data or "").split(":")[2]
    if period not in PERIOD_LABELS:
        await safe_edit(q, rtl("دوره نامعتبر."), reply_markup=rc_period_kb())
        return RC_PERIOD

    context.user_data.setdefault("rc_draft", {})["period"] = period
    await safe_edit(q, rtl("🗓 اولین اجرا از چه تاریخی؟ (شمسی/میلادی یا «امروز»)"))
    return RC_START

async def rc_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    start = parse_date_any(update.message.text or "")
    if not start:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره:"))
        return RC_START

    draft = context.user_data.get("rc_draft") or {}
    needed = ("ttype", "category", "amount", "period")
    if any(draft.get(k) is None for k in needed):
        await update.effective_chat.send_message(rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        create_recurring(
            scope, owner, draft["ttype"], draft["category"], int(draft["amount"]),
            draft.get("description"), draft["period"], start,
        )
        # Anything already due fires immediately, so the first run is not a surprise.
        run_due_recurring()

    context.user_data.clear()
    await update.effective_chat.send_message(
        recurring_text(scope, owner), reply_markup=recurring_kb(scope, owner)
    )
    return ConversationHandler.END

# =========================
# Search handlers
# =========================
async def search_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    await safe_edit(q, rtl(
        "🔎 جست‌وجو\n\n"
        "بخشی از نام دسته یا توضیح را بنویس.\n"
        "مثال: اجاره"
    ))
    return SR_QUERY

async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, edit: bool) -> None:
    user = update.effective_user
    scope, owner = resolve_scope_owner(user.id)

    query = context.chat_data.get("search_query", "")
    rows, total = search_transactions(scope, owner, query, None, None, page, SEARCH_PAGE_SIZE)
    context.chat_data["search_page"] = page

    text = search_results_text(query, rows, total, page)
    kb = search_results_kb(query, "a", page, total)

    if edit and update.callback_query:
        await safe_edit(update.callback_query, text, reply_markup=kb)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb)

async def search_query_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    query = (update.message.text or "").strip()
    if len(query) < 2:
        await update.effective_chat.send_message(rtl("❌ حداقل ۲ نویسه بنویس:"))
        return SR_QUERY

    context.chat_data["search_query"] = query[:60]
    await show_search_results(update, context, 0, edit=False)
    return ConversationHandler.END

async def search_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    if not context.chat_data.get("search_query"):
        await safe_edit(q, rtl("جست‌وجو منقضی شده. دوباره شروع کن."), reply_markup=main_menu())
        return

    try:
        page = int((q.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 0
    await show_search_results(update, context, page, edit=True)

# =========================
# Custom date range
# =========================
async def range_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    context.user_data.clear()
    await safe_edit(q, rtl(
        "📆 بازهٔ دلخواه\n\n"
        "تاریخ شروع را بنویس (شمسی یا میلادی).\n"
        "مثال: 1404/01/01"
    ))
    return RG_START

async def range_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    start = parse_date_any(update.message.text or "")
    if not start:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره:"))
        return RG_START

    context.user_data["range_start"] = start
    await update.effective_chat.send_message(
        rtl(f"شروع: {g_to_j(start)}\n\nحالا تاریخ پایان را بنویس:")
    )
    return RG_END

async def range_end_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    end = parse_date_any(update.message.text or "")
    if not end:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره:"))
        return RG_END

    start = context.user_data.get("range_start")
    if not start:
        await update.effective_chat.send_message(rtl("خطا: تاریخ شروع مشخص نیست."))
        context.user_data.clear()
        return ConversationHandler.END

    if end < start:
        start, end = end, start

    context.user_data.clear()
    scope, owner = resolve_scope_owner(user.id)
    _, title, s_g, e_ex = parse_period(["r", start, end])
    s = sums_for_range(scope, owner, s_g, e_ex)

    await update.effective_chat.send_message(
        report_lines(f"📊 گزارش {title}", s), reply_markup=range_report_kb(start, end)
    )
    return ConversationHandler.END

# =========================
# Budget handlers
# =========================
def budget_pick_kb() -> InlineKeyboardMarkup:
    rows = [[(f"کل {grp_label(g)}", f"{CB_BG}:t:g:{g}")] for g in SECTION_ORDER]
    rows.append([("🏷 یک دستهٔ مشخص", f"{CB_BG}:t:c")])
    rows.append([("↩️ انصراف", f"{CB_BG}:panel")])
    return ikb(rows)

async def budgets_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    if act in ("panel", "page"):
        page = 0
        if act == "page":
            try:
                page = int(parts[2])
            except (IndexError, ValueError):
                page = 0
        context.user_data.pop("bg_draft", None)
        jy, jm, _ = g_to_j_parts(today_g())
        await safe_edit(q, budgets_text(scope, owner, jy, jm, page),
                        reply_markup=budgets_kb(scope, owner, page))
        return ConversationHandler.END

    if act == "del":
        async with DB_LOCK:
            delete_budget(scope, owner, int(parts[2]))
        jy, jm, _ = g_to_j_parts(today_g())
        await safe_edit(q, budgets_text(scope, owner, jy, jm), reply_markup=budgets_kb(scope, owner))
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        context.user_data["bg_draft"] = {}
        await safe_edit(q, rtl("🎯 بودجه برای چه چیزی؟"), reply_markup=budget_pick_kb())
        return BG_PICK

    if act == "t":
        draft = context.user_data.setdefault("bg_draft", {})
        if parts[2] == "g":
            draft["kind"] = "group"
            draft["target"] = parts[3]
            await safe_edit(q, rtl(f"💵 سقف ماهانه برای {grp_label(parts[3])} را بنویس:"))
            return BG_AMOUNT

        draft["kind"] = "category"
        await safe_edit(q, rtl("🏷 نام دقیق دسته را بنویس:"))
        return BG_CATNAME

    jy, jm, _ = g_to_j_parts(today_g())
    await safe_edit(q, budgets_text(scope, owner, jy, jm), reply_markup=budgets_kb(scope, owner))
    return ConversationHandler.END

async def budget_catname_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.message.text or "").strip()
    if not name:
        await update.effective_chat.send_message(rtl("نام خالی است. دوباره:"))
        return BG_CATNAME

    context.user_data.setdefault("bg_draft", {})["target"] = name[:40]
    await update.effective_chat.send_message(rtl(f"💵 سقف ماهانه برای «{name}» را بنویس:"))
    return BG_AMOUNT

async def budget_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    amount = parse_amount(update.message.text or "")
    if amount is None or amount <= 0:
        await update.effective_chat.send_message(rtl("❌ مبلغ نامعتبر است. دوباره:"))
        return BG_AMOUNT

    draft = context.user_data.get("bg_draft") or {}
    if not draft.get("kind") or not draft.get("target"):
        await update.effective_chat.send_message(rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        set_budget(scope, owner, draft["kind"], draft["target"], amount)

    context.user_data.clear()
    jy, jm, _ = g_to_j_parts(today_g())
    await update.effective_chat.send_message(
        budgets_text(scope, owner, jy, jm), reply_markup=budgets_kb(scope, owner)
    )
    return ConversationHandler.END

# =========================
# Debt handlers
# =========================
def debt_dir_kb() -> InlineKeyboardMarkup:
    return ikb([
        [("📥 به من بدهکار است", f"{CB_DT}:dir:owed_to_me")],
        [("📤 من بدهکارم", f"{CB_DT}:dir:i_owe")],
        [("↩️ انصراف", f"{CB_DT}:panel")],
    ])

async def debts_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    if act in ("panel", "page", "all"):
        page = 0
        if act == "page":
            try:
                page = int(parts[2])
            except (IndexError, ValueError):
                page = 0
        context.user_data.pop("dt_draft", None)
        await safe_edit(q,
            debts_text(scope, owner, page, include_settled=(act == "all")),
            reply_markup=debts_kb(scope, owner, page),
        )
        return ConversationHandler.END

    if act == "settle":
        async with DB_LOCK:
            settle_debt(scope, owner, int(parts[2]))
        await safe_edit(q, debts_text(scope, owner), reply_markup=debts_kb(scope, owner))
        return ConversationHandler.END

    if act == "del":
        async with DB_LOCK:
            delete_debt(scope, owner, int(parts[2]))
        await safe_edit(q, debts_text(scope, owner), reply_markup=debts_kb(scope, owner))
        return ConversationHandler.END

    if act == "add":
        context.user_data.clear()
        context.user_data["dt_draft"] = {}
        await safe_edit(q, rtl("👤 نام طرف حساب را بنویس:"))
        return DT_PERSON

    await safe_edit(q, debts_text(scope, owner), reply_markup=debts_kb(scope, owner))
    return ConversationHandler.END

async def debt_person_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    person = (update.message.text or "").strip()
    if not person:
        await update.effective_chat.send_message(rtl("نام خالی است. دوباره:"))
        return DT_PERSON

    context.user_data.setdefault("dt_draft", {})["person"] = person[:40]
    await update.effective_chat.send_message(rtl("جهت را انتخاب کن:"), reply_markup=debt_dir_kb())
    return DT_DIR

async def debt_dir_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    direction = (q.data or "").split(":")[2]
    if direction not in DEBT_LABELS:
        await safe_edit(q, rtl("گزینه نامعتبر."), reply_markup=debt_dir_kb())
        return DT_DIR

    context.user_data.setdefault("dt_draft", {})["direction"] = direction
    await safe_edit(q, rtl("💵 مبلغ را بنویس:"))
    return DT_AMOUNT

async def debt_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount = parse_amount(update.message.text or "")
    if amount is None:
        await update.effective_chat.send_message(rtl("❌ مبلغ نامعتبر است. دوباره:"))
        return DT_AMOUNT

    context.user_data.setdefault("dt_draft", {})["amount"] = amount
    await update.effective_chat.send_message(rtl("📝 توضیح (اختیاری) یا /skip:"))
    return DT_NOTE

async def debt_note_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note = (update.message.text or "").strip()
    context.user_data.setdefault("dt_draft", {})["note"] = note or None
    await update.effective_chat.send_message(rtl("🗓 سررسید (اختیاری) یا /skip:"))
    return DT_DUE

async def debt_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("dt_draft", {})["note"] = None
    await update.effective_chat.send_message(rtl("🗓 سررسید (اختیاری) یا /skip:"))
    return DT_DUE

async def _save_debt(update: Update, context: ContextTypes.DEFAULT_TYPE, due: Optional[str]) -> int:
    user = update.effective_user
    draft = context.user_data.get("dt_draft") or {}
    if not draft.get("person") or not draft.get("direction") or draft.get("amount") is None:
        await update.effective_chat.send_message(rtl("خطا: اطلاعات ناقص."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        create_debt(scope, owner, draft["person"], draft["direction"],
                    int(draft["amount"]), draft.get("note"), due)

    context.user_data.clear()
    await update.effective_chat.send_message(
        debts_text(scope, owner), reply_markup=debts_kb(scope, owner)
    )
    return ConversationHandler.END

async def debt_due_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    due = parse_date_any(update.message.text or "")
    if not due:
        await update.effective_chat.send_message(rtl("❌ تاریخ نامعتبر است. دوباره یا /skip:"))
        return DT_DUE
    return await _save_debt(update, context, due)

async def debt_due_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_debt(update, context, None)

# =========================
# Trend handler
# =========================
async def trend_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    parts = (q.data or "").split(":")
    metric = parts[2] if len(parts) > 2 else "savings_final"
    try:
        months = int(parts[3])
    except (IndexError, ValueError):
        months = 6

    if metric not in TREND_METRICS:
        metric = "savings_final"
    months = 12 if months == 12 else 6

    scope, owner = resolve_scope_owner(user.id)
    await safe_edit(q, trend_text(scope, owner, metric, months), reply_markup=trend_kb(metric, months))

# =========================
# Reminder handlers
# =========================
async def reminders_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END
    await q.answer()

    parts = (q.data or "").split(":")
    act = parts[1]

    if act == "tog":
        key = "digest_enabled" if parts[2] == "digest" else "loan_reminder_enabled"
        set_setting(key, "0" if get_setting(key) == "1" else "1")
        await safe_edit(q, rtl(reminders_text()), reply_markup=reminders_kb())
        return ConversationHandler.END

    if act == "hour":
        await safe_edit(q, rtl("🕘 ساعت ارسال خلاصهٔ روزانه را بنویس (۰ تا ۲۳):"))
        return RM_HOUR

    if act == "days":
        await safe_edit(q, rtl("⏳ چند روز قبل از سررسید قسط خبر بدهم؟"))
        return RM_DAYS

    await safe_edit(q, rtl(reminders_text()), reply_markup=reminders_kb())
    return ConversationHandler.END

async def reminder_hour_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = to_ascii_digits(update.message.text or "").strip()
    if not re.fullmatch(r"\d{1,2}", raw) or int(raw) > 23:
        await update.effective_chat.send_message(rtl("❌ عددی بین ۰ تا ۲۳ بنویس:"))
        return RM_HOUR

    set_setting("digest_hour", str(int(raw)))
    await update.effective_chat.send_message(rtl(reminders_text()), reply_markup=reminders_kb())
    return ConversationHandler.END

async def reminder_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = to_ascii_digits(update.message.text or "").strip()
    if not re.fullmatch(r"\d{1,2}", raw):
        await update.effective_chat.send_message(rtl("❌ فقط عدد بنویس:"))
        return RM_DAYS

    set_setting("loan_reminder_days", str(int(raw)))
    await update.effective_chat.send_message(rtl(reminders_text()), reply_markup=reminders_kb())
    return ConversationHandler.END

# =========================
# Receipt upload
# =========================
async def receipt_wait(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return ConversationHandler.END

    msg = update.message
    file_id = None
    if msg and msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg and msg.document:
        file_id = msg.document.file_id

    if not file_id:
        await update.effective_chat.send_message(rtl("❌ عکس یا فایل بفرست، یا /cancel بزن."))
        return RCP_WAIT

    tx_id = context.user_data.get("receipt_tx_id")
    gdate = context.user_data.get("receipt_gdate")
    if not isinstance(tx_id, int) or not isinstance(gdate, str):
        await update.effective_chat.send_message(rtl("خطا."))
        context.user_data.clear()
        return ConversationHandler.END

    scope, owner = resolve_scope_owner(user.id)
    async with DB_LOCK:
        set_receipt(scope, owner, tx_id, file_id)

    context.user_data.clear()
    tx = get_tx(scope, owner, tx_id)
    if not tx:
        await update.effective_chat.send_message(rtl("تراکنش پیدا نشد."), reply_markup=tx_menu())
        return ConversationHandler.END

    await update.effective_chat.send_message(
        tx_detail_text(tx, "🧾 رسید ذخیره شد."),
        reply_markup=tx_view_kb(gdate, tx_id, daily_back_cb(gdate, current_pages(context)), True),
    )
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
        schedule_recurring_job(application)
        schedule_digest_job(application)

    app.post_init = _post_init

    # Every conversation can be escaped with /start or /cancel.
    common_fallbacks = [CommandHandler("start", start), CommandHandler("cancel", cancel_cmd)]

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # Main
    app.add_handler(CallbackQueryHandler(main_cb, pattern=r"^m:(home|tx|st|report|noop)$"))

    # Settings / Access
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^st:(cats|access|cur|db)$"))
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
                r"^ct:(grp:(work_in|work_out|personal_in|personal_out)"
                r"|page:(work_in|work_out|personal_in|personal_out):\d+"
                r"|del:\d+|delok:\d+|noop)$"
            ),
        )
    )

    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:add:(work_in|work_out|personal_in|personal_out)$")],
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
                r"|page:\d{4}-\d{2}-\d{2}(?::\d+)+"
                r"|noop)$"
            ),
        )
    )

    # Transaction creation conversation
    tx_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(tx_entry_from_menu, pattern=r"^tx:new$"),
            CallbackQueryHandler(tx_entry_from_daily, pattern=r"^dl:add:\d{4}-\d{2}-\d{2}:(work_in|work_out|personal_in|personal_out)$"),
        ],
        states={
            TX_DATE_MENU: [CallbackQueryHandler(tx_date_menu_cb, pattern=r"^tx:date:(today|g|j)$")],
            TX_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_g_input)],
            TX_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_j_input)],
            TX_TTYPE: [CallbackQueryHandler(tx_ttype_cb, pattern=r"^tx:tt:(work_in|work_out|personal_in|personal_out)$")],
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
        CallbackQueryHandler(
            dtx_cb,
            pattern=r"^dtx:(open|del|delok|undo|cat|rcpv|rcpd):\d{4}-\d{2}-\d{2}:\d+$",
        )
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

    # Reports (summary / comparison / breakdown / CSV export)
    PERIOD_RE = r"(a|y:\d{4}|m:\d{4}:\d{2}|r:\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2})"
    app.add_handler(
        CallbackQueryHandler(
            report_cb,
            pattern=(
                r"^rp:(root"
                r"|y:\d{4}"
                r"|m:\d{4}:\d{2}"
                r"|r:\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}"
                r"|bd:" + PERIOD_RE +
                r"|csv:" + PERIOD_RE + r")$"
            ),
        )
    )

    # Custom date range
    range_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(range_entry, pattern=r"^rp:range$")],
        states={
            RG_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, range_start_input)],
            RG_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, range_end_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(range_conv)

    # Search
    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_entry, pattern=r"^sr:new$")],
        states={SR_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_query_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(search_conv)
    app.add_handler(CallbackQueryHandler(search_page_cb, pattern=r"^sr:p:\d+$"))

    # Currency
    app.add_handler(CallbackQueryHandler(currency_cb, pattern=r"^cu:set:.+$"))
    currency_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(currency_cb, pattern=r"^cu:custom$")],
        states={CU_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, currency_custom_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(currency_conv)

    # Loans and installments
    app.add_handler(
        CallbackQueryHandler(
            loans_cb,
            pattern=r"^ln:(panel|noop|page:\d+|open:\d+|pay:\d+|del:\d+|delok:\d+)$",
        )
    )
    loan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(loans_cb, pattern=r"^ln:add$")],
        states={
            LN_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, loan_title_input)],
            LN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, loan_amount_input)],
            LN_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, loan_count_input)],
            LN_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, loan_start_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(loan_conv)

    # Recurring transactions
    app.add_handler(
        CallbackQueryHandler(
            recurring_cb,
            pattern=r"^rc:(panel|noop|page:\d+|tog:\d+|del:\d+|delok:\d+)$",
        )
    )
    recurring_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(recurring_cb, pattern=r"^rc:add$")],
        states={
            RC_TTYPE: [
                CallbackQueryHandler(rc_ttype_cb, pattern=r"^rc:tt:(work_in|work_out|personal_in|personal_out)$"),
                CallbackQueryHandler(recurring_cb, pattern=r"^rc:panel$"),
            ],
            RC_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rc_cat_input)],
            RC_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rc_amount_input)],
            RC_DESC: [
                CommandHandler("skip", rc_desc_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rc_desc_input),
            ],
            RC_PERIOD: [
                CallbackQueryHandler(rc_period_cb, pattern=r"^rc:pr:(daily|weekly|monthly)$"),
                CallbackQueryHandler(recurring_cb, pattern=r"^rc:panel$"),
            ],
            RC_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, rc_start_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(recurring_conv)

    # Budgets
    app.add_handler(
        CallbackQueryHandler(budgets_cb, pattern=r"^bg:(panel|noop|page:\d+|del:\d+)$")
    )
    budget_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(budgets_cb, pattern=r"^bg:add$")],
        states={
            BG_PICK: [
                CallbackQueryHandler(
                    budgets_cb,
                    pattern=r"^bg:t:(g:(work_in|work_out|personal_in|personal_out)|c)$",
                ),
                CallbackQueryHandler(budgets_cb, pattern=r"^bg:panel$"),
            ],
            BG_CATNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, budget_catname_input)],
            BG_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, budget_amount_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(budget_conv)

    # Debts and receivables
    app.add_handler(
        CallbackQueryHandler(debts_cb, pattern=r"^dt:(panel|noop|all|page:\d+|settle:\d+|del:\d+)$")
    )
    debt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(debts_cb, pattern=r"^dt:add$")],
        states={
            DT_PERSON: [MessageHandler(filters.TEXT & ~filters.COMMAND, debt_person_input)],
            DT_DIR: [
                CallbackQueryHandler(debt_dir_cb, pattern=r"^dt:dir:(owed_to_me|i_owe)$"),
                CallbackQueryHandler(debts_cb, pattern=r"^dt:panel$"),
            ],
            DT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, debt_amount_input)],
            DT_NOTE: [
                CommandHandler("skip", debt_note_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, debt_note_input),
            ],
            DT_DUE: [
                CommandHandler("skip", debt_due_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, debt_due_input),
            ],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(debt_conv)

    # Monthly trend
    app.add_handler(
        CallbackQueryHandler(
            trend_cb,
            pattern=r"^tr:show:(income|work_out|net|savings_final):(6|12)$",
        )
    )

    # Reminders and daily digest
    app.add_handler(
        CallbackQueryHandler(reminders_cb, pattern=r"^rm:(panel|tog:(digest|loan))$")
    )
    reminder_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reminders_cb, pattern=r"^rm:(hour|days)$")],
        states={
            RM_HOUR: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_hour_input)],
            RM_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_days_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(reminder_conv)

    # Receipt upload
    receipt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:rcp:\d{4}-\d{2}-\d{2}:\d+$")],
        states={RCP_WAIT: [MessageHandler(filters.PHOTO | filters.Document.ALL, receipt_wait)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(receipt_conv)

    # Quick entry follow-up (which group should this category live in?)
    app.add_handler(
        CallbackQueryHandler(
            quick_entry_cb,
            pattern=r"^qe:(cancel|g:(work_in|work_out|personal_in|personal_out))$",
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
            pattern=r"^(?!m:|st:|ac:|ad:|ct:|tx:|dl:|dtx:|rp:|db:|ln:|rc:|sr:|cu:|qe:|bg:|dt:|tr:|rm:).+",
        ),
        group=90,
    )

    # Plain text outside every conversation: try to read it as a transaction.
    # Registered last in group 0, so an active conversation always wins.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, quick_entry))

    # Nothing should ever fail silently.
    app.add_error_handler(on_error)

    return app

def main() -> None:
    app = build_app()
    logger.info("%s started. TZ=%s DB=%s", PROJECT_NAME, "Asia/Tehran", DB_PATH)
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
