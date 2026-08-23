"""Low-level rendering: RTL text, keyboards, safe edits, labels."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from typing import List, Optional

from .config import CB_M, RLM

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
