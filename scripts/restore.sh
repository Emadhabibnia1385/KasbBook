#!/bin/bash
# Put a backup back.
#
# This one destroys data by design, so it says exactly what it is about to
# replace and makes you type the word. It also takes a backup of what it is
# about to overwrite — restoring the wrong file should not be unrecoverable.

source "$(dirname "$(readlink -f "$0")")/lib.sh"
need_root

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ]; then
    echo "usage: restore.sh <backup.sql.gz>"
    echo
    echo "available:"
    ls -1t "$BACKUP_DIR"/kasbbook-*.sql.gz 2>/dev/null | head -20 | sed 's/^/  /' || echo "  (none)"
    exit 1
fi
[ -f "$ARCHIVE" ] || die "no such file: $ARCHIVE"
gzip -t "$ARCHIVE" 2>/dev/null || die "$ARCHIVE is not a valid gzip archive"

URL="$(env_value KASBBOOK_DATABASE_URL)"
[ -n "$URL" ] || die "KASBBOOK_DATABASE_URL is not in $KASBBOOK_HOME/.env"

echo
warn "this REPLACES the current database with the contents of:"
echo "      $ARCHIVE  ($(date -r "$ARCHIVE" '+%Y-%m-%d %H:%M'))"
echo "      target: $(printf '%s' "$URL" | sed 's|://[^@]*@|://***@|')"
echo
confirm restore "Type 'restore' to go ahead: "

say "stopping services"
for unit in "${UNITS[@]}"; do
    systemctl stop "$unit" 2>/dev/null || true
done

say "backing up what is about to be replaced"
SAFETY="$("$(dirname "$(readlink -f "$0")")/backup.sh" --quiet)" || warn "could not back up first"
[ -n "${SAFETY:-}" ] && ok "previous state saved to $SAFETY"

say "restoring"
case "$URL" in
    postgresql*)
        PGURL="$(printf '%s' "$URL" | sed 's/+asyncpg//; s/+psycopg//')"
        gunzip -c "$ARCHIVE" | psql --quiet --set ON_ERROR_STOP=1 "$PGURL" >/dev/null || {
            warn "the restore failed"
            [ -n "${SAFETY:-}" ] && warn "the state from before this attempt is in $SAFETY"
            die "database left as it was found"
        }
        ;;
    sqlite*)
        FILE="$(printf '%s' "$URL" | sed 's|.*:///||')"
        gunzip -c "$ARCHIVE" > "$FILE"
        ;;
esac

say "bringing the schema up to the running code"
cd "$KASBBOOK_HOME"
set -a; . ./.env; set +a
./venv/bin/alembic upgrade head

say "starting services"
for unit in "${UNITS[@]}"; do
    systemctl is-enabled --quiet "$unit" 2>/dev/null || continue
    systemctl start "$unit"
    service_is_healthy "$unit" 8 && ok "$unit is up" || { show_failure "$unit"; die "$unit did not come back"; }
done

echo
ok "restored from $ARCHIVE"
