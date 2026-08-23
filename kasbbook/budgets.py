"""Monthly spending ceilings and the warnings they raise."""

import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Dict, List, Optional

from .config import BUDGET_PAGE_SIZE, CB_BG, CB_M
from .jalali import g_to_j_parts, j_month_range_g, jmonth_name
from .money import fmt_money
from .store import db
from .text import grp_label, page_nav_row, rtl
from .timeutil import now_ts, today_g

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
