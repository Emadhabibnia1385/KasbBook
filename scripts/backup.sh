#!/bin/bash
# Dump the database, keep the last N, verify what was written.
#
# A backup nobody has restored is a hypothesis. This one at least refuses to
# claim success for an empty or truncated file, and restore.sh is written and
# meant to be exercised.

source "$(dirname "$(readlink -f "$0")")/lib.sh"

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1
KEEP="${KASBBOOK_BACKUP_KEEP:-14}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"   # dumps contain everyone's books

STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/kasbbook-$STAMP.sql.gz"
URL="$(env_value KASBBOOK_DATABASE_URL)"
[ -n "$URL" ] || die "KASBBOOK_DATABASE_URL is not in $KASBBOOK_HOME/.env"

[ "$QUIET" = 1 ] || say "dumping to $TARGET"

case "$URL" in
    postgresql*)
        # pg_dump reads the URL directly, so the password never becomes an
        # argument that other users could see in the process list.
        PGURL="$(printf '%s' "$URL" | sed 's/+asyncpg//; s/+psycopg//')"
        pg_dump --no-owner --no-privileges --clean --if-exists "$PGURL" | gzip -9 > "$TARGET"
        ;;
    sqlite*)
        FILE="$(printf '%s' "$URL" | sed 's|.*:///||')"
        [ -f "$FILE" ] || die "no database file at $FILE"
        # .backup rather than copying the file: a copy taken mid-write is a
        # corrupt database that looks fine until the day it is needed.
        sqlite3 "$FILE" ".backup '/tmp/kasbbook-$STAMP.db'"
        gzip -9 -c "/tmp/kasbbook-$STAMP.db" > "$TARGET"
        rm -f "/tmp/kasbbook-$STAMP.db"
        ;;
    *)
        die "unrecognised database URL"
        ;;
esac

chmod 600 "$TARGET"

# Verify rather than assume. gzip -t catches a truncated write, and a dump
# smaller than a kilobyte is an error message that got redirected.
gzip -t "$TARGET" 2>/dev/null || { rm -f "$TARGET"; die "the dump is not a valid archive"; }
SIZE="$(stat -c%s "$TARGET")"
[ "$SIZE" -gt 1024 ] || { rm -f "$TARGET"; die "the dump is only ${SIZE} bytes; something went wrong"; }

# Trim oldest first, and only ever inside our own directory.
ls -1t "$BACKUP_DIR"/kasbbook-*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
    rm -f "$old"
done

if [ "$QUIET" = 1 ]; then
    echo "$TARGET"
else
    ok "$(numfmt --to=iec "$SIZE" 2>/dev/null || echo "$SIZE bytes") → $TARGET"
    ok "keeping the last $KEEP ($(ls -1 "$BACKUP_DIR"/kasbbook-*.sql.gz 2>/dev/null | wc -l) on disk)"
fi
