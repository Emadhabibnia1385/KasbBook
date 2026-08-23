"""Category storage and the keyboards that list them."""

import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List

from .config import CAT_PAGE_SIZE, CB_CT, CB_ST, CB_TX, INSTALLMENT_NAME
from .store import _INSTALLMENT_READY, db
from .text import page_nav_row

def ensure_installment(scope: str, owner_user_id: int) -> None:
    key = (scope, owner_user_id)
    if key in _INSTALLMENT_READY:
        return

    with db() as conn:
        row = conn.execute(
            """
            SELECT id, is_locked FROM categories
            WHERE scope=? AND owner_user_id=? AND grp='personal_out' AND name=?
            """,
            (scope, owner_user_id, INSTALLMENT_NAME),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO categories(scope, owner_user_id, grp, name, is_locked)
                VALUES(?, ?, 'personal_out', ?, 1)
                """,
                (scope, owner_user_id, INSTALLMENT_NAME),
            )
        elif int(row["is_locked"]) != 1:
            conn.execute("UPDATE categories SET is_locked=1 WHERE id=?", (row["id"],))
        conn.commit()

    _INSTALLMENT_READY.add(key)

def find_categories_by_name(scope: str, owner: int, name: str) -> List[sqlite3.Row]:
    """Every category with this exact name, across all four groups."""
    cleaned = (name or "").strip()
    if not cleaned:
        return []
    with db() as conn:
        return list(conn.execute(
            """
            SELECT id, grp, name FROM categories
            WHERE scope=? AND owner_user_id=? AND name=? COLLATE NOCASE
            ORDER BY grp
            """,
            (scope, owner, cleaned),
        ).fetchall())

def fetch_cats(scope: str, owner: int, grp: str) -> List[sqlite3.Row]:
    with db() as conn:
        return list(
            conn.execute(
                """
                SELECT id, name, is_locked
                FROM categories
                WHERE scope=? AND owner_user_id=? AND grp=?
                ORDER BY is_locked DESC, name COLLATE NOCASE
                """,
                (scope, owner, grp),
            ).fetchall()
        )

def build_cat_kb(scope: str, owner: int, grp: str, page: int = 0) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    cats = fetch_cats(scope, owner, grp)

    page = max(0, min(page, max(0, (len(cats) - 1) // CAT_PAGE_SIZE)))
    window = cats[page * CAT_PAGE_SIZE:(page + 1) * CAT_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton("➕ افزودن دسته", callback_data=f"{CB_CT}:add:{grp}")])

    for r in window:
        nm = r["name"]
        locked = int(r["is_locked"]) == 1
        is_install = (grp == "personal_out" and nm == INSTALLMENT_NAME and locked)

        if is_install:
            rows.append([InlineKeyboardButton(f"🔒 {nm}", callback_data=f"{CB_CT}:noop")])
        else:
            rows.append(
                [
                    InlineKeyboardButton(nm, callback_data=f"{CB_CT}:noop"),
                    InlineKeyboardButton("🗑 حذف", callback_data=f"{CB_CT}:del:{r['id']}"),
                    InlineKeyboardButton("✏️ ویرایش", callback_data=f"{CB_CT}:ren:{r['id']}"),
                ]
            )

    nav = page_nav_row(f"{CB_CT}:page:{grp}:", page, len(cats), CAT_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"{CB_ST}:cats")])
    return InlineKeyboardMarkup(rows)

# =========================
# Transaction flow
# =========================
def cat_pick_keyboard(scope: str, owner: int, grp: str, back_cb: str, page: int = 0) -> InlineKeyboardMarkup:
    ensure_installment(scope, owner)
    cats = fetch_cats(scope, owner, grp)

    page = max(0, min(page, max(0, (len(cats) - 1) // CAT_PAGE_SIZE)))
    window = cats[page * CAT_PAGE_SIZE:(page + 1) * CAT_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = []
    for r in window:
        rows.append([InlineKeyboardButton(r["name"], callback_data=f"{CB_TX}:cat:{r['id']}")])

    nav = page_nav_row(f"{CB_TX}:catp:", page, len(cats), CAT_PAGE_SIZE)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("➕ افزودن دسته جدید", callback_data=f"{CB_TX}:cat_add")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)
