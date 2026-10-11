"""The screens package keeps the contract screens.py had, and its own shape.

screens.py was one file of 2,600 lines. It is now one module per feature plus
`common`. These tests are what keep that true:
- nothing the old module offered went missing, and no name is defined twice;
- the package's internal imports form a star around `common`, with no cycle;
- importing it touches nothing but itself;
- every button and every screen still obeys the rules a messenger and a
  Persian reader impose.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/kasbbook/bot"
PKG = BOT / "screens"

pytestmark = pytest.mark.asyncio

# Everything screens.py defined at the top level when it was split (145
# functions, 20 constants), plus Button, which callers reached through it.
# Frozen: a name may be added to the package, never quietly lost.
PREVIOUS_EXPORTS = (
    "RLM", "BOOK_LABELS", "PROVIDER_LABELS", "Screen", "rtl", "_problem",
    "with_notice", "fmt", "WHOLE_UNIT_CURRENCIES", "fmt_currency", "welcome",
    "not_linked", "main_menu", "_book_names", "_book_buttons", "book_list",
    "book_created", "pick_book", "new_book_type", "ask_book_name", "ENTRY_TYPES",
    "TYPES_FOR_BOOK", "SECTION_ORDER", "DAY_PAGE", "day_token", "_entry_code",
    "_pairs", "_book_mark", "entry_label", "tx_home", "pick_date", "ask_date",
    "pick_type", "daily_pick_type", "_day_summary", "daily_view", "ask_category",
    "ask_amount", "transaction_saved", "report_menu", "book_report", "account_created",
    "account_panel", "_reading", "api_panel", "api_key_created", "ask_email",
    "ask_phone", "ask_current_password", "ask_new_password", "ask_display_name",
    "ask_timezone", "session_list", "CLOSE_WORD", "confirm_close", "ask_close_word",
    "account_closed", "identity_list", "period_menu", "period_report",
    "category_breakdown", "comparison_line", "_quick_facts", "quick_pick_book",
    "quick_pick_flow", "stale", "cancelled", "unreadable_line", "_UNCLEAR",
    "unclear_reason", "unclear_line", "error", "_ENGLISH_ERRORS", "user_message",
    "book_menu", "_bar", "budget_list", "budget_pick_kind", "budget_ask_target",
    "budget_ask_amount", "debt_list", "debt_ask_person", "debt_pick_direction",
    "debt_ask_amount", "debt_ask_due", "loan_list", "loan_detail", "loan_ask_title",
    "loan_ask_amount", "loan_ask_count", "loan_ask_start", "debt_confirm_settle",
    "confirm_delete", "transaction_list", "RECEIPT_KINDS", "_receipt_line",
    "transaction_detail", "ask_receipt", "ask_description",
    "ask_description_with_rate", "category_list", "ask_category_name",
    "ask_category_flow", "ask_teammate", "team_invitation", "invitation_inbox",
    "ask_login_destination", "ask_login_code", "login_proof", "ask_search",
    "search_results", "RECURRING_PERIOD_LABELS", "recurring_list",
    "recurring_pick_flow", "recurring_ask_category", "recurring_ask_amount",
    "recurring_pick_period", "recurring_ask_start", "reminder_settings", "ask_hour",
    "ask_days", "COST_POLICY_LABELS", "cost_policy_pick", "FUND_LABELS",
    "BASIS_LABELS", "fund_list", "fund_ask_name", "fund_pick_kind", "fund_detail",
    "rule_pick_basis", "rule_ask_value", "PERIOD_LABELS", "period_dates",
    "period_ask_date", "period_list", "period_detail", "confirm_close_period",
    "payslip_list", "_payment_amount", "payslip_detail", "payslip_ask_amount",
    "adjustment_list", "adjustment_pick_member", "adjustment_ask_value",
    "adjustment_ask_reason", "SHARE_BASIS_LABELS", "MEASURED_BASES", "share_list",
    "share_pick_basis", "share_ask_value", "performance_list", "performance_ask_value",
    "no_shares_defined", "currency_home", "currency_settings",
    "conversion_pick_source", "conversion_ask_amount", "conversion_pick_target",
    "conversion_ask_target_amount", "conversion_ask_base_value", "conversion_saved",
    "pick_currency", "ask_rate", "payslip_pick_currency", "payslip_ask_rate",
    "Button",
)


def _modules():
    return {p.stem: p for p in sorted(PKG.glob("*.py")) if p.stem != "__init__"}


def _defined(path: Path):
    names = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names += [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


# --------------------------------------------------------------- the contract
async def test_everything_screens_py_offered_is_still_there():
    from kasbbook.bot import screens

    assert len(PREVIOUS_EXPORTS) == len(set(PREVIOUS_EXPORTS)) == 166
    missing = [name for name in PREVIOUS_EXPORTS if not hasattr(screens, name)]
    assert not missing, f"lost in the split: {missing}"
    assert set(PREVIOUS_EXPORTS) <= set(screens.__all__)


async def test_every_name_is_defined_once_and_exported_once():
    from kasbbook.bot import screens

    where = {}
    for module, path in _modules().items():
        for name in _defined(path):
            assert name not in where, f"{name} defined in both {where[name]} and {module}"
            where[name] = module

    assert len(screens.__all__) == len(set(screens.__all__)), "a name exported twice"
    exported = set(screens.__all__) - {"Button"}
    assert exported == set(where), (
        f"defined but not exported: {sorted(set(where) - exported)}; "
        f"exported but not defined: {sorted(exported - set(where))}"
    )
    # Each export is the very object its owning module defines.
    for name, module in where.items():
        owner = importlib.import_module(f"kasbbook.bot.screens.{module}")
        assert getattr(screens, name) is getattr(owner, name), name


# ------------------------------------------------------------------ the shape
def _sibling_imports(path: Path):
    """Modules of this package a file imports, at any depth, relative or absolute."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module:
                found.add(node.module.split(".")[0])
            elif node.level == 0 and (node.module or "").startswith("kasbbook.bot.screens."):
                found.add(node.module.split(".")[3])
    return found


async def test_the_package_is_a_star_around_common_with_no_cycle():
    for module, path in _modules().items():
        siblings = _sibling_imports(path)
        if module == "common":
            assert not siblings, f"common must import no feature's screens: {siblings}"
        else:
            assert siblings <= {"common"}, f"{module} imports another feature's screens: {siblings}"


async def test_screens_never_reach_back_into_the_bot_or_the_database():
    """Screens are pure: data in, text and buttons out. No feature, no session."""
    forbidden = re.compile(
        r"from \.\.(features|conversation|state)\b|sqlalchemy\.ext|AsyncSession"
        r"|shared\.database|from \.\.\.adapters\.(telegram|bale|rubika|botapi)"
    )
    for module, path in _modules().items():
        hits = forbidden.findall(path.read_text(encoding="utf-8"))
        assert not hits, f"{module}: {hits}"


async def test_every_relative_import_points_at_a_real_module():
    """The package sits one level deeper than screens.py did; nothing may dangle."""
    for path in PKG.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                parts = "kasbbook.bot.screens".split(".")
                base = ".".join(parts[: len(parts) - (node.level - 1)])
                target = base + ("." + node.module if node.module else "")
                assert importlib.util.find_spec(target) is not None, \
                    f"{path.name}:{node.lineno} imports {target}, which does not exist"


async def test_importing_the_package_has_no_side_effects(tmp_path):
    """In a fresh interpreter, in an empty directory: nothing printed, nothing
    written, none of the bot loaded, and nothing that could connect anywhere.

    The models are imported (a screen takes a Book), and they declare their
    tables on shared.database's Base - which defines classes and a naming
    convention and opens nothing. A connection would need a driver, Redis or
    an HTTP client, so those are what must stay unloaded.
    """
    probe = "\n".join([
        "import sys",
        f"sys.path.insert(0, {str(ROOT / 'src')!r})",
        "import kasbbook.bot.screens as s",
        "prefixes = ('kasbbook.bot.features', 'kasbbook.bot.conversation',",
        "            'kasbbook.bot.state', 'kasbbook.adapters.telegram',",
        "            'kasbbook.adapters.bale', 'kasbbook.adapters.rubika',",
        "            'aiosqlite', 'asyncpg', 'psycopg', 'redis', 'httpx')",
        "loaded = sorted(m for m in sys.modules if m.startswith(prefixes))",
        "assert not loaded, loaded",
        "assert len(s.__all__) > 100",
    ])
    result = subprocess.run([sys.executable, "-I", "-c", probe], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------- the buttons
# The longest value each placeholder in a callback can take:
# - a UUID is 36 bytes;
# - a day token is yyyymmdd;
# - a currency code is at most its column's 8;
# - a page or a count fits in 4 digits;
# - a report spec is at most "m:1405:07".
# A placeholder not listed here fails the test, so a new one is sized on purpose.
PLACEHOLDER_BYTES = [
    (re.compile(r"\bid$|_id$|\.id\b"), 36),
    (re.compile(r"^view$"), 36),                      # "a", or a book's UUID
    (re.compile(r"^(token|day)$|^day_token\("), 8),
    (re.compile(r"code$"), 8),
    (re.compile(r"^nonce$"), 6),
    (re.compile(r"^spec$"), 10),
    (re.compile(r"^(page|index)( [+-] 1)?$|paid_count$"), 4),
    (re.compile(r"year$"), 4),
    (re.compile(r"month:02d$"), 2),
    (re.compile(r"^origin$"), 1),                     # "a" or "b"
    (re.compile(r"^tail$"), 2),                       # "" or ":a" / ":b"
]


def _worst_case(template: str) -> int:
    def size(expr: str) -> int:
        for pattern, length in PLACEHOLDER_BYTES:
            if pattern.search(expr):
                return length
        raise AssertionError(
            f"unsized callback placeholder {{{expr}}}: add it to PLACEHOLDER_BYTES"
        )

    fixed = re.sub(r"\{[^}]*\}", "", template)
    placeholders = re.findall(r"\{([^}]*)\}", template)
    return len(fixed.encode("utf-8")) + sum(size(expr) for expr in placeholders)


def _callback_templates():
    for path in [*PKG.glob("*.py"), *(BOT / "features").glob("*.py"), BOT / "conversation.py"]:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in re.finditer(r'data=f?"([^"]*)"', line):
                yield path.relative_to(BOT).as_posix(), line_no, match.group(1)


async def test_no_callback_can_outgrow_the_64_bytes_a_messenger_accepts():
    """Telegram refuses the whole message, not the button, past 64 bytes."""
    from kasbbook.adapters.base import CALLBACK_DATA_LIMIT, Button

    templates = list(_callback_templates())
    assert len(templates) > 150, "found almost no buttons: has the scan gone stale?"
    over = [(where, n, t, _worst_case(t)) for where, n, t in templates
            if _worst_case(t) > CALLBACK_DATA_LIMIT]
    assert not over, f"callbacks that can exceed {CALLBACK_DATA_LIMIT} bytes: {over}"

    # And the guard at construction holds for whatever the scan cannot see.
    with pytest.raises(ValueError):
        Button("x", data="x" * (CALLBACK_DATA_LIMIT + 1))


# ------------------------------------------------- Persian, RTL, no English
PERSIAN = re.compile("[؀-ۿ]")


def _literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    if isinstance(node, ast.BinOp):
        return (_literal(node.left) or "") + (_literal(node.right) or "")
    return None


def _bot_trees():
    for path in [*PKG.glob("*.py"), *(BOT / "features").glob("*.py"), BOT / "conversation.py"]:
        yield path.relative_to(BOT).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


async def test_every_screen_returns_persian_text_through_rtl():
    """Persian returned raw starts left-to-right in some clients: a number or a
    Latin word at the front of a line jumps to the wrong side. rtl() is the fix."""
    raw = []
    for where, tree in _bot_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple) and node.value.elts:
                text = _literal(node.value.elts[0])
                if text and PERSIAN.search(text):
                    raw.append((where, node.lineno, text[:40]))
    assert not raw, f"screens returning Persian without rtl(): {raw}"


async def test_no_error_shown_to_a_person_is_written_in_english():
    english = []
    for where, tree in _bot_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name != "error":
                continue
            text = _literal(node.args[0])
            if text is not None and re.search(r"\b[A-Za-z]{3,}\b", text) and not PERSIAN.search(text):
                english.append((where, node.lineno, text[:60]))
    assert not english, f"English reaching a person: {english}"
