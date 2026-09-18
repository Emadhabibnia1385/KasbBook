"""An unchanged checkout must not hide an interrupted installation."""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="production updater requires Bash/POSIX")
REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("backup_ok", [True, False])
def test_same_commit_runs_recovery_only_after_a_successful_backup(tmp_path, backup_ok):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "update.sh").write_text((REPO / "scripts/update.sh").read_text(), encoding="utf-8")
    log = tmp_path / "events"
    (scripts / "lib.sh").write_text('''
set -e
need_root() { :; }
trust_checkout() { :; }
say() { :; }
ok() { :; }
warn() { :; }
die() { exit 1; }
installed_providers() { :; }
service_is_healthy() { echo health >> "$EVENTS"; }
show_failure() { :; }
UNITS=(kasbbook-api)
''', encoding="utf-8")
    backup = scripts / "backup.sh"
    backup.write_text('#!/bin/bash\necho backup >> "$EVENTS"\nexit ' + ("0" if backup_ok else "1") + '\n')
    backup.chmod(0o755)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    programs = {
        "git": 'case "$1" in rev-parse) echo samecommit;; log) echo samecommit;; esac',
        "systemctl": 'echo "systemctl $*" >> "$EVENTS"',
        "curl": 'echo ready >> "$EVENTS"',
    }
    for name, body in programs.items():
        executable = binaries / name
        executable.write_text("#!/bin/bash\n" + body + "\n")
        executable.chmod(0o755)
    venv = tmp_path / "venv/bin"
    venv.mkdir(parents=True)
    for name in ("pip", "python", "alembic"):
        executable = venv / name
        executable.write_text(f'#!/bin/bash\necho "{name} $*" >> "$EVENTS"\n')
        executable.chmod(0o755)
    (tmp_path / ".env").write_text("# test environment\n")
    environment = dict(os.environ, KASBBOOK_UPDATE_DETACHED="1", KASBBOOK_HOME=str(tmp_path),
        KASBBOOK_BRANCH="main", BACKUP_DIR=str(tmp_path), EVENTS=str(log),
        PATH=str(binaries) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(["bash", str(scripts / "update.sh")], env=environment,
                            capture_output=True, text=True)
    events = log.read_text().splitlines()
    if not backup_ok:
        assert result.returncode != 0
        assert events == ["backup"]
    else:
        assert result.returncode == 0, result.stderr
        assert events.index("backup") < events.index("python -m pytest tests -q")
        assert events.index("python -m pytest tests -q") < events.index("alembic upgrade head")
        assert events.index("alembic upgrade head") < events.index("systemctl restart kasbbook-api")
        assert events.index("systemctl restart kasbbook-api") < events.index("health") < events.index("ready")
