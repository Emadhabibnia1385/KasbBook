#!/bin/bash
# Update a running installation, and put it back if the new version does not work.
#
# The rollback is the point. An update script that only moves forward turns a
# bad commit into an outage that lasts until somebody wakes up; one that checks
# and reverts turns it into a failed update and a bot that is still running.

# Run from a copy of ourselves, before touching the working tree.
#
# This is not caution, it is a bug that already happened. bash reads a script
# incrementally and keeps a byte offset into the file. `git reset --hard` a few
# lines down rewrites this very file in place, and bash then carries on reading
# at that same offset in the *new* content — so what executes is a splice of two
# versions. The symptom was an update that skipped a step it plainly contains
# and then reported the service healthy while it was crash-looping.
if [ -z "${KASBBOOK_UPDATE_DETACHED:-}" ]; then
    SELF_DIR="$(dirname "$(readlink -f "$0")")"
    STAGING="$(mktemp -d)"
    trap 'rm -rf "$STAGING"' EXIT
    cp "$SELF_DIR"/*.sh "$STAGING/"
    export KASBBOOK_UPDATE_DETACHED=1
    exec bash "$STAGING/$(basename "$0")" "$@"
fi

source "$(dirname "$(readlink -f "$0")")/lib.sh"
need_root
trust_checkout

cd "$KASBBOOK_HOME"
PREVIOUS="$(git rev-parse HEAD)"

say "current: $(git log --oneline -1)"

say "fetching"
git fetch --quiet origin "$KASBBOOK_BRANCH"
if [ "$PREVIOUS" = "$(git rev-parse "origin/$KASBBOOK_BRANCH")" ]; then
    ok "already up to date"
    exit 0
fi

# Taken before anything changes, so the rollback path exists even if the
# migration is the thing that breaks.
say "backing up the database first"
"$(dirname "$(readlink -f "$0")")/backup.sh" --quiet || die "backup failed; not updating"

roll_back() {
    warn "rolling back to $PREVIOUS"
    git reset --quiet --hard "$PREVIOUS"
    ./venv/bin/pip install --quiet -r requirements-v2.txt || true
    ./venv/bin/pip install --quiet --no-deps -e . || true
    install_units
    for unit in "${UNITS[@]}"; do
        systemctl restart "$unit" 2>/dev/null || true
    done
    echo
    die "update failed and was rolled back. The database backup is in $BACKUP_DIR."
}

install_units() {
    # Rewritten every update, so a change to an entry point ships with the code
    # that moved it. This is not hypothetical: the bot's runner moved from
    # apps/telegram_bot/ to apps/bot/, and a unit file left behind would have
    # pointed at a path that no longer exists.
    for unit in "${UNITS[@]}"; do
        [ -f "deploy/$unit.service" ] || continue
        install -m 644 "deploy/$unit.service" "/etc/systemd/system/$unit.service"
    done
    systemctl daemon-reload
}

say "updating to origin/$KASBBOOK_BRANCH"
git checkout --quiet -B "$KASBBOOK_BRANCH" "origin/$KASBBOOK_BRANCH"
git log --oneline -1

say "dependencies"
./venv/bin/pip install --quiet --upgrade -r requirements-v2.txt || roll_back
./venv/bin/pip install --quiet --no-deps -e . || roll_back

say "tests"
# Run before the migration, not after: a suite that fails here means the commit
# is bad, and finding that out before touching the schema is much cheaper.
if ! ./venv/bin/python -m pytest tests/v2 -q; then
    roll_back
fi

say "migrating"
set -a; . ./.env; set +a
./venv/bin/alembic upgrade head || roll_back
ok "schema at $(./venv/bin/alembic current 2>/dev/null | tail -1)"

say "units"
install_units

say "restarting"
for unit in "${UNITS[@]}"; do
    systemctl is-enabled --quiet "$unit" 2>/dev/null || continue
    systemctl restart "$unit"
done

say "health"
for unit in "${UNITS[@]}"; do
    systemctl is-enabled --quiet "$unit" 2>/dev/null || continue
    if service_is_healthy "$unit" 10; then
        ok "$unit: active, log clean, $(systemctl show "$unit" -p NRestarts --value) restarts"
    else
        show_failure "$unit"
        roll_back
    fi
done

# An API that has not crashed is not the same as an API that answers. This is
# the only check that would have caught the last failure on its own.
if systemctl is-enabled --quiet kasbbook-api 2>/dev/null; then
    if curl -fsS --max-time 5 http://127.0.0.1:8210/readyz >/dev/null 2>&1; then
        ok "the API answers /readyz"
    else
        warn "the API is running but does not answer /readyz"
        show_failure kasbbook-api
        roll_back
    fi
fi

echo
ok "updated to $(git log --oneline -1)"
