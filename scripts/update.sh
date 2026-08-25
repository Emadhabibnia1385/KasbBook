#!/bin/bash
# Update a running installation, and put it back if the new version does not work.
#
# The rollback is the point. An update script that only moves forward turns a
# bad commit into an outage that lasts until somebody wakes up; one that checks
# and reverts turns it into a failed update and a bot that is still running.

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
git reset --quiet --hard "origin/$KASBBOOK_BRANCH"
git log --oneline -1

say "dependencies"
./venv/bin/pip install --quiet --upgrade -r requirements-v2.txt || roll_back

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

echo
ok "updated to $(git log --oneline -1)"
