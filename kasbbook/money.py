"""Currency setting and money formatting."""

from telegram import InlineKeyboardMarkup

from .config import CB_CU, CB_M, DEFAULT_CURRENCY
from .store import get_setting
from .text import fmt_num, ikb

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
