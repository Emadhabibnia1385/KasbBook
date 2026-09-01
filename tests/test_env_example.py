"""`.env.example` must describe the variables the code actually reads.

This file drifted all the way through a rewrite without anyone noticing: it
still listed BOT_TOKEN, ADMIN_CHAT_ID and ADMIN_USERNAME from the first
generation, none of which exist any more. Copying it to `.env` produced a
configuration where every single value was ignored, and the only symptom was
the bot refusing to start over a token that had been "set".

Nothing imports an example file, so nothing could fail. Hence this test.
"""

from __future__ import annotations

import ast
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = REPO / ".env.example"

# Read by the scripts, not the application, and not something a person edits.
OPERATIONAL = {
    "KASBBOOK_HOME",
    "KASBBOOK_REPO",
    "KASBBOOK_BRANCH",
    "KASBBOOK_BACKUP_DIR",
    "KASBBOOK_BACKUP_KEEP",
    "KASBBOOK_UPDATE_DETACHED",
    "KASBBOOK_TEST_POSTGRES_URL",
}

# The helpers that reach the environment. Anything else is not configuration.
READERS = {"_env", "getenv"}


def _variables_the_code_reads() -> set[str]:
    """Every environment variable name passed to a reader, found on the AST.

    The AST rather than a grep: a name inside a docstring or an error message
    is not a variable being read, and this file exists precisely because
    text-level agreement is not the same as real agreement.
    """
    found: set[str] = set()
    for path in [*(REPO / "src").rglob("*.py"), *(REPO / "apps").rglob("*.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name)
                else None
            )
            # os.environ.get("X") reads as a `get` on a Subscript-free
            # attribute chain; os.getenv("X") as `getenv`; ours as `_env`.
            if name in READERS or (
                name == "get"
                and isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "environ"
            ):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return {n for n in found if n.isupper()} - OPERATIONAL


def _variables_the_example_documents() -> set[str]:
    """Names assigned in the example, whether commented out or not.

    A commented-out optional is still documented — the point is that somebody
    reading the file learns the variable exists.
    """
    text = EXAMPLE.read_text(encoding="utf-8")
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, re.MULTILINE))


def test_every_variable_the_code_reads_is_in_the_example():
    missing = _variables_the_code_reads() - _variables_the_example_documents()
    assert not missing, (
        "these are read by the code and absent from .env.example, so nobody "
        f"copying it would know to set them: {sorted(missing)}"
    )


def test_the_example_invents_no_variables():
    """The failure that actually happened: names nothing reads."""
    unknown = _variables_the_example_documents() - _variables_the_code_reads()
    assert not unknown, (
        "these are in .env.example and nothing reads them, so setting them "
        f"does nothing and the file is lying: {sorted(unknown)}"
    )


def test_no_secret_is_filled_in():
    """An example with a real token in it is a leak waiting to be committed."""
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if any(w in name for w in ("TOKEN", "SECRET", "KEY", "PASSWORD")):
            assert not value.strip(), f"{name} has a value in .env.example"
