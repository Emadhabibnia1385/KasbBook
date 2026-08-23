"""Transactions: storage, totals, the daily list and the detail view."""

import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from typing import Dict, List, Optional, Tuple

from .categories import ensure_installment, fetch_cats
from .config import CAT_PAGE_SIZE, CB_DL, CB_DTX, CB_M, DAILY_PAGE_SIZE, INSTALLMENT_NAME
from .jalali import g_to_j
from .money import fmt_money
from .store import db
from .text import fmt_num, ikb, page_nav_row, rtl, ttype_label
from .timeutil import now_ts, today_g

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
