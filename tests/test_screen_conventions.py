"""The layout and navigation conventions the screens package just adopted.

`test_screens_architecture.py` pins what the package *is*: one module per
feature, a star around `common`, screens that stay pure, callbacks that fit in
the 64 bytes a messenger allows. This file is its sibling for what the screens
*look like*, now that three helpers in `common` have taken over the two
decisions every screen used to make by hand:

- `rows_of()` lays buttons out, never more than three to a row;
- `back_row()` and `cancel_row()` own the one glyph and the one word that each
  way out of a screen gets.

Both helpers were written to end drift that had already shipped, and both are
cheap to lose again, because the next screen gets written by copying the one
beside it. A convention nothing checks lasts until the next feature.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src/kasbbook/bot/screens"

pytestmark = pytest.mark.asyncio


def _modules():
    return {p.stem: p for p in sorted(PKG.glob("*.py")) if p.stem != "__init__"}


def _literal(node):
    """The part of a label that is written in the source, or None.

    An f-string contributes only its constant pieces, which is what both tests
    below want: a label assembled from a book's name at runtime is not a
    decision anyone made in the source, so there is nothing to pin.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    if isinstance(node, ast.BinOp):
        return (_literal(node.left) or "") + (_literal(node.right) or "")
    return None


def _is_button(node) -> bool:
    return isinstance(node, ast.Call) and (
        getattr(node.func, "id", None) == "Button"
        or getattr(node.func, "attr", None) == "Button"
    )


def _is_row(node) -> bool:
    """A list literal holding nothing but Buttons."""
    return isinstance(node, ast.List) and bool(node.elts) and all(
        _is_button(e) for e in node.elts
    )


def _rows(tree):
    """Every list of Buttons that is written where a *row* goes.

    Position is what decides it, not shape. A list of Buttons is a row when it
    sits inside the keyboard that encloses it, or when it is appended to one.
    A list of Buttons handed to `rows_of()`, or bound to a name and chunked
    later, is a *sequence* — `book_menu`'s nine peers and `ask_timezone`'s five
    cities are written as one list each and come out two to a row — so reading
    position rather than shape is what keeps those out without a special case.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            yield from (e for e in node.elts if _is_row(e))
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", None) == "append"
            and len(node.args) == 1
            and _is_row(node.args[0])
        ):
            yield node.args[0]


# ------------------------------------------------------------------- layout
async def test_no_row_is_wider_than_three_buttons():
    """Refuses a hand-written row of four or more buttons.

    A Persian label is a word, not an abbreviation, so the fourth one wraps or
    is cut off on a phone. `transaction_detail` was the only four-wide row the
    package ever had — «ویرایش دسته», «ویرایش مبلغ», «ویرایش توضیحات»,
    «ویرایش تاریخ», four labels of eleven to thirteen characters in one row —
    and it is 2x2 now, with the repeated word carried by the ✏️ this codebase
    already uses for editing.

    Only a hand-written row can break this. `rows_of()` clamps `per_row` to
    three whatever it is asked for, so what it lays out needs no guard; what
    someone writes between two brackets does.
    """
    rows = [(mod, r) for mod, path in _modules().items()
            for r in _rows(ast.parse(path.read_text(encoding="utf-8")))]

    too_wide = [
        (f"{mod}.py:{r.lineno}", len(r.elts),
         [_literal(e.args[0]) if e.args else "?" for e in r.elts])
        for mod, r in rows if len(r.elts) > 3
    ]
    assert not too_wide, f"rows wider than three buttons: {too_wide}"

    # The scan reads one AST shape, so it would go quiet rather than wrong if
    # the screens stopped writing keyboards that way. A row of two or three is
    # the only shape that could ever break the rule above, so some of those
    # must still be in sight for the assertion to have meant anything.
    assert len(rows) > 50, f"found almost no rows ({len(rows)}): has the scan gone stale?"
    multi = [r for _, r in rows if len(r.elts) > 1]
    assert len(multi) >= 10, f"found almost no multi-button rows ({len(multi)})"


# --------------------------------------------------------------- navigation
# Every word a way out of a screen can be called. `بازگشت` and `انصراف` are the
# two the helpers write; `منصرف`, `منوی اصلی` and `خانه` are here so a third
# word for the same action cannot arrive quietly the way the second glyph did.
NAV_WORDS = ("بازگشت", "انصراف", "منصرف", "منوی اصلی", "خانه")


def _nav_labels(mod: str, path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not (_is_button(node) and node.args):
            continue
        label = _literal(node.args[0])
        if label and any(word in label for word in NAV_WORDS):
            yield f"{mod}.py:{node.lineno}", label


# RED when written, because of `⬅️ منوی اصلی` at transactions.py:390
# (`transaction_saved`) and wallet.py:214 (`conversion_saved`) — both owned by
# other agents mid-flight, and both a case the helpers cannot express: "go
# home" is a third navigation action, and `back_row("nav:home")` would say
# «⬅️ بازگشت», which is a different word, not a reformatting.
#
# To delete this marker, one of two things has to land, and either one is a
# decision about the copy rather than a rename:
#   - `common` grows a `home_row()` beside `back_row()`/`cancel_row()`, owning
#     «⬅️ منوی اصلی» the same way, and those two sites plus `error()` call it; or
#   - both sites accept that the way out of a saved-confirmation screen is
#     بازگشت, and become `back_row("nav:home")`.
# Nothing else in the package is in the way: the rule is green for account,
# books, payroll, planning, reports, and for every other label in transactions
# and wallet.
# Was xfail while two screens wrote «⬅️ منوی اصلی» by hand and had nothing to
# call: «go home» is a third action, and `back_row("nav:home")` would have said
# «بازگشت» on a screen that returns nowhere. `common.home_row()` closed that
# gap, both sites now call it, and the rule is a hard guard.
async def test_navigation_labels_are_written_only_in_common():
    """Refuses a back, cancel or home label spelled out anywhere but `common`.

    These were written by hand at 131 of the package's buttons, and the glyph
    had come to track the module rather than the action: planning and books
    said «↩️ انصراف» where payroll, account and wallet said «⬅️ انصراف», and
    transactions managed both inside one flow. A reader learns a glyph, not a
    module, so the same way out has to look the same everywhere — which means
    one module writes it and every screen calls that module.
    """
    offenders = [
        (where, label)
        for mod, path in _modules().items() if mod != "common"
        for where, label in _nav_labels(mod, path)
    ]
    assert not offenders, (
        "navigation labels written outside common.py — call back_row(), "
        f"cancel_row() or confirm_delete() instead: {offenders}"
    )


async def test_common_still_writes_the_words_this_file_is_watching():
    """Keeps NAV_WORDS honest: the guard above is a word list, and a word list
    goes blind the moment the copy moves on without it. If `common` stopped
    spelling these words, the test would pass by having nothing left to find
    rather than by every screen behaving.
    """
    found = list(_nav_labels("common", _modules()["common"]))
    assert len(found) >= 3, (
        f"common.py writes almost none of NAV_WORDS ({found}): the word list is "
        "stale, so the guard above is watching for nothing"
    )


# ------------------------------------------- what is deliberately not guarded
# There is no test here for "every list screen has an empty branch", though the
# convention is real: a screen that renders a title and a lone back button when
# its sequence is empty teaches nothing, and `identity_list`, `session_list`,
# `category_list` and `budget_list` all now spend their empty branch saying
# what the thing is for and where it comes from.
#
# It was tried and dropped, because the two signals available to an AST are
# both wrong about code that is right, in opposite directions:
#
#   - "a `*_list` function must test its sequence parameter for falsiness"
#     fails `session_list`, which is correct: it tests `rows`, bound from
#     `list(sessions)` one line earlier. It also *passes* `identity_list` for
#     the wrong reason, matching `current` rather than the sequence. Finding
#     the real sequence means following aliases (`rows = list(sessions)`) and
#     derived comprehensions (`performance_list` branches on `measured`,
#     `share_list` builds `unset`) — data flow, not a walk. And which parameter
#     even is the sequence is not in the name: `share_list(book, members,
#     names, rules)`.
#
#   - "a `*_list` function must return early" fails `category_list`, which
#     picks its body with a conditional expression, and `budget_list`, which
#     assigns `text` in an if/else and returns once at the end. Six of the
#     fifteen list screens are shaped that way.
#
# An empty branch is written at least four ways here, and all four are fine.
# A guard that red-flags four correct screens to catch one would train people
# to ignore it, and in this repo a failing guard is supposed to mean you are
# wrong. `payroll.share_list` does look like the one genuine gap — it has no
# empty branch at all — but a book with zero members may not be reachable, and
# a guard whose only catch is unreachable is not worth the false alarms.
# Checking this honestly means rendering the screens with empty sequences and
# reading what comes back, which is a different kind of test than this file.
