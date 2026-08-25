#!/bin/bash
# Deploy the bot on the server.
#
# `set -e` and no output filtering, on purpose: an earlier version of this
# piped alembic through `grep ERROR`, and a migration that died with a Python
# traceback looked like a clean deploy for three rounds.
set -euo pipefail

cd "${KASBBOOK_HOME:-/opt/kasbbook-v2}"

echo "==> pulling"
git pull --ff-only
git log --oneline -1

echo "==> tests"
./venv/bin/python -m pytest tests/v2 -q

echo "==> migrating"
set -a; . ./.env; set +a
./venv/bin/alembic upgrade head

echo "==> schema is where the code expects it"
./venv/bin/alembic current | tail -1

echo "==> restarting"
systemctl restart kasbbook-v2
sleep 8
systemctl is-active --quiet kasbbook-v2 || { journalctl -u kasbbook-v2 -n 40 --no-pager; exit 1; }

echo "==> health"
echo "  service: $(systemctl is-active kasbbook-v2) | restarts: $(systemctl show kasbbook-v2 -p NRestarts --value)"

# A started process is not a working one: fail loudly on anything in the log.
sleep 5
if journalctl -u kasbbook-v2 --since "1 minute ago" -o cat --no-pager | grep -qiE "Traceback|Error:|Exception"; then
    echo "  ERRORS IN LOG:"
    journalctl -u kasbbook-v2 --since "1 minute ago" -o cat --no-pager | grep -iE "Traceback|Error|Exception" | head -5
    exit 1
fi
echo "  log is clean"
