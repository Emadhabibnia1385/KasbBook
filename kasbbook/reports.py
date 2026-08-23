"""Reports, breakdowns, trends, comparison, search and CSV export."""

import csv
import io
import sqlite3
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Dict, List, Optional, Tuple

from .config import CB_M, CB_RP, CB_SR, CB_TR, SEARCH_PAGE_SIZE, TOP_CATEGORIES, TZ
from .jalali import g_to_j, g_to_j_parts, j_month_range_g, j_year_range_g, jmonth_name, week_range_g
from .ledger import SECTION_ORDER, sums_for_range
from .money import fmt_money
from .store import db
from .text import fmt_num, grp_label, ikb, page_nav_row, rtl, ttype_label
from .timeutil import today_g

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
