"""Debts and receivables, tracked outside the ledger on purpose."""

import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Dict, List, Optional

from .config import CB_DT, CB_M, DEBT_PAGE_SIZE
from .jalali import g_to_j
from .money import fmt_money
from .store import db
from .text import page_nav_row, rtl
from .timeutil import now_ts

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
