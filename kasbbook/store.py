"""Database file: connection, schema, migrations, snapshots and validation."""

import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

from .config import ACCESS_ADMIN_ONLY, ADMIN_CHAT_ID, BACKUP_DIR, DB_PATH, DEFAULT_CURRENCY, TZ, logger

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
        _ensure_setting("single_message", "1")   # one screen per chat, edited in place

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

# The locked "قسط" category is ensured once per (scope, owner) per process.
# Without this memo, every screen render fired its own write transaction.
_INSTALLMENT_READY: Set[Tuple[str, int]] = set()

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
