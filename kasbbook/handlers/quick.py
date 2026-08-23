"""One-line transaction entry from free text."""

import sqlite3
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from typing import Dict, Optional

from ..access import access_allowed, deny, resolve_scope_owner, within_quota
from ..budgets import budget_warning
from ..categories import find_categories_by_name
from ..config import CB_DL, CB_DTX, DB_LOCK
from ..jalali import g_to_j
from ..ledger import SECTION_ORDER
from ..menus import main_menu
from ..money import fmt_money
from ..parsing import parse_amount, parse_date_any
from ..store import db
from ..text import grp_label, ikb, rtl, safe_edit, ttype_label
from ..timeutil import now_ts, today_g
from ..screen import render

# =========================
# Quick entry (free text)
# =========================
def parse_quick_entry(text: str) -> Optional[Dict]:
    """
    Read a one-line transaction: "فروش 250000", "اجاره 1.2م بابت مرداد".

    An optional leading date comes first. The amount splits the rest: what comes
    before it is the category (so multi-word names work), what comes after is the
    note. If the amount comes first, the next single word is the category.
    Returns None whenever the line is not clearly a transaction — a wrong guess
    here would silently record money that never moved.
    """
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return None

    tokens = raw.split()
    if len(tokens) < 2:
        return None

    date_g = None
    if len(tokens) > 2:
        maybe = parse_date_any(tokens[0])
        if maybe:
            date_g = maybe
            tokens = tokens[1:]

    if len(tokens) < 2:
        return None

    # Find the amount, preferring a two-token form like "250 هزار".
    idx, amount, span = -1, None, 1
    for i in range(len(tokens)):
        if i + 1 < len(tokens):
            pair = parse_amount(tokens[i] + tokens[i + 1])
            if pair is not None and parse_amount(tokens[i + 1]) is None:
                idx, amount, span = i, pair, 2
                break
        single = parse_amount(tokens[i])
        if single is not None:
            idx, amount, span = i, single, 1
            break

    if amount is None or idx < 0:
        return None

    before = tokens[:idx]
    after = tokens[idx + span:]

    if before:
        category = " ".join(before)
        description = " ".join(after) or None
    else:
        # Amount first: the very next word names the category.
        if not after:
            return None
        category = after[0]
        description = " ".join(after[1:]) or None

    if not category.strip():
        return None

    return {
        "date_g": date_g or today_g(),
        "category": category.strip(),
        "amount": amount,
        "description": description,
    }

def quick_group_kb() -> InlineKeyboardMarkup:
    rows = [[(grp_label(g), f"qe:g:{g}")] for g in SECTION_ORDER]
    rows.append([("↩️ انصراف", "qe:cancel")])
    return ikb(rows)

async def save_quick_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    entry: Dict,
    ttype: str,
    create_category: bool,
) -> None:
    user = update.effective_user
    scope, owner = resolve_scope_owner(user.id)

    ok, why = within_quota(scope, owner, "tx")
    if not ok:
        await render(update, context, rtl(f"⛔ {why}"))
        return

    if create_category:
        ok, why = within_quota(scope, owner, "cat")
        if not ok:
            await render(update, context, rtl(f"⛔ {why}"))
            return
        with db() as conn:
            try:
                conn.execute(
                    "INSERT INTO categories(scope, owner_user_id, grp, name, is_locked) VALUES(?,?,?,?,0)",
                    (scope, owner, ttype, entry["category"]),
                )
            except sqlite3.IntegrityError:
                pass

    ts = now_ts()
    async with DB_LOCK:
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO transactions(
                    scope, owner_user_id, actor_user_id, date_g, ttype, category,
                    amount, description, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (scope, owner, user.id, entry["date_g"], ttype, entry["category"],
                 int(entry["amount"]), entry["description"], ts, ts),
            )
            tx_id = int(cur.lastrowid)

    context.user_data.pop("quick_pending", None)
    gdate = entry["date_g"]
    lines = [
        "✅ ثبت شد.",
        "",
        f"📅 {gdate} ({g_to_j(gdate)})",
        f"🔖 {ttype_label(ttype)}",
        f"🏷 {entry['category']}",
        f"💵 {fmt_money(int(entry['amount']))}",
    ]
    if entry["description"]:
        lines.append(f"📝 {entry['description']}")

    warning = budget_warning(scope, owner, ttype, entry["category"], gdate)
    if warning:
        lines += ["", warning]

    kb = ikb([
        [("✏️ ویرایش", f"{CB_DTX}:open:{gdate}:{tx_id}")],
        [("📄 لیست همان روز", f"{CB_DL}:show:{gdate}")],
    ])
    await render(update, context, rtl("\n".join(lines)), reply_markup=kb)

async def quick_entry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Finish a quick entry whose category was unknown or ambiguous."""
    q = update.callback_query
    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return
    await q.answer()

    parts = (q.data or "").split(":")
    pending = context.user_data.get("quick_pending")

    if parts[1] == "cancel" or not pending:
        context.user_data.pop("quick_pending", None)
        await safe_edit(q, rtl("↩️ لغو شد." if parts[1] == "cancel" else "این درخواست منقضی شده. دوباره بفرست."))
        return

    ttype = parts[2]
    if ttype not in SECTION_ORDER:
        await safe_edit(q, rtl("گروه نامعتبر."))
        return

    scope, owner = resolve_scope_owner(user.id)
    known = {str(r["grp"]) for r in find_categories_by_name(scope, owner, pending["category"])}

    await safe_edit(q, rtl("⏳ در حال ثبت..."))
    await save_quick_entry(update, context, pending, ttype, create_category=ttype not in known)

async def quick_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Catch plain text typed outside any conversation.

    Registered last in its group, so an active conversation always wins.
    """
    msg = update.message
    if not msg or not msg.text:
        return
    if update.effective_chat and update.effective_chat.type != "private":
        return

    user = update.effective_user
    if not access_allowed(user.id):
        await deny(update)
        return

    entry = parse_quick_entry(msg.text)
    if not entry:
        await render(update, context, 
            rtl(
                "❓ متوجه نشدم.\n\n"
                "برای ثبت سریع بنویس: «دسته مبلغ [توضیح]»\n"
                "مثال‌ها:\n"
                "• فروش 250000\n"
                "• اجاره ۱٫۲م بابت مرداد\n"
                "• 1405/05/31 خدمات ۵۰۰ک\n\n"
                "یا از منو استفاده کن:"
            ),
            reply_markup=main_menu(),
        )
        return

    scope, owner = resolve_scope_owner(user.id)
    matches = find_categories_by_name(scope, owner, entry["category"])

    if len(matches) == 1:
        await save_quick_entry(update, context, entry, str(matches[0]["grp"]), create_category=False)
        return

    context.user_data["quick_pending"] = entry
    if len(matches) > 1:
        prompt = (
            f"🏷 «{entry['category']}» در چند گروه وجود دارد.\n"
            f"💵 {fmt_money(int(entry['amount']))}\n\n"
            "کدام یک؟"
        )
    else:
        prompt = (
            f"🏷 دستهٔ «{entry['category']}» وجود ندارد.\n"
            f"💵 {fmt_money(int(entry['amount']))}\n\n"
            "در کدام گروه ساخته شود؟"
        )

    await render(update, context, rtl(prompt), reply_markup=quick_group_kb())
