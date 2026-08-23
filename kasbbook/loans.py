"""Loans and their installment schedule."""

import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Dict, List, Optional

from .categories import ensure_installment
from .config import CB_LN, CB_M, INSTALLMENT_NAME, LOAN_PAGE_SIZE
from .jalali import add_jalali_months, g_to_j
from .money import fmt_money
from .store import db
from .text import ikb, page_nav_row, rtl
from .timeutil import now_ts, today_g

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
