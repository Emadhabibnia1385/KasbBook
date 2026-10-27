"""The Persian copy rules, applied to the half of the surface the bot's guard cannot see.

`tests/test_bot_ux_fixes.py` holds these rules — one word per concept, the ZWNJ
half-space, ASCII digits — over `bot/`. But `screens.user_message()` returns a
service's own sentence *verbatim* when it contains any Persian character, and
`Conversation.handle` renders it for every `KasbBookError`. So each
`ValidationError("…")` a service raises is user-facing copy with the same
rules on it, and until this file nothing checked it.

The surface is found rather than guessed. An AST walk collects the first
argument of every call to a class `shared/errors.py` defines, which is exactly
what reaches `user_message()`. A regex over the sources would also sweep up
comments and docstrings, which no one reads, and would miss a message held in
a module constant — `shared/money.py` keeps its longest one that way.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/kasbbook"

# The service layer only. `bot/` is covered by test_bot_ux_fixes, and `api/`
# answers the web panel with an HTTP status rather than through user_message().
SERVICE_DIRS = ("modules", "shared")

PERSIAN_LETTER = "[؀-ۿ]"
PERSIAN_DIGIT = re.compile("[۰-۹٠-٩]")


class Message(NamedTuple):
    """One sentence a person can be shown, and where it was written."""

    where: str
    error: str
    text: str


@lru_cache(maxsize=1)
def _error_types() -> frozenset:
    """Every error this system raises on purpose; `user_message` renders them all."""
    tree = ast.parse((SRC / "shared/errors.py").read_text(encoding="utf-8"))
    return frozenset(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))


def _string_constants(tree: ast.AST) -> Dict[str, str]:
    """Names bound to a string literal, so a message held in a constant is still read."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Constant) \
           and isinstance(node.value.value, str):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value.value
    return found


def _interpolated(value: ast.AST) -> str:
    """What stands in for a computed part of the sentence.

    `{fa}` marks a number rendered by payroll's `_fa_number`, because a literal
    digit sharing a sentence with one has to read the same way. Any string
    literal inside the expression — a join's separator, say — is kept, since a
    person reads that too; the format spec is not, since nobody sees `,f`.
    """
    calls = {call.func.id for call in ast.walk(value)
             if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)}
    if "_fa_number" in calls:
        return "{fa}"
    literals = [node.value for node in ast.walk(value)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    return "{" + "".join(literals) + "}"


def _render(node: ast.AST, constants: Dict[str, str]) -> str:
    """The sentence as a person sees it, computed parts marked rather than guessed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, "")
    if isinstance(node, ast.JoinedStr):
        parts = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            elif isinstance(piece, ast.FormattedValue):
                parts.append(_interpolated(piece.value))
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _render(node.left, constants) + _render(node.right, constants)
    return ""


@lru_cache(maxsize=1)
def _service_messages() -> tuple:
    """Every Persian sentence the service layer can put in front of a person."""
    errors = _error_types()
    messages: List[Message] = []
    for directory in SERVICE_DIRS:
        for path in sorted((SRC / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            constants = _string_constants(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name not in errors:
                    continue
                text = _render(node.args[0], constants)
                if re.search(PERSIAN_LETTER, text):
                    where = f"{path.relative_to(SRC).as_posix()}:{node.lineno}"
                    messages.append(Message(where, name, text))
    return tuple(messages)


def test_the_guard_can_still_see_the_service_layers_copy():
    """A walk that silently finds nothing would pass every rule below.

    The floor is deliberately far under the real count, which grows: it fails
    when the surface collapses — services raising through a helper this walk
    does not follow, say — rather than every time a message is added.
    """
    messages = _service_messages()
    modules = {message.where.split(":")[0] for message in messages}
    assert len(messages) > 80, f"only {len(messages)} Persian service messages found"
    assert len(modules) > 8, f"only {len(modules)} files contribute copy: {sorted(modules)}"


def test_the_vocabulary_is_one_word_per_concept():
    """The same list test_bot_ux_fixes holds over the bot: one word, one concept."""
    forbidden = {
        "دسته‌بندی": "the word is «دسته»",
        "ثبت تکی": "it is «ثبت تراکنش»",
        "پاک کردن": "it is «حذف»",
        "حساب من": "it is «حساب کاربری»",
        "لغو آخرین": "it is «برگرداندن»",
        "به من بدهکار است": "it is «طلب من»",
    }
    for message in _service_messages():
        for word, why in forbidden.items():
            assert word not in message.text, f"{message.where}: «{word}» — {why}"


def test_persian_is_typed_with_a_half_space_and_the_right_letters():
    for message in _service_messages():
        assert not re.search(f"(?<!{PERSIAN_LETTER})ن?می {PERSIAN_LETTER}", message.text), \
            f"{message.where}: می without ZWNJ — {message.text}"
        assert "ي" not in message.text and "ك" not in message.text, \
            f"{message.where}: Arabic ye/kaf — {message.text}"


# A number a person reads is written in ASCII digits everywhere in this product
# — «حداکثر 500 حرف», «مثلاً: 10», «مثلاً 24» — with one deliberate exception.
# `payroll/service.py` renders a percentage through `_fa_number`, whose comment
# says why: "A percentage as a person reads it in a refusal: ۳۰ or ۳۲٫۵, never
# 30.0000". That is live and pinned — three callers build refusals with it, and
# three assertions hard-require its output: test_payroll asserts «۳۰» and
# «۶۰۰۰۰۰۰» in a refusal, test_bot_payroll_treasury asserts «۴۰» in a reply,
# none of them accepting the ASCII form.
#
# So the exemption is these sentences by name, not payroll as a module: a new
# Persian digit anywhere — payroll included — still fails, and rewording one of
# these re-opens the decision instead of carrying it along silently.
PERSIAN_DIGITS_ALLOWED = {
    # The ceiling is read beside the total `_fa_number` just printed; writing
    # one of the two in ASCII would put «۱۲۰ درصد» and «100» in one sentence.
    "جمع سهم‌های درصدی اعضا {fa} درصد است؛ پیش از محاسبه آن را به ۱۰۰ یا کمتر برسانید":
        "shares the sentence with _fa_number's own reading of the total",
    "جمع سهم‌های درصدی از ۱۰۰ بیشتر می‌شود؛ حداکثر {fa} درصد آزاد است":
        "shares the sentence with _fa_number's reading of the free room",
    # `set_share` raises this and the one above a few lines apart, about the
    # same ceiling. Treasury's rule percentages raise the identical sentence,
    # and one refusal of one concept should not be spelled two ways, so the
    # exemption is the sentence rather than the file it is written in.
    "درصد نمی‌تواند بیشتر از ۱۰۰ باشد":
        "the percent ceiling, raised beside _fa_number in payroll and verbatim in treasury",
    # These last two are NOT the percentage decision: a name limit and a rate
    # floor, neither computed nor beside anything computed. The product writes
    # both concepts in ASCII elsewhere — bot/screens/transactions.py says
    # «حداکثر 500 حرف» and bot/features/books.py formats its own limit — so
    # they are listed to leave payroll untouched here, not to bless them.
    "نام دوره حداکثر ۴۰ حرف است.":
        "a character limit, written 500/40 in ASCII in the bot's own copy",
    "نرخ تبدیل باید مثبت باشد (دست‌کم ۰٫۰۰۰۱).":
        "a rate floor, not a percentage _fa_number would print",
}


def test_user_facing_digits_are_written_one_way():
    for message in _service_messages():
        if not PERSIAN_DIGIT.search(message.text):
            continue
        assert message.text in PERSIAN_DIGITS_ALLOWED, \
            f"{message.where}: Persian digits in «{message.text}» — write them in ASCII"


def test_every_allowed_persian_number_is_still_raised_somewhere():
    """An exemption nothing uses is an exemption nobody will notice is wrong."""
    live = {message.text for message in _service_messages()}
    for text in PERSIAN_DIGITS_ALLOWED:
        assert text in live, f"no service raises «{text}» any more; drop its exemption"
