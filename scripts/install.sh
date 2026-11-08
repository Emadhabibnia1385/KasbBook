#!/bin/bash
# Install KasbBook from nothing.
#
# Idempotent: running it twice is safe and the second run repairs whatever the
# first one left half-done. It asks for the few things it genuinely cannot
# invent — a bot token — and generates everything it can, because a signing key
# somebody types by hand is a signing key somebody can guess.

source "$(dirname "$(readlink -f "$0")")/lib.sh" 2>/dev/null || {
    # Bootstrapping from a bare curl, before the repo exists.
    set -euo pipefail
    KASBBOOK_HOME="${KASBBOOK_HOME:-/opt/kasbbook}"
    KASBBOOK_BRANCH="${KASBBOOK_BRANCH:-main}"
    KASBBOOK_REPO="${KASBBOOK_REPO:-https://github.com/Emadhabibnia1385/KasbBook.git}"
    R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; N=$'\033[0m'
    B=$'\033[1m'; D=$'\033[2m'; V=$'\033[38;5;105m'; A=$'\033[38;5;179m'
    if [ ! -t 1 ] || [ -n "${NO_COLOR:-}" ]; then R=; G=; Y=; C=; N=; B=; D=; V=; A=; fi
    STEP=0
    step() { STEP=$((STEP + 1)); echo; echo "${V}${B}[${STEP}/${STEPS:-?}]${N} ${B}$*${N}"; }
    say()  { echo "${C}==>${N} $*"; }
    ok()   { echo "  ${G}✓${N} $*"; }
    warn() { echo "  ${Y}!${N} $*"; }
    die()  { echo "  ${R}✗${N} $*" >&2; exit 1; }
    # No UNITS here on purpose. Nothing touches a unit before the checkout
    # exists, and lib.sh — sourced below, once it does — discovers them from
    # disk. A copy here would be a second answer to the same question.
}

STEPS=9
START_TIME=$(date +%s)

# What the person sees first. Plain box drawing and two 256-colour tints, so it reads the same over
# ssh from any terminal; with no terminal (a pipe, a log) the colours drop away and it is still text.
banner() {
    # ASCII inside the box so every row is the same width however the terminal counts characters;
    # the Persian name sits under it, where nothing has to line up with a border.
    local width=58 line
    echo
    echo "${V}  ╭$(printf '─%.0s' $(seq 1 $width))╮${N}"
    for line in "" "   KasbBook" "   bookkeeping for a small business, where it already" "   talks: Telegram, Bale, Rubika, web panel and API" ""; do
        case "$line" in
            "   KasbBook") printf '%s  │%s   %s%s%s%*s%s│%s\n' "${V}" "${N}" "${B}" "KasbBook" "${N}" $((width - 11)) "" "${V}" "${N}" ;;
            *) printf '%s  │%s%s%-*s%s%s│%s\n' "${V}" "${N}" "${D}" "$width" "$line" "${N}" "${V}" "${N}" ;;
        esac
    done
    echo "${V}  ╰$(printf '─%.0s' $(seq 1 $width))╯${N}"
    echo "  ${A}کسب‌بوک${N}  ${D}running it twice is safe; the second run repairs what the first left half-done${N}"
}
banner

[ "$(id -u)" -eq 0 ] || die "run this with sudo"

step "checking what this box already has"
for tool in git python3 curl; do
    command -v "$tool" >/dev/null || die "$tool is required and not installed"
done
PYTHON_OK="$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)')"
[ "$PYTHON_OK" = "1" ] || die "python3.11 or newer is required (found $(python3 -V))"
ok "python $(python3 -V | cut -d' ' -f2)"

command -v docker >/dev/null && ok "docker is available" || warn "no docker — you will need your own PostgreSQL and Redis"

step "fetching the code into $KASBBOOK_HOME"
if [ -d "$KASBBOOK_HOME/.git" ]; then
    git config --global --add safe.directory "$KASBBOOK_HOME" 2>/dev/null || true
    git -C "$KASBBOOK_HOME" fetch --quiet origin "$KASBBOOK_BRANCH"
    # Move the local branch too, not just its contents. Resetting alone leaves
    # HEAD on whatever branch it was on, so an older install keeps reporting a
    # branch name while holding a different branch's code — and `git status`
    # lying about where you are is a bad way to start debugging anything.
    git -C "$KASBBOOK_HOME" checkout --quiet -B "$KASBBOOK_BRANCH" \
        "origin/$KASBBOOK_BRANCH"
else
    git clone --quiet --branch "$KASBBOOK_BRANCH" "$KASBBOOK_REPO" "$KASBBOOK_HOME"
    git config --global --add safe.directory "$KASBBOOK_HOME" 2>/dev/null || true
fi
cd "$KASBBOOK_HOME"
ok "$(git log --oneline -1)"

# The bootstrap block above defines just enough to get here, because under
# `curl ... | sudo bash` there is no checkout yet to source anything from.
# There is now, and the helpers that ask questions safely live in it — so
# nothing has to be kept in two places, drifting.
# shellcheck source=scripts/lib.sh
source "$KASBBOOK_HOME/scripts/lib.sh"

step "python environment"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt
# Editable, so `kasbbook` is importable because it is installed rather than
# because something arranged sys.path first. That arrangement has broken three
# times, most recently under uvicorn.
./venv/bin/pip install --quiet --no-deps -e .
ok "dependencies installed"

# ---------------------------------------------------------------- datastores
step "datastores (PostgreSQL and Redis)"
if [ ! -f deploy/.env ]; then
    say "generating datastore credentials"
    POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    cat > deploy/.env <<ENV
POSTGRES_DB=kasbbook
POSTGRES_USER=kasbbook
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_PORT=5435
REDIS_PORT=6382
ENV
    chmod 600 deploy/.env
    ok "written to deploy/.env"
fi

if command -v docker >/dev/null; then
    say "starting PostgreSQL and Redis"
    (cd deploy && docker compose up -d) >/dev/null 2>&1 || warn "compose did not start cleanly"

    # A container that is "up" is not a database that accepts connections.
    for _ in $(seq 1 30); do
        (cd deploy && docker compose exec -T postgres pg_isready -q) 2>/dev/null && break
        sleep 2
    done
    (cd deploy && docker compose exec -T postgres pg_isready -q) 2>/dev/null \
        && ok "postgres is accepting connections" \
        || warn "postgres is not answering yet; check 'docker compose -f deploy/docker-compose.yml logs'"
fi

# -------------------------------------------------------------- environment
step "environment"
if [ ! -f .env ]; then
    say "setting up the environment"
    . deploy/.env 2>/dev/null || true

    echo
    ask TELEGRAM_BOT_TOKEN "  Telegram bot token (from @BotFather): "
    [ -n "$TELEGRAM_BOT_TOKEN" ] || die "a bot token is required. Either run this \
from a terminal, or pass it: curl ... | sudo TELEGRAM_BOT_TOKEN=... bash"
    sane "$TELEGRAM_BOT_TOKEN" "TELEGRAM_BOT_TOKEN"
    ask TELEGRAM_BOT_USERNAME "  Bot username, without the @: "
    sane "$TELEGRAM_BOT_USERNAME" "TELEGRAM_BOT_USERNAME"

    # Optional, and asked for because there is nowhere else to put it. Without
    # it the bot's API screen shows no link to the documentation — deliberately
    # no link rather than a dead one — and webhook mode cannot be turned on at
    # all, because a provider has to be told where to deliver.
    ask KASBBOOK_API_URL "  Public https URL for the API, if you have one (blank to skip): "
    KASBBOOK_API_URL=$(normalise_url "$KASBBOOK_API_URL")

    TOKEN=$TELEGRAM_BOT_TOKEN
    USERNAME=$TELEGRAM_BOT_USERNAME

    cat > .env <<ENV
# Generated by scripts/install.sh. Secrets live here and nowhere else.

KASBBOOK_PROVIDER=telegram
TELEGRAM_BOT_TOKEN=$TOKEN
TELEGRAM_BOT_USERNAME=${USERNAME#@}

KASBBOOK_DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-kasbbook}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT:-5435}/${POSTGRES_DB:-kasbbook}
REDIS_URL=redis://127.0.0.1:${REDIS_PORT:-6382}/0

# Generated, never typed: a signing key a person chose is a key a person can guess.
KASBBOOK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
KASBBOOK_ACCESS_MINUTES=30
KASBBOOK_REFRESH_DAYS=30

KASBBOOK_LOG_LEVEL=INFO

# Where this API is published. The bot links to <url>/docs from its API screen.
KASBBOOK_API_URL=$KASBBOOK_API_URL

# polling holds an outbound connection and needs nothing reachable from
# outside, which is why it is the default. Switching to webhook needs the URL
# above to be real, terminating TLS, and nothing logging the path below.
KASBBOOK_UPDATE_MODE=polling

# Generated now even though polling ignores it, so that turning webhooks on
# later is one word and a restart rather than "invent a secret" — which is how
# guessable ones get chosen.
KASBBOOK_WEBHOOK_PATH=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
ENV
    chmod 600 .env
    ok "written to .env"
else
    ok ".env already exists; leaving it alone"
    # An installation predating the API has no signing key, and the API will
    # not start without one. Adding it is safe; overwriting it would sign
    # everyone out.
    if ! grep -q "^KASBBOOK_SECRET_KEY=" .env; then
        echo "KASBBOOK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" >> .env
        ok "added a signing key for the API"
    fi
    # Same reasoning: an installation predating webhook support has no path
    # secret, and inventing one under pressure later is how a guessable one
    # gets chosen. Adding it changes nothing until the mode is switched.
    if ! grep -q "^KASBBOOK_WEBHOOK_PATH=" .env; then
        echo "KASBBOOK_WEBHOOK_PATH=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')" >> .env
        ok "added a webhook path secret, unused until KASBBOOK_UPDATE_MODE=webhook"
    fi
    if ! grep -q "^KASBBOOK_API_URL=" .env; then
        ask KASBBOOK_API_URL "  Public https URL for the API, if you have one (blank to skip): "
        KASBBOOK_API_URL=$(normalise_url "$KASBBOOK_API_URL")
        if [ -n "$KASBBOOK_API_URL" ]; then
            echo "KASBBOOK_API_URL=$KASBBOOK_API_URL" >> .env
            ok "the bot will link to $KASBBOOK_API_URL/docs"
        fi
    fi
fi

step "creating the schema"
set -a; . ./.env; set +a
./venv/bin/alembic upgrade head
ok "schema at $(./venv/bin/alembic current 2>/dev/null | tail -1)"

step "installing services"
for unit in "${UNITS[@]}"; do
    install -m 644 "deploy/$unit.service" "/etc/systemd/system/$unit.service"
done
systemctl daemon-reload
systemctl enable --quiet --now kasbbook-bot
systemctl enable --quiet --now kasbbook-api

step "checking that it came up"
sleep 10
FAILED=0
for unit in "${UNITS[@]}"; do
    if systemctl is-active --quiet "$unit"; then
        ok "$unit is running"
    else
        warn "$unit did not start:"
        journalctl -u "$unit" -n 15 --no-pager -o cat | sed 's/^/      /'
        FAILED=1
    fi
done

curl -fsS --max-time 5 http://127.0.0.1:8210/readyz >/dev/null 2>&1 \
    && ok "the API answers /readyz" \
    || warn "the API is not answering on 127.0.0.1:8210 yet"

echo
if [ "$FAILED" = 0 ]; then
    ELAPSED=$(( $(date +%s) - START_TIME ))
    WEB="${KASBBOOK_API_URL:-}"
    [ -n "$WEB" ] || WEB="http://127.0.0.1:8210"
    echo "${G}  ╭──────────────────────────────────────────────────────────╮${N}"
    echo "${G}  │${N}  ${G}${B}✓ KasbBook is installed and running${N}  ${D}(${ELAPSED}s)${N}"
    echo "${G}  ╰──────────────────────────────────────────────────────────╯${N}"
    echo
    echo "  ${B}Open it${N}"
    echo "    web panel   ${C}${WEB}/${N}"
    echo "    api docs    ${C}${WEB}/docs${N}"
    echo "    the bot     send /start to @${TELEGRAM_BOT_USERNAME:-your bot} in Telegram"
    echo
    echo "  ${B}Look after it${N}"
    echo "    bot logs    journalctl -u kasbbook-bot -f"
    echo "    api logs    journalctl -u kasbbook-api -f"
    echo "    update      sudo $KASBBOOK_HOME/scripts/update.sh"
    echo "    back up     sudo $KASBBOOK_HOME/scripts/backup.sh"
    echo
    echo "  ${D}docs: https://emadhabibnia1385.github.io/KasbBook/  ·  powered by Emad Habibnia${N}"
    echo
else
    die "installation finished with problems; see the logs above"
fi
