# Shared bits for the operational scripts. Sourced, never executed.

set -euo pipefail

KASBBOOK_HOME="${KASBBOOK_HOME:-/opt/kasbbook}"
KASBBOOK_BRANCH="${KASBBOOK_BRANCH:-main}"
KASBBOOK_REPO="${KASBBOOK_REPO:-https://github.com/Emadhabibnia1385/KasbBook.git}"
BACKUP_DIR="${KASBBOOK_BACKUP_DIR:-/var/backups/kasbbook}"
# Discovered from disk, never listed here. A second messenger is a third unit,
# and the obvious place to record it — this array — is a tracked file that
# `update.sh` overwrites with `git checkout -B`. The edit would survive exactly
# until the next update and then vanish, taking that bot out of the restart and
# health loops without saying so. Asking systemd what exists cannot drift.
discover_units() {
    local found=() f
    for f in /etc/systemd/system/kasbbook-*.service; do
        [ -e "$f" ] || continue
        found+=("$(basename "$f" .service)")
    done
    # Nothing installed yet: this is the first run of install.sh.
    [ ${#found[@]} -gt 0 ] || found=(kasbbook-api kasbbook-bot)
    printf '%s\n' "${found[@]}"
}
# A read loop rather than `mapfile`, which is bash 4 and absent on macOS —
# where the tests for these scripts run.
UNITS=()
while IFS= read -r _unit; do UNITS+=("$_unit"); done < <(discover_units)
unset _unit

# Messengers that can run beside the main unit. Telegram is the main unit, and
# Eitaa has no adapter — asking the runner for one fails at startup rather than
# three screens in, which is the right failure but not a useful bot.
EXTRA_PROVIDERS=(bale rubika)

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

# ---------------------------------------------------------------- asking
#
# The README says to install with `curl ... | sudo bash`, and under a pipe
# stdin *is the script*. A plain `read` there does not wait for anybody: it
# swallows the next line of source as the answer, and that line then never
# runs. It really happened — .env came out holding
#
#   TELEGRAM_BOT_TOKEN=[ -n "$TOKEN" ] || die "a bot token is required"
#
# with the check that would have caught it eaten as the answer, and the
# installer exiting zero. So prompts are read from the terminal, never from
# stdin, and an environment variable wins over both so the whole thing can be
# driven with no terminal at all.
# Opened rather than tested: /dev/tty exists on a box with no controlling
# terminal and fails only when something tries to read it, which would put
# "Device not configured" in front of a person who is being told something
# more useful.
KASBBOOK_TTY=""
# The 2> comes first on purpose: redirections are applied left to right, and
# with it second the failing open has already printed before stderr is shut.
if [ -r /dev/tty ] && : 2>/dev/null < /dev/tty; then KASBBOOK_TTY=/dev/tty; fi

ask() {  # ask VAR_NAME "prompt"
    local __name=$1 __prompt=$2 __value=""
    __value=${!__name:-}
    if [ -z "$__value" ] && [ -n "$KASBBOOK_TTY" ]; then
        read -r -p "$__prompt" __value < "$KASBBOOK_TTY" 2>/dev/null || __value=""
    fi
    printf -v "$__name" '%s' "$__value"
}

# A token or username can never contain whitespace or a quote, and those are
# exactly what the bug above produced. Refusing them turns a .env full of shell
# into a failed install, which is the difference between a bad five minutes and
# a bad afternoon. The `$` matters for a second reason: .env is written from an
# unquoted heredoc, so a value carrying one would be expanded on the way in.
sane() {  # sane VALUE NAME
    case "$1" in
        *[[:space:]]*|*\"*|*\'*|*'$'*|*'`'*)
            die "$2 contains whitespace or a shell character, which no real value does.
     If you piped this script, the prompt may have eaten a line of it.
     Pass the value instead: curl ... | sudo $2=... bash" ;;
    esac
}

# Accept what a person actually types. "example.com" is a URL to everyone
# except a URL parser, and a trailing slash turns <url>/docs into <url>//docs.
normalise_url() {
    local u=${1:-}
    [ -n "$u" ] || { printf ''; return 0; }
    case "$u" in
        http://*) die "the API URL must be https — Telegram refuses a plain HTTP webhook, \
and bearer tokens cross this boundary" ;;
        https://*) ;;
        *) u="https://$u" ;;
    esac
    printf '%s' "${u%/}"
}

# Confirming something destructive. Deliberately NOT ask(): no environment
# variable may answer this, and it is read from the terminal only. Otherwise
# `echo destroy | sudo ./uninstall.sh --purge` confirms itself, and a
# confirmation something else can supply is not a confirmation. No terminal
# means no, which is the safe direction for a script that deletes data.
confirm() {  # confirm WORD "prompt"
    local __want=$1 __prompt=$2 __got=""
    [ -n "$KASBBOOK_TTY" ] || die "this destroys data and needs a terminal to confirm on"
    read -r -p "$__prompt" __got < "$KASBBOOK_TTY" 2>/dev/null || __got=""
    [ "$__got" = "$__want" ] || die "not confirmed; nothing was changed"
}

# One provider unit, generated from the Telegram one rather than written twice.
# Both environment files are loaded, in order: the shared one carries the
# database, Redis and the signing key, and the per-provider one carries only
# what differs. systemd applies them in order, so the second wins — which is
# why rotating the signing key does not mean editing it in N places.
write_provider_unit() {
    local provider="$1" unit="kasbbook-$provider"
    local template="$KASBBOOK_HOME/deploy/kasbbook-bot.service"
    [ -f "$template" ] || die "$template is missing; is $KASBBOOK_HOME a checkout?"
    {
        echo "# Generated for the $provider bot from deploy/kasbbook-bot.service, and"
        echo "# regenerated by scripts/update.sh — so a change to the entry point reaches"
        echo "# every messenger rather than only the one whose template is in the repo."
        # awk rather than `sed ... a`, whose syntax differs between GNU and
        # BSD sed and fails outright on the second.
        awk -v desc="Description=KasbBook bot ($provider)" \
            -v extra="EnvironmentFile=$KASBBOOK_HOME/.env.$provider" '
            /^Description=/     { print desc; next }
            /^EnvironmentFile=/ { print; print extra; next }
                                { print }
        ' "$template"
    } > "/etc/systemd/system/$unit.service"
    chmod 644 "/etc/systemd/system/$unit.service"
}

# Which providers currently have a unit and an environment file.
installed_providers() {
    local p
    for p in "${EXTRA_PROVIDERS[@]}"; do
        [ -f "/etc/systemd/system/kasbbook-$p.service" ] && echo "$p"
    done
    return 0
}
