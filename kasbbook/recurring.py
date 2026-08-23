"""Recurring transaction rules and the job that materialises them."""

import sqlite3
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from typing import List, Optional

from .config import CB_M, CB_RC, JOB_RECURRING, LOAN_PAGE_SIZE, logger
from .jalali import add_jalali_months, g_to_j
from .money import fmt_money
from .store import db
from .text import page_nav_row, rtl, ttype_label
from .timeutil import now_ts, today_g

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
