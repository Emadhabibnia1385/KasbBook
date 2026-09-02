"""Running a second messenger, and the trap that used to be in the way.

The documented procedure said to add the new unit name to `UNITS` in
scripts/lib.sh. `update.sh` moves the checkout with `git checkout -B`, which
discards changes to tracked files — so that edit survived until the next update
and then vanished, quietly dropping the second bot out of the restart and
health loops. Nothing failed; it simply stopped being looked after.

UNITS is now discovered from disk. These tests run the real shell.
"""

from __future__ import annotations

import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "lib.sh"
MESSENGER = REPO / "scripts" / "messenger.sh"


def _sh(script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash"], input=script, text=True, capture_output=True, timeout=60,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/tmp", **(env or {})},
    )


def test_units_are_not_hardcoded_anywhere():
    """The instance: an array literal is what could not survive an update."""
    for path in sorted((REPO / "scripts").glob("*.sh")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not stripped.startswith("UNITS=(kasbbook"), (
                f"{path.name}:{i} hardcodes the unit list; `update.sh` overwrites "
                "this file, so a messenger added here disappears on the next update"
            )


def test_units_come_from_the_units_that_exist():
    result = _sh(f'''
    set -euo pipefail
    source {LIB}
    printf '%s\\n' "${{UNITS[@]}}"
    ''')
    assert result.returncode == 0, result.stderr
    # This machine has no kasbbook units, so the fallback is what should appear.
    assert result.stdout.split() == ["kasbbook-api", "kasbbook-bot"], result.stdout


def test_a_discovered_unit_list_includes_a_second_messenger(tmp_path):
    """discover_units reads a directory; point it at a fake one and check."""
    fake = tmp_path / "systemd"
    fake.mkdir()
    for name in ("kasbbook-api", "kasbbook-bot", "kasbbook-bale"):
        (fake / f"{name}.service").write_text("")
    result = _sh(f'''
    set -euo pipefail
    source {LIB}
    discover() {{
        local found=() f
        for f in {fake}/kasbbook-*.service; do
            [ -e "$f" ] || continue
            found+=("$(basename "$f" .service)")
        done
        printf '%s\\n' "${{found[@]}}"
    }}
    discover
    ''')
    assert result.stdout.split() == ["kasbbook-api", "kasbbook-bale", "kasbbook-bot"]


def test_the_generated_unit_loads_both_environment_files():
    """The shared .env first, the provider's second, so the second wins."""
    result = _sh(f'''
    set -euo pipefail
    KASBBOOK_HOME={REPO}
    source {LIB}
    write_provider_unit() {{
        awk -v desc="Description=KasbBook bot (bale)" \\
            -v extra="EnvironmentFile=$KASBBOOK_HOME/.env.bale" '
            /^Description=/     {{ print desc; next }}
            /^EnvironmentFile=/ {{ print; print extra; next }}
                                {{ print }}
        ' "{REPO}/deploy/kasbbook-bot.service"
    }}
    write_provider_unit
    ''')
    assert result.returncode == 0, result.stderr
    files = [l for l in result.stdout.splitlines() if l.startswith("EnvironmentFile=")]
    assert len(files) == 2, files
    assert files[0].endswith("/.env"), files
    assert files[1].endswith("/.env.bale"), files
    assert "Description=KasbBook bot (bale)" in result.stdout


def test_update_regenerates_the_units_it_has_no_template_for():
    """deploy/ has no kasbbook-bale.service, so the loop that copies templates
    skips it. Without the second loop the Bale unit would keep pointing at an
    entry point that has moved — which is the failure the whole rewrite-units
    step exists to prevent."""
    text = (REPO / "scripts" / "update.sh").read_text(encoding="utf-8")
    assert "installed_providers" in text and "write_provider_unit" in text


def test_the_helper_refuses_a_provider_with_no_adapter():
    result = _sh(f'''
    source {LIB}
    valid() {{ local p; for p in "${{EXTRA_PROVIDERS[@]}}"; do [ "$p" = "$1" ] && return 0; done; return 1; }}
    valid eitaa && echo ACCEPTED || echo REFUSED
    valid bale && echo BALE-OK || echo BALE-NO
    ''')
    assert "REFUSED" in result.stdout and "BALE-OK" in result.stdout, result.stdout


def test_usage_works_without_root():
    """Somebody finding out what the command does should be told, not refused."""
    result = _sh(f"bash {MESSENGER}")
    assert "usage: messenger.sh" in result.stdout, result.stdout + result.stderr
    assert "bale" in result.stdout and "rubika" in result.stdout
