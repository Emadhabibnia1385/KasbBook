"""The installer must not read answers from stdin.

The documented way to install is `curl ... | sudo bash`, and under a pipe stdin
IS the script. A plain `read` there does not wait for anybody — it consumes the
next line of source as the answer, and that line then never executes. It did
exactly that: .env came out holding

    TELEGRAM_BOT_TOKEN=[ -n "$TOKEN" ] || die "a bot token is required"

with the check that would have caught it eaten as the answer, and the installer
exiting zero. The headline command in both READMEs had never worked.

These tests run the real helpers under a real pipe.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "lib.sh"


def _piped(script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run `script` the way the README says to: piped into bash, no terminal."""
    return subprocess.run(
        ["bash"],
        input=script,
        text=True,
        capture_output=True,
        # `input=` gives bash its script down a pipe, which is the whole point:
        # it reproduces `curl ... | bash`, where stdin is the script itself.
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/tmp", **(env or {})},
        timeout=60,
    )


PREAMBLE = f"""
set -euo pipefail
source {LIB}
"""


def test_a_prompt_does_not_eat_the_next_line_of_the_script():
    """The failure itself: the line after the prompt must still run."""
    result = _piped(PREAMBLE + """
ask ANSWER "  question: "
echo "THIS LINE MUST RUN"
echo "answer=[${ANSWER}]"
""")
    assert "THIS LINE MUST RUN" in result.stdout, result.stdout + result.stderr
    assert "answer=[]" in result.stdout, (
        "the prompt consumed something from stdin instead of leaving it empty: "
        + result.stdout
    )


def test_an_environment_variable_answers_without_a_terminal():
    """How a piped install is meant to be driven."""
    result = _piped(PREAMBLE + 'ask TOKEN "  token: "\necho "got=[$TOKEN]"',
                    env={"TOKEN": "123456:AAH-example"})
    assert "got=[123456:AAH-example]" in result.stdout, result.stdout + result.stderr


def test_no_terminal_produces_no_device_noise():
    """A person being told what to do should not also be told about /dev/tty."""
    result = _piped(PREAMBLE + 'ask X "  q: "\necho done')
    assert "Device not configured" not in result.stderr, result.stderr
    assert "/dev/tty" not in result.stderr, result.stderr


def test_a_value_carrying_shell_is_refused():
    """Exactly what the bug produced, and .env is an unquoted heredoc."""
    for bad in ['[ -n "$TOKEN" ] || die "x"', "with space", "with$dollar", "back`tick"]:
        result = _piped(PREAMBLE + f'sane {bad!r} "TELEGRAM_BOT_TOKEN"\necho REACHED')
        assert "REACHED" not in result.stdout, f"{bad!r} was accepted"
        assert result.returncode != 0, f"{bad!r} did not fail the install"


def test_a_real_token_passes():
    result = _piped(PREAMBLE + 'sane "123456:AAH-abc_DEF-123" "T"\necho REACHED')
    assert "REACHED" in result.stdout, result.stdout + result.stderr


def test_urls_are_normalised_and_plain_http_refused():
    cases = {
        "example.com": "https://example.com",
        "https://a.example.com/": "https://a.example.com",
        "https://a.example.com": "https://a.example.com",
        "": "",
    }
    for given, expected in cases.items():
        result = _piped(PREAMBLE + f'printf "[%s]" "$(normalise_url {given!r})"')
        assert f"[{expected}]" in result.stdout, f"{given!r} → {result.stdout}"

    result = _piped(PREAMBLE + 'normalise_url "http://insecure.example.com"\necho REACHED')
    assert "REACHED" not in result.stdout, "plain http was accepted"


def test_the_installer_never_reads_from_stdin():
    """The class, not the instance: no bare `read` anywhere in the scripts."""
    offenders = []
    for path in sorted((REPO / "scripts").glob("*.sh")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            # `read -p` is a prompt. A bare `read` in a `while` is a loop
            # over a pipe, which is a different thing and fine.
            if stripped.startswith("#") or not re.search(r"\bread\b.*-r?p\b|\bread\s+-r\s+-p\b", stripped):
                continue
            if '< "$KASBBOOK_TTY"' not in stripped:
                offenders.append(f"{path.name}:{i}: {stripped}")
    assert not offenders, (
        "these read from stdin, which under `curl | bash` is the script itself; "
        f"use `ask` instead: {offenders}"
    )
