#!/bin/bash
# Remove KasbBook.
#
# The data is the part that cannot be recovered, so it is kept unless you ask
# twice — once to uninstall and once, explicitly, to destroy the books.

source "$(dirname "$(readlink -f "$0")")/lib.sh"
need_root

PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

echo
warn "this removes the KasbBook services and the checkout at $KASBBOOK_HOME"
if [ "$PURGE" = 1 ]; then
    echo "      ${R}and --purge means the database and every backup go too.${N}"
    echo "      ${R}Everyone's books. There is no undo.${N}"
else
    echo "      the database and $BACKUP_DIR are kept. Add --purge to delete those as well."
fi
echo
read -r -p "Type 'remove' to go ahead: " CONFIRM
[ "$CONFIRM" = "remove" ] || die "cancelled"

if [ "$PURGE" = 1 ]; then
    read -r -p "Type the word 'destroy' to confirm deleting the data: " CONFIRM2
    [ "$CONFIRM2" = "destroy" ] || die "cancelled"
fi

# Even on the way out. If this is a mistake, the dump is what makes it a
# recoverable one.
if [ "$PURGE" = 0 ] && [ -f "$KASBBOOK_HOME/.env" ]; then
    say "taking a final backup"
    "$(dirname "$(readlink -f "$0")")/backup.sh" --quiet && ok "saved in $BACKUP_DIR" || warn "could not back up"
fi

say "stopping services"
for unit in "${UNITS[@]}"; do
    systemctl disable --quiet --now "$unit" 2>/dev/null || true
    rm -f "/etc/systemd/system/$unit.service"
done
systemctl daemon-reload
ok "services removed"

if [ "$PURGE" = 1 ]; then
    say "removing the datastores"
    (cd "$KASBBOOK_HOME/deploy" && docker compose down -v) >/dev/null 2>&1 || true
    rm -rf "$BACKUP_DIR"
    ok "database and backups deleted"
fi

say "removing $KASBBOOK_HOME"
rm -rf "$KASBBOOK_HOME"
ok "done"

echo
if [ "$PURGE" = 0 ]; then
    echo "  The database container is still running and the backups are in $BACKUP_DIR."
fi
