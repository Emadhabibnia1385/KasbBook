# Shared bits for the operational scripts. Sourced, never executed.

set -euo pipefail

KASBBOOK_HOME="${KASBBOOK_HOME:-/opt/kasbbook}"
KASBBOOK_BRANCH="${KASBBOOK_BRANCH:-main}"
KASBBOOK_REPO="${KASBBOOK_REPO:-https://github.com/Emadhabibnia1385/KasbBook.git}"
BACKUP_DIR="${KASBBOOK_BACKUP_DIR:-/var/backups/kasbbook}"
UNITS=(kasbbook-bot kasbbook-api)

R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; N=$'\033[0m'

say()  { echo "${C}==>${N} $*"; }
ok()   { echo "  ${G}✓${N} $*"; }
warn() { echo "  ${Y}!${N} $*"; }
die()  { echo "  ${R}✗${N} $*" >&2; exit 1; }

need_root() {
    [ "$(id -u)" -eq 0 ] || die "run this with sudo — it writes systemd units and restarts services"
}

# Git refuses to work in a directory owned by someone else. On this box the
# checkout is root-owned and the scripts run under sudo, so the exception is
# both narrow and correct.
trust_checkout() {
    git config --global --get-all safe.directory | grep -qxF "$KASBBOOK_HOME" \
        || git config --global --add safe.directory "$KASBBOOK_HOME"
}

env_value() {
    # One key out of the environment file, without sourcing it — sourcing runs
    # whatever is in there, and a password with a backtick in it should not be
    # a code path.
    local key="$1" file="${2:-$KASBBOOK_HOME/.env}"
    [ -f "$file" ] || return 0
    sed -n "s/^${key}=//p" "$file" | tail -1
}

# A started process is not a working one. This is the check every script that
# restarts something has to pass before it calls itself done.
service_is_healthy() {
    local unit="$1" seconds="${2:-10}"

    local before
    before="$(systemctl show "$unit" -p NRestarts --value 2>/dev/null || echo 0)"
    sleep "$seconds"

    systemctl is-active --quiet "$unit" || return 1

    # `Restart=always` keeps a crash-looping service "active" forever, so the
    # word means very little on its own. A restart counter that moved while we
    # were watching means the process died and came back.
    local after
    after="$(systemctl show "$unit" -p NRestarts --value 2>/dev/null || echo 0)"
    [ "$after" = "$before" ] || return 1

    if journalctl -u "$unit" --since "-${seconds}s" -o cat --no-pager \
        | grep -qiE "Traceback|ModuleNotFoundError|ImportError|CRITICAL"; then
        return 1
    fi
    return 0
}

show_failure() {
    local unit="$1"
    echo "  ${R}--- last 25 lines of $unit ---${N}"
    journalctl -u "$unit" -n 25 --no-pager -o cat | sed 's/^/  /'
}
