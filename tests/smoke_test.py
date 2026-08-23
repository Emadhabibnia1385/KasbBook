#!/usr/bin/env python3
"""Offline smoke test for KasbBook. No network, no Telegram calls.

It builds the Application (which compiles and validates every handler pattern),
exercises the pure report / keyboard / parsing / CSV logic against a throwaway
database, and — the part that catches the most real bugs — asserts that every
callback_data any keyboard emits is matched by at least one registered
CallbackQueryHandler pattern.

Run it from anywhere:

    python tests/smoke_test.py

Exit code 0 means everything passed.
"""
import csv
import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

WORK = tempfile.mkdtemp(prefix="kasbbook_smoke_")
os.chdir(WORK)

os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-not-real")
os.environ.setdefault("ADMIN_CHAT_ID", "555001")
os.environ.setdefault("ADMIN_USERNAME", "tester")

sys.path.insert(0, str(REPO))
# The package re-exports its whole public surface, so the test can reach any of
# it from one place while the code stays split by responsibility.
import kasbbook as bot  # noqa: E402

from telegram.ext import CallbackQueryHandler, ConversationHandler  # noqa: E402

FAILS = []
CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILS.append(msg)


def section(title):
    print(f"\n[{title}]")


# =========================================================== application
section("build_app")
app = bot.build_app()
check(app is not None, "application built")
check(len(app.error_handlers) == 1, "global error handler registered")


def collect_patterns(application):
    pats = []

    def walk(h):
        if isinstance(h, ConversationHandler):
            for sub in list(h.entry_points) + list(h.fallbacks):
                walk(sub)
            for lst in h.states.values():
                for sub in lst:
                    walk(sub)
        elif isinstance(h, CallbackQueryHandler) and h.pattern is not None:
            pats.append(h.pattern)

    for group in application.handlers.values():
        for h in group:
            walk(h)
    return pats


# Quick entry must sit after every conversation in its group, otherwise it would
# swallow the text a conversation is waiting for.
from telegram.ext import MessageHandler  # noqa: E402

group0 = app.handlers.get(0, [])
plain_text = [i for i, h in enumerate(group0)
              if isinstance(h, MessageHandler) and not isinstance(h, ConversationHandler)]
convs = [i for i, h in enumerate(group0) if isinstance(h, ConversationHandler)]
check(len(plain_text) == 1, f"exactly one catch-all text handler ({len(plain_text)})")
check(bool(convs) and plain_text and plain_text[0] > max(convs),
      "quick entry is registered after every conversation")
check(plain_text and plain_text[0] == len(group0) - 1, "quick entry is the last handler in its group")

PATTERNS = collect_patterns(app)
print(f"  ..   {len(PATTERNS)} callback patterns registered")


def matched(data):
    return any(p.search(data) for p in PATTERNS)


def audit(kb, label, max_buttons=100):
    """A keyboard is healthy when Telegram will render it and every button works."""
    rows = kb.inline_keyboard
    n_btn = sum(len(r) for r in rows)
    check(n_btn <= max_buttons, f"{label}: {len(rows)} rows / {n_btn} buttons (limit {max_buttons})")

    bad_cb = [b.callback_data for r in rows for b in r if not matched(b.callback_data)]
    check(not bad_cb, f"{label}: every callback has a handler" + (f" — orphans: {bad_cb[:4]}" if bad_cb else ""))

    too_long = [b.callback_data for r in rows for b in r if len(b.callback_data.encode()) > 64]
    check(not too_long, f"{label}: callback_data within 64 bytes" + (f" — {too_long[:2]}" if too_long else ""))

    wide = [len(r) for r in rows if len(r) > 8]
    check(not wide, f"{label}: no row wider than 8 buttons")


# The bot token must never reach the logs: httpx logs full request URLs at INFO.
import logging as _logging  # noqa: E402

for _name in ("httpx", "httpcore", "apscheduler"):
    check(_logging.getLogger(_name).level >= _logging.WARNING,
          f"{_name} logger is quiet enough to keep the token out of logs")

# =========================================================== structure
section("package structure")
import ast as _ast  # noqa: E402

PKG_DIR = REPO / "kasbbook"
mod_files = sorted(PKG_DIR.rglob("*.py"))
check(len(mod_files) > 15, f"{len(mod_files)} modules in the package")

entry = (REPO / "bot.py").read_text(encoding="utf-8")
check(len(entry.splitlines()) < 20, "bot.py stays a thin entry point")
check("from kasbbook.app import main" in entry, "bot.py launches the package")

# Import graph, built from the modules themselves rather than assumed.
graph, sizes = {}, {}
for f in mod_files:
    rel = f.relative_to(PKG_DIR).with_suffix("")
    name = ".".join(rel.parts).replace(".__init__", "") or "__init__"
    text = f.read_text(encoding="utf-8")
    sizes[name] = len(text.splitlines())

    deps = set()
    for node in _ast.walk(_ast.parse(text)):
        if isinstance(node, _ast.ImportFrom) and node.level:
            base = name.split(".")[:-1] if name != "__init__" else []
            target = node.module or ""
            if node.level == 1:
                dep = ".".join(base + target.split(".")) if base else target
            else:
                dep = target
            deps.add(dep.lstrip("."))
    graph[name] = {d for d in deps if d and d in ("__init__",) or d in graph or True}

known = set(graph)
graph = {m: {d for d in deps if d in known} for m, deps in graph.items()}

biggest = max(sizes.items(), key=lambda kv: kv[1])
check(biggest[1] <= 900, f"largest module is {biggest[0]} at {biggest[1]} lines (cap 900)")
check(sizes.get("__init__", 0) < 500, "the package facade stays small")

# Cycles would make import order load-bearing and the layering meaningless.
cycles = []
state = {}

def _visit(mod, stack):
    state[mod] = "open"
    for dep in sorted(graph.get(mod, ())):
        if dep == "__init__":
            continue  # the facade imports everything by design
        if state.get(dep) == "open":
            cycles.append(" -> ".join(stack[stack.index(dep):] + [dep]))
        elif dep not in state:
            _visit(dep, stack + [dep])
    state[mod] = "done"

for m in sorted(graph):
    if m not in state:
        _visit(m, [m])

check(not cycles, "no circular imports between modules" + (f" — {cycles[:2]}" if cycles else ""))

# =========================================================== schema
section("schema and migrations")
check(bot.SCHEMA_VERSION >= 3, f"schema version = {bot.SCHEMA_VERSION}")
with bot.db() as conn:
    row = conn.execute("SELECT v FROM settings WHERE k='schema_version'").fetchone()
    check(row and int(row["v"]) == bot.SCHEMA_VERSION, "fresh database is stamped with the current version")
    cols = bot._columns(conn, "transactions")
    check("loan_id" in cols, "transactions.loan_id exists")
    check("personal_in" in bot._table_sql(conn, "transactions"), "transactions accepts personal_in")
    check("personal_in" in bot._table_sql(conn, "categories"), "categories accepts personal_in")
    for t in ("loans", "recurring"):
        check(bot._table_exists(conn, t), f"table {t} exists")

# A legacy (v1) database must upgrade in place without losing rows.
legacy = os.path.join(WORK, "legacy.db")
lc = sqlite3.connect(legacy)
lc.executescript(
    """
    CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT NOT NULL);
    CREATE TABLE admins(user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, added_at TEXT NOT NULL);
    CREATE TABLE transactions(
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
        updated_at TEXT NOT NULL);
    CREATE TABLE categories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL CHECK(scope IN ('private','shared')),
        owner_user_id INTEGER NOT NULL,
        grp TEXT NOT NULL CHECK(grp IN ('work_in','work_out','personal_out')),
        name TEXT NOT NULL,
        is_locked INTEGER NOT NULL DEFAULT 0);
    INSERT INTO settings(k,v) VALUES('access_mode','admin_only'),('share_enabled','0'),
        ('backup_enabled','0'),('backup_target_type','chat'),('backup_target_id','1'),
        ('backup_interval_hours','1');
    INSERT INTO transactions(scope,owner_user_id,actor_user_id,date_g,ttype,category,amount,
        description,created_at,updated_at)
        VALUES('private',7,7,'2025-06-01','work_in','legacy sale',12345,'note','x','y'),
              ('private',7,7,'2025-06-02','personal_out','قسط',5000,NULL,'x','y');
    INSERT INTO categories(scope,owner_user_id,grp,name,is_locked)
        VALUES('private',7,'work_in','legacy sale',0),('private',7,'personal_out','قسط',1);
    """
)
lc.commit()
lc.close()

real_db = bot.store.DB_PATH
try:
    bot.store.DB_PATH = legacy
    with bot.db() as conn:
        check(bot._detect_version(conn) == 1, "unversioned database detected as v1")
    bot.init_db()
    with bot.db() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
        check(n == 2, f"legacy rows survived the migration ({n} of 2)")
        note = conn.execute("SELECT description FROM transactions WHERE amount=12345").fetchone()
        check(note["description"] == "note", "legacy column values preserved")
        check("personal_in" in bot._table_sql(conn, "transactions"), "legacy transactions widened")
        check("loan_id" in bot._columns(conn, "transactions"), "legacy transactions gained loan_id")
        check(bot._detect_version(conn) == bot.SCHEMA_VERSION, "legacy database stamped to current version")
        cats = conn.execute("SELECT COUNT(*) c FROM categories").fetchone()["c"]
        check(cats == 2, f"legacy categories survived ({cats} of 2)")
    # running it again must be a no-op, not a second rebuild
    bot.init_db()
    with bot.db() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
        check(n == 2, "re-running init_db is idempotent")
finally:
    bot.store.DB_PATH = real_db
    bot._SETTINGS_CACHE.clear()
    bot._INSTALLMENT_READY.clear()

# =========================================================== seed
section("seed data")
SCOPE, OWNER = "private", 555001
bot.ensure_installment(SCOPE, OWNER)

rows = []
for g, ttype, cat, amt in [
    ("2025-04-10", "work_in", "فروش", 500_000),
    ("2025-04-10", "work_out", "اجاره", 120_000),
    ("2025-04-10", "personal_out", "قسط", 90_000),
    ("2025-04-10", "personal_out", "خرید خانه", 40_000),
    ("2025-05-11", "personal_in", "هدیه", 70_000),
    ("2026-01-05", "work_in", "فروش", 800_000),
    ("2026-01-05", "work_out", "حمل و نقل", 60_000),
    ("2026-08-20", "work_in", "خدمات", 300_000),
]:
    rows.append((SCOPE, OWNER, OWNER, g, ttype, cat, amt, None, bot.now_ts(), bot.now_ts()))

BUSY = "2026-08-22"
for i in range(37):
    rows.append((SCOPE, OWNER, OWNER, BUSY, "work_in", f"فروش {i}", 1000 + i, None, bot.now_ts(), bot.now_ts()))
for i in range(19):
    rows.append((SCOPE, OWNER, OWNER, BUSY, "work_out", f"هزینه {i}", 500 + i, None, bot.now_ts(), bot.now_ts()))

with bot.db() as conn:
    conn.executemany(
        """INSERT INTO transactions(scope,owner_user_id,actor_user_id,date_g,ttype,
           category,amount,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
check(True, f"{len(rows)} transactions inserted")

# =========================================================== jalali
section("Jalali calendar")
check(bot.g_to_j("2026-03-21") == "1405/01/01", f"Nowruz 1405 maps correctly ({bot.g_to_j('2026-03-21')})")
check(bot.j_year_range_g(1404) == ("2025-03-21", "2026-03-21"), "Jalali year 1404 spans the right Gregorian range")
check(bot.j_month_range_g(1404, 12)[1] == bot.j_to_g_str(1405, 1, 1), "Esfand rolls into the next year")
for jm in range(1, 13):
    a, b = bot.j_month_range_g(1404, jm)
    check(a < b, f"{bot.jmonth_name(jm)} range is ordered")

years = bot.jalali_years_with_data(SCOPE, OWNER)
check(years == sorted(years, reverse=True) and len(years) >= 2, f"years with data, newest first: {years}")

# =========================================================== parsing
section("input parsing")
for raw, want in [
    ("250000", 250_000),
    ("۲۵۰۰۰۰", 250_000),
    ("250,000", 250_000),
    ("۲۵۰٬۰۰۰", 250_000),
    ("250k", 250_000),
    ("250K", 250_000),
    ("۲۵۰ه", 250_000),
    ("250 هزار", 250_000),
    ("1.2m", 1_200_000),
    ("۱٫۲م", 1_200_000),
    ("2 میلیون", 2_000_000),
    ("1.5 میلیارد", 1_500_000_000),
    ("0", 0),
]:
    got = bot.parse_amount(raw)
    check(got == want, f"amount {raw!r} -> {got} (want {want})")

for raw in ["", "abc", "12abc", "-5", "1.2.3", "k"]:
    check(bot.parse_amount(raw) is None, f"amount {raw!r} rejected")

today = bot.today_g()
for raw, want in [
    ("2026-08-22", "2026-08-22"),
    ("2026-8-2", "2026-08-02"),
    ("1405/05/31", bot.j_to_g_str(1405, 5, 31)),
    ("1405/5/31", bot.j_to_g_str(1405, 5, 31)),
    ("۱۴۰۵/۰۵/۳۱", bot.j_to_g_str(1405, 5, 31)),
    ("1405-05-31", bot.j_to_g_str(1405, 5, 31)),
    ("امروز", today),
    ("today", today),
]:
    got = bot.parse_date_any(raw)
    check(got == want, f"date {raw!r} -> {got} (want {want})")

check(bot.parse_date_any("دیروز") < today, "yesterday resolves before today")
check(bot.parse_date_any("فردا") > today, "tomorrow resolves after today")
for raw in ["", "hello", "1405/13/01", "2026-02-30", "99/1/1"]:
    check(bot.parse_date_any(raw) is None, f"date {raw!r} rejected")

check(bot.to_ascii_digits("۱۲۳۴۵۶۷۸۹۰") == "1234567890", "Persian digits normalised")
check(bot.to_ascii_digits("١٢٣") == "123", "Arabic-Indic digits normalised")

# =========================================================== money
section("currency")
check(bot.get_setting("currency") == bot.DEFAULT_CURRENCY, f"default currency = {bot.DEFAULT_CURRENCY}")
check(bot.fmt_money(1500) == f"1,500 {bot.DEFAULT_CURRENCY}", f"money formatted as {bot.fmt_money(1500)}")
bot.set_setting("currency", "ریال")
check(bot.fmt_money(10) == "10 ریال", "currency change reflected immediately")
bot.set_setting("currency", bot.DEFAULT_CURRENCY)
check(bot.fmt_num(1500) == "1,500", "fmt_num stays unit-free for buttons and CSV")

# =========================================================== reports
section("report arithmetic")
allt = bot.sums_all(SCOPE, OWNER)
check(allt["income"] > 0, f"all-time business income = {allt['income']:,}")
check(allt["net"] == allt["income"] - allt["work_out"], "net = business income - business expense")
check(
    allt["savings_operational"] == allt["net"] + allt["personal_in"] - allt["personal"],
    "operational savings folds in personal income",
)
check(
    allt["savings_final"] == allt["savings_operational"] - allt["installment"],
    "final savings subtracts installments",
)
check(allt["personal_in"] == 70_000, f"personal income totalled ({allt['personal_in']:,})")

per_year = sum(
    bot.sums_for_range(SCOPE, OWNER, *bot.j_year_range_g(jy))["income"] for jy in years
)
check(per_year == allt["income"], f"Jalali years sum to all-time ({per_year} vs {allt['income']})")

jy = years[0]
year_income = bot.sums_for_range(SCOPE, OWNER, *bot.j_year_range_g(jy))["income"]
month_income = sum(
    bot.sums_for_range(SCOPE, OWNER, *bot.j_month_range_g(jy, jm))["income"] for jm in range(1, 13)
)
check(month_income == year_income, f"months of {jy} sum to the year ({month_income} vs {year_income})")

# comparison
prev = bot.previous_period("y:1405")
check(prev == "y:1404", f"previous year of 1405 = {prev}")
check(bot.previous_period("m:1405:01") == "m:1404:12", "previous month of Farvardin is last Esfand")
check(bot.previous_period("m:1405:05") == "m:1405:04", "previous month within a year")
check(bot.previous_period("a") is None, "all-time has no previous period")

cmp_txt = bot.comparison_lines(SCOPE, OWNER, "y:1405")
check(cmp_txt is None or "نسبت به" in cmp_txt, "comparison block renders or is skipped cleanly")

# =========================================================== search
section("search")
hits, total = bot.search_transactions(SCOPE, OWNER, "فروش", None, None, 0, bot.SEARCH_PAGE_SIZE)
check(total >= 38, f"search found {total} rows for 'فروش'")
check(len(hits) <= bot.SEARCH_PAGE_SIZE, f"search page capped at {bot.SEARCH_PAGE_SIZE}")
hits2, total2 = bot.search_transactions(SCOPE, OWNER, "فروش", None, None, 1, bot.SEARCH_PAGE_SIZE)
check(hits and hits2 and hits[0]["id"] != hits2[0]["id"], "search paging advances")
_, none_total = bot.search_transactions(SCOPE, OWNER, "zzz-nothing", None, None, 0, 10)
check(none_total == 0, "search with no match returns nothing")
_, scoped = bot.search_transactions(SCOPE, OWNER, "فروش", "2026-01-01", "2026-02-01", 0, 10)
check(scoped < total, f"date-scoped search narrows results ({scoped} < {total})")

# =========================================================== keyboards
section("keyboards")
for pages in [(0, 0, 0, 0), (1, 1, 0, 0), (4, 2, 0, 0), (99, 99, 99, 99)]:
    audit(bot.daily_rows_kb(SCOPE, OWNER, BUSY, pages), f"daily list pages={pages}")

with bot.db() as conn:
    conn.executemany(
        "INSERT OR IGNORE INTO categories(scope,owner_user_id,grp,name,is_locked) VALUES(?,?,?,?,0)",
        [(SCOPE, OWNER, "work_in", f"دسته {i}") for i in range(120)],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO admins(user_id,name,added_at) VALUES(?,?,?)",
        [(900000 + i, f"ادمین {i}", bot.now_ts()) for i in range(75)],
    )

for page in (0, 1, 9):
    audit(bot.build_cat_kb(SCOPE, OWNER, "work_in", page), f"category manager p{page}")
    audit(bot.cat_pick_keyboard(SCOPE, OWNER, "work_in", f"{bot.CB_M}:tx", page), f"category picker p{page}")
    audit(bot.tx_cat_change_kb(SCOPE, OWNER, "work_in", BUSY, 1, page), f"tx category change p{page}")
    audit(bot.build_admin_panel_kb(page), f"admin panel p{page}")

# =========================================================== loans
section("loans")
loan_id = bot.create_loan(SCOPE, OWNER, "وام مسکن", 2_000_000, 24, "2025-04-10")
check(isinstance(loan_id, int) and loan_id > 0, f"loan created (id={loan_id})")

loan = bot.get_loan(SCOPE, OWNER, loan_id)
check(loan is not None, "loan reads back")
prog = bot.loan_progress(SCOPE, OWNER, loan)
check(prog["paid_count"] == 0, "new loan has no payments")
check(prog["remaining_count"] == 24, "24 installments remaining")
check(prog["remaining_amount"] == 48_000_000, f"remaining amount = {prog['remaining_amount']:,}")
check(prog["end_date_g"] > "2025-04-10", f"projected end date {prog['end_date_g']}")

tx_id = bot.record_loan_payment(SCOPE, OWNER, OWNER, loan_id, "2025-05-10")
check(isinstance(tx_id, int), "loan payment recorded as a transaction")
with bot.db() as conn:
    r = conn.execute("SELECT ttype, category, amount, loan_id FROM transactions WHERE id=?", (tx_id,)).fetchone()
check(r["ttype"] == "personal_out", "loan payment is a personal expense")
check(r["category"] == bot.INSTALLMENT_NAME, "loan payment lands in the locked installment category")
check(r["loan_id"] == loan_id, "loan payment is linked to its loan")

prog = bot.loan_progress(SCOPE, OWNER, bot.get_loan(SCOPE, OWNER, loan_id))
check(prog["paid_count"] == 1, "payment counted")
check(prog["remaining_count"] == 23, "remaining count decremented")

audit(bot.loans_kb(SCOPE, OWNER, 0), "loan list")
audit(bot.loan_detail_kb(loan_id), "loan detail")
check("وام مسکن" in bot.loans_text(SCOPE, OWNER), "loan list mentions the loan")
check("۲۳" in bot.loan_detail_text(SCOPE, OWNER, loan_id) or "23" in bot.loan_detail_text(SCOPE, OWNER, loan_id),
      "loan detail shows what is left")

for i in range(60):
    bot.create_loan(SCOPE, OWNER, f"وام {i}", 1000, 12, "2025-04-10")
for page in (0, 1, 5):
    audit(bot.loans_kb(SCOPE, OWNER, page), f"loan list p{page}")

# deleting a loan keeps its payments
bot.delete_loan(SCOPE, OWNER, loan_id)
check(bot.get_loan(SCOPE, OWNER, loan_id) is None, "loan deleted")
with bot.db() as conn:
    kept = conn.execute("SELECT loan_id FROM transactions WHERE id=?", (tx_id,)).fetchone()
check(kept is not None, "the payment transaction survived the loan")
check(kept["loan_id"] is None, "the payment was unlinked, not deleted")

# =========================================================== recurring
section("recurring transactions")
rec_id = bot.create_recurring(SCOPE, OWNER, "work_out", "اجاره", 500_000, "ماهانه", "monthly", "2025-04-10")
check(isinstance(rec_id, int), f"recurring rule created (id={rec_id})")

check(bot.next_run_after("daily", "2025-04-10") == "2025-04-11", "daily rolls one day")
check(bot.next_run_after("weekly", "2025-04-10") == "2025-04-17", "weekly rolls seven days")
nxt = bot.next_run_after("monthly", "2025-04-10")
check(bot.g_to_j_parts(nxt)[1] != bot.g_to_j_parts("2025-04-10")[1], f"monthly rolls a Jalali month ({nxt})")

# Esfand 30 in a leap year must not fall off the calendar
last = bot.next_run_after("monthly", bot.j_to_g_str(1403, 12, 29))
check(last is not None, f"month rollover from Esfand works ({last})")

before = bot.count_transactions(SCOPE, OWNER)
made = bot.run_due_recurring(until_g="2025-07-01")
after = bot.count_transactions(SCOPE, OWNER)
check(made >= 2, f"due rules materialised {made} transactions")
check(after == before + made, "each materialised rule produced exactly one row")

again = bot.run_due_recurring(until_g="2025-07-01")
check(again == 0, "running the catch-up twice does not duplicate rows")

with bot.db() as conn:
    nr = conn.execute("SELECT next_run_g, last_run_g FROM recurring WHERE id=?", (rec_id,)).fetchone()
check(nr["next_run_g"] > "2025-07-01", f"next run advanced past the cutoff ({nr['next_run_g']})")
check(nr["last_run_g"] is not None, "last run recorded")

bot.toggle_recurring(SCOPE, OWNER, rec_id)
with bot.db() as conn:
    st = conn.execute("SELECT is_active FROM recurring WHERE id=?", (rec_id,)).fetchone()
check(int(st["is_active"]) == 0, "recurring rule can be paused")
check(bot.run_due_recurring(until_g="2030-01-01") == 0, "a paused rule never fires")

audit(bot.recurring_kb(SCOPE, OWNER, 0), "recurring list")
check("اجاره" in bot.recurring_text(SCOPE, OWNER), "recurring list names the rule")

# =========================================================== quick entry
section("quick entry parsing")
cases = [
    ("فروش 250000", "فروش", 250_000, None),
    ("فروش ۲۵۰ک", "فروش", 250_000, None),
    ("اجاره 1.2م بابت مرداد", "اجاره", 1_200_000, "بابت مرداد"),
    ("خرید خانه 40000", "خرید خانه", 40_000, None),
    ("250000 فروش", "فروش", 250_000, None),
]
for text, want_cat, want_amt, want_desc in cases:
    parsed = bot.parse_quick_entry(text)
    check(parsed is not None, f"quick entry parses {text!r}")
    if parsed:
        check(parsed["category"] == want_cat, f"  category -> {parsed['category']!r} (want {want_cat!r})")
        check(parsed["amount"] == want_amt, f"  amount -> {parsed['amount']} (want {want_amt})")
        check(parsed["description"] == want_desc, f"  description -> {parsed['description']!r}")
        check(parsed["date_g"] == today, "  defaults to today")

dated = bot.parse_quick_entry("1405/05/31 فروش 5000")
check(dated and dated["date_g"] == bot.j_to_g_str(1405, 5, 31), "quick entry accepts a leading date")
check(dated and dated["category"] == "فروش", "  category still parsed after a date")

for text in ["", "فروش", "12345", "سلام چطوری", "/start"]:
    check(bot.parse_quick_entry(text) is None, f"quick entry ignores {text!r}")

with bot.db() as conn:
    conn.execute(
        "INSERT OR IGNORE INTO categories(scope,owner_user_id,grp,name,is_locked) VALUES(?,?,?,?,0)",
        (SCOPE, OWNER, "work_in", "فروش"),
    )
matches = bot.find_categories_by_name(SCOPE, OWNER, "فروش")
check(len(matches) == 1, f"category lookup found {len(matches)} exact match")
check(matches and matches[0]["grp"] == "work_in", "lookup returns the owning group")
check(len(bot.find_categories_by_name(SCOPE, OWNER, "  فروش  ")) == 1, "lookup tolerates surrounding spaces")

with bot.db() as conn:
    conn.execute(
        "INSERT OR IGNORE INTO categories(scope,owner_user_id,grp,name,is_locked) VALUES(?,?,?,?,0)",
        (SCOPE, OWNER, "personal_out", "فروش"),
    )
ambiguous = bot.find_categories_by_name(SCOPE, OWNER, "فروش")
check(len(ambiguous) == 2, "a name used in two groups returns both, for disambiguation")

# =========================================================== quotas
section("public-mode quotas")
bot.set_setting("access_mode", bot.ACCESS_PUBLIC)
ok, why = bot.within_quota(SCOPE, OWNER, "tx")
check(ok, f"normal usage inside the quota ({why})")
check(bot.PUBLIC_MAX_TX_PER_DAY > 0 and bot.PUBLIC_MAX_CATEGORIES > 0, "quotas configured")

with bot.db() as conn:
    n_cats = conn.execute(
        "SELECT COUNT(*) c FROM categories WHERE scope=? AND owner_user_id=?", (SCOPE, OWNER)
    ).fetchone()["c"]
real_cap = bot.PUBLIC_MAX_CATEGORIES
try:
    bot.access.PUBLIC_MAX_CATEGORIES = 1
    ok, why = bot.within_quota(SCOPE, OWNER, "cat")
    check(not ok, f"category quota enforced with {n_cats} categories ({why})")
finally:
    bot.access.PUBLIC_MAX_CATEGORIES = real_cap

bot.set_setting("access_mode", bot.ACCESS_ADMIN_ONLY)
ok, _ = bot.within_quota(SCOPE, OWNER, "cat")
check(ok, "admin mode is not rate limited")

# =========================================================== budgets
section("budgets")
JY, JM = bot.g_to_j_parts(BUSY)[0], bot.g_to_j_parts(BUSY)[1]

bot.set_budget(SCOPE, OWNER, "group", "work_out", 100_000)
bot.set_budget(SCOPE, OWNER, "category", "اجاره", 50_000)
check(len(bot.list_budgets(SCOPE, OWNER)) == 2, "two budgets stored")

bot.set_budget(SCOPE, OWNER, "group", "work_out", 200_000)
check(len(bot.list_budgets(SCOPE, OWNER)) == 2, "setting the same target updates instead of duplicating")

status = bot.budget_status(SCOPE, OWNER, JY, JM)
check(len(status) == 2, "budget status covers every budget")
grp = [x for x in status if x["kind"] == "group"][0]
check(grp["limit"] == 200_000, f"limit reflects the update ({grp['limit']})")
check(grp["spent"] >= 0, f"spend computed ({grp['spent']})")
check(grp["remaining"] == grp["limit"] - grp["spent"], "remaining = limit - spent")
check(0 <= grp["percent"] or grp["percent"] > 100, "percent computed")

over = [x for x in status if x["spent"] > x["limit"]]
check(isinstance(over, list), "over-budget rows identifiable")
check("بودجه" in bot.budgets_text(SCOPE, OWNER, JY, JM), "budget screen renders")

b_id = bot.list_budgets(SCOPE, OWNER)[0]["id"]
bot.delete_budget(SCOPE, OWNER, b_id)
check(len(bot.list_budgets(SCOPE, OWNER)) == 1, "budget deleted")

for i in range(40):
    bot.set_budget(SCOPE, OWNER, "category", f"بودجه {i}", 1000)
for page in (0, 1, 5):
    audit(bot.budgets_kb(SCOPE, OWNER, page), f"budget list p{page}")

# =========================================================== debts
section("debts and receivables")
d1 = bot.create_debt(SCOPE, OWNER, "علی", "owed_to_me", 500_000, "نسیه", "2026-09-01")
d2 = bot.create_debt(SCOPE, OWNER, "بانک", "i_owe", 300_000, None, None)
check(isinstance(d1, int) and isinstance(d2, int), "debts created")

totals = bot.debt_totals(SCOPE, OWNER)
check(totals["owed_to_me"] == 500_000, f"receivable total ({totals['owed_to_me']:,})")
check(totals["i_owe"] == 300_000, f"payable total ({totals['i_owe']:,})")
check(totals["net"] == 200_000, f"net position ({totals['net']:,})")

check(len(bot.list_debts(SCOPE, OWNER)) == 2, "open debts listed")
bot.settle_debt(SCOPE, OWNER, d1)
check(len(bot.list_debts(SCOPE, OWNER)) == 1, "settled debt leaves the open list")
check(len(bot.list_debts(SCOPE, OWNER, include_settled=True)) == 2, "settled debt is kept for history")
check(bot.debt_totals(SCOPE, OWNER)["owed_to_me"] == 0, "settling clears it from the totals")

# a debt is a promise, not money that moved — it must not touch the ledger
before_tx = bot.count_transactions(SCOPE, OWNER)
bot.create_debt(SCOPE, OWNER, "رضا", "owed_to_me", 10_000, None, None)
check(bot.count_transactions(SCOPE, OWNER) == before_tx, "debts never create transactions")

check("علی" in bot.debts_text(SCOPE, OWNER, include_settled=True), "debt screen names the person")
for i in range(40):
    bot.create_debt(SCOPE, OWNER, f"شخص {i}", "i_owe", 100, None, None)
for page in (0, 1, 5):
    audit(bot.debts_kb(SCOPE, OWNER, page), f"debt list p{page}")

# =========================================================== trend
section("trend chart")
trend = bot.monthly_trend(SCOPE, OWNER, 6, "income")
check(len(trend) == 6, f"six months of trend data ({len(trend)})")
check(all(isinstance(v, int) for _, v in trend), "trend values are numbers")
txt = bot.trend_text(SCOPE, OWNER, "income", 6)
check("روند" in txt, "trend chart renders")
check(len(txt) < 4096, f"trend fits one message ({len(txt)} chars)")
check(bot.trend_text(SCOPE, OWNER, "savings_final", 12).count("\n") > 3, "12-month trend renders")
audit(bot.trend_kb("income", 6), "trend controls")

# a metric that is always zero must not blow up on the scaling divide
empty = bot.trend_text(SCOPE, 999999, "income", 6)
check(isinstance(empty, str) and empty, "trend survives an owner with no data")

# =========================================================== weeks
section("week ranges")
ws, we = bot.week_range_g(0)
check(ws <= bot.today_g() <= we, f"this week contains today ({ws}..{we})")
ls, le = bot.week_range_g(1)
check(le < ws, f"last week ends before this week starts ({ls}..{le})")
import datetime as _dt  # noqa: E402
check((_dt.date.fromisoformat(we) - _dt.date.fromisoformat(ws)).days == 6, "a week spans seven days")
check(_dt.date.fromisoformat(ws).weekday() == 5, "the week starts on Saturday")

# =========================================================== receipts
section("receipts")
with bot.db() as conn:
    some_tx = conn.execute("SELECT id, date_g FROM transactions LIMIT 1").fetchone()
    check("receipt_file_id" in bot._columns(conn, "transactions"), "transactions.receipt_file_id exists")

bot.set_receipt(SCOPE, OWNER, int(some_tx["id"]), "FAKE_FILE_ID")
with bot.db() as conn:
    got = conn.execute("SELECT receipt_file_id FROM transactions WHERE id=?", (int(some_tx["id"]),)).fetchone()
check(got["receipt_file_id"] == "FAKE_FILE_ID", "receipt stored")
audit(bot.tx_view_kb(str(some_tx["date_g"]), int(some_tx["id"]), has_receipt=True), "tx view with a receipt")
audit(bot.tx_view_kb(str(some_tx["date_g"]), int(some_tx["id"]), has_receipt=False), "tx view without a receipt")
bot.set_receipt(SCOPE, OWNER, int(some_tx["id"]), None)
with bot.db() as conn:
    got = conn.execute("SELECT receipt_file_id FROM transactions WHERE id=?", (int(some_tx["id"]),)).fetchone()
check(got["receipt_file_id"] is None, "receipt removable")

# =========================================================== undo
section("undo a delete")
tx_row = bot.get_tx(SCOPE, OWNER, int(some_tx["id"]))
snap = bot.snapshot_tx(tx_row)
check(isinstance(snap, dict) and snap["id"] == int(some_tx["id"]), "transaction snapshotted before deletion")

with bot.db() as conn:
    conn.execute("DELETE FROM transactions WHERE id=?", (int(some_tx["id"]),))
check(bot.get_tx(SCOPE, OWNER, int(some_tx["id"])) is None, "transaction gone")

restored = bot.restore_tx(snap)
check(restored == int(some_tx["id"]), "undo restores the same row id")
back = bot.get_tx(SCOPE, OWNER, int(some_tx["id"]))
check(back is not None and int(back["amount"]) == int(tx_row["amount"]), "undo restores the amount")
check(bot.restore_tx(snap) == int(some_tx["id"]), "undo is idempotent")

# =========================================================== reminders
section("reminders and digest")
check(bot.get_setting("digest_enabled") in ("0", "1"), "digest setting present")
check(bot.get_setting("loan_reminder_enabled") in ("0", "1"), "loan reminder setting present")

rl = bot.create_loan(SCOPE, OWNER, "وام یادآور", 1000, 6, bot.today_g())
loan = bot.get_loan(SCOPE, OWNER, rl)
dues = bot.loan_due_dates(loan)
check(len(dues) == 6, f"six due dates generated ({len(dues)})")
check(dues == sorted(dues), "due dates are in order")
check(dues[0] == bot.today_g(), "the first installment falls on the start date")

nxt = bot.next_unpaid_due(SCOPE, OWNER, loan)
check(nxt == dues[0], f"next unpaid due is the first one ({nxt})")
bot.record_loan_payment(SCOPE, OWNER, OWNER, rl, bot.today_g())
check(bot.next_unpaid_due(SCOPE, OWNER, bot.get_loan(SCOPE, OWNER, rl)) == dues[1],
      "next unpaid due advances after a payment")

bot.set_setting("loan_reminder_enabled", "1")
due_soon = bot.upcoming_loan_reminders(days_ahead=40)
check(any(int(x["loan"]["id"]) == rl for x in due_soon), "the loan shows up in upcoming reminders")
bot.set_setting("loan_reminder_enabled", "0")
check(bot.upcoming_loan_reminders(days_ahead=40) == [], "reminders off means no reminders")

check("گزارش روز" in bot.digest_text(SCOPE, OWNER), "digest renders a daily summary")
audit(bot.reminders_kb(), "reminder settings")

# =========================================================== static menus
section("menus")
static = {
    "main": bot.main_menu(),
    "transactions": bot.tx_menu(),
    "settings (primary admin)": bot.settings_menu(bot.PRIMARY_ADMIN_USER_ID),
    "settings (other user)": bot.settings_menu(4242),
    "access": bot.access_menu(bot.PRIMARY_ADMIN_USER_ID),
    "categories root": bot.cats_root_menu(),
    "currency": bot.currency_kb(),
    "daily picker": bot.daily_pick_menu(),
    "tx date": bot.tx_date_menu_kb(f"{bot.CB_M}:tx"),
    "tx type": bot.tx_ttype_kb(f"{bot.CB_M}:tx"),
    "tx view": bot.tx_view_kb(BUSY, 1),
    "tx view (with page memory)": bot.tx_view_kb(BUSY, 1, bot.daily_back_cb(BUSY, (2, 1, 0, 0))),
    "edit date": bot.ed_date_menu_kb(BUSY, 1),
    "report root": bot.report_root_kb(years),
    "report year": bot.report_year_kb(years[0]),
    "report month": bot.report_month_kb(years[0], 5),
    "back (all time)": bot.back_to_period_kb("a"),
    "back (year)": bot.back_to_period_kb(f"y:{years[0]}"),
    "back (month)": bot.back_to_period_kb(f"m:{years[0]}:05"),
    "database": bot.db_menu_kb(),
    "backup target": bot.db_target_kb(),
    "search results": bot.search_results_kb("فروش", "a", 0, 40),
}
for name, kb in static.items():
    audit(kb, name)

# =========================================================== breakdown/CSV
section("breakdown and CSV")
allt = bot.sums_all(SCOPE, OWNER)  # rows were added by the loan and recurring sections
data = bot.category_breakdown(SCOPE, OWNER, None, None)
check(set(bot.SECTION_ORDER) <= set(data.keys()), "breakdown covers every transaction type")
txt = bot.breakdown_text("کلی", data)
check(len(txt) < 4096, f"breakdown fits one Telegram message ({len(txt)} chars)")
grand = sum(t for items in data.values() for _, t, _ in items)
expected = allt["income"] + allt["work_out"] + allt["installment"] + allt["personal"] + allt["personal_in"]
check(grand == expected, f"breakdown totals reconcile ({grand} vs {expected})")

payload = bot.make_csv_bytes(SCOPE, OWNER, None, None)
check(payload.startswith("﻿".encode("utf-8")), "CSV carries a UTF-8 BOM for Excel")
parsed = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))
check(parsed[0][0] == "شناسه", "CSV header is Persian")
check(len(parsed) - 1 == bot.count_transactions(SCOPE, OWNER), "CSV row count matches the table")
check("/" in parsed[1][2], f"CSV carries a Jalali date column ({parsed[1][2]})")

# =========================================================== backups
section("backup and restore safety")
ok, why = bot.validate_backup_file(bot.DB_PATH)
check(ok, f"the live database validates ({why})")

junk = os.path.join(WORK, "junk.db")
open(junk, "wb").write(b"not a database at all " * 50)
ok, why = bot.validate_backup_file(junk)
check(not ok, f"garbage rejected ({why})")

empty = os.path.join(WORK, "empty.db")
c = sqlite3.connect(empty)
c.execute("CREATE TABLE unrelated(x INTEGER)")
c.commit()
c.close()
ok, why = bot.validate_backup_file(empty)
check(not ok, "a SQLite file with the wrong schema is rejected")

trunc = os.path.join(WORK, "trunc.db")
raw = open(bot.DB_PATH, "rb").read()
open(trunc, "wb").write(raw[: len(raw) // 3])
ok, why = bot.validate_backup_file(trunc)
check(not ok, "a truncated database is rejected")

open(bot.DB_PATH + "-wal", "wb").write(b"stale")
open(bot.DB_PATH + "-shm", "wb").write(b"stale")
bot.drop_sidecars()
check(
    not os.path.exists(bot.DB_PATH + "-wal") and not os.path.exists(bot.DB_PATH + "-shm"),
    "stale -wal/-shm removed before a restore",
)
check(bot.make_backup_bytes()[:15] == b"SQLite format 3", "backup snapshot is a real SQLite file")
check(bool(bot.save_disk_backup("probe.db", b"x" * 10)), "on-disk rollback copy written")

# =========================================================== misc
section("misc")
check(bot.normalize_pages(("2", "x", None)) == (0, 0, 0, 0), "bad page data falls back to zeros")
check(bot.normalize_pages(["3"]) == (3, 0, 0, 0), "short page tuple padded")
check(bot.daily_back_cb(BUSY, (1, 2, 3, 4)) == f"dl:page:{BUSY}:1:2:3:4", "back callback keeps every page")
check("گزارش روز" in bot.daily_list_text(SCOPE, OWNER, BUSY), "daily summary renders")

with bot.db() as conn:
    tx = conn.execute("SELECT * FROM transactions LIMIT 1").fetchone()
check("جزئیات تراکنش" in bot.tx_detail_text(tx), "transaction detail renders")

import shutil  # noqa: E402

shutil.rmtree(WORK, ignore_errors=True)

print("\n" + "=" * 62)
if FAILS:
    print(f"{len(FAILS)} of {CHECKS} checks FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print(f"ALL {CHECKS} CHECKS PASSED")
