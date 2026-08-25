# Operations

## The scripts

All under `/opt/kasbbook-v2/scripts/`, all needing `sudo`, all sourcing
`lib.sh`.

| | |
|---|---|
| `install.sh` | from nothing to running. Idempotent. |
| `update.sh` | pull, test, migrate, restart — **and roll back if it fails** |
| `backup.sh` | dump, verify, keep the last 14 |
| `restore.sh` | put a backup back, after backing up what it replaces |
| `uninstall.sh` | remove services and checkout; `--purge` for the data too |

## Updating

```bash
sudo /opt/kasbbook-v2/scripts/update.sh
```

In order:

1. **Back up first** — so the rollback path exists even if the migration is
   what breaks.
2. **Fetch and reset** to the branch head.
3. **Install dependencies.**
4. **Run the tests** — before the migration, not after. A failing suite means
   the commit is bad, and finding that out before touching the schema is much
   cheaper.
5. **Migrate.**
6. **Rewrite the systemd units** from `deploy/`. This is why they live in the
   repo: the bot's runner once moved from `apps/telegram_bot/` to `apps/bot/`,
   and a unit file left behind would have pointed at a path that no longer
   existed.
7. **Restart** both services.
8. **Check health** — active, and no traceback in the last ten seconds of
   journal.

If any step fails, it resets to the previous commit, reinstalls the previous
units, restarts, and exits non-zero telling you where the backup is.

An update script that only moves forward turns a bad commit into an outage
lasting until somebody wakes up. One that checks and reverts turns it into a
failed update and a bot that is still running.

## Backups

```bash
sudo /opt/kasbbook-v2/scripts/backup.sh
```

`pg_dump | gzip` into `/var/backups/kasbbook/`, mode 600, directory 700 —
dumps contain everyone's books.

It **verifies** rather than assumes: `gzip -t` on what it wrote, and it refuses
to call a sub-kilobyte file a backup, because that is exactly what a redirected
error message looks like.

On SQLite it uses `.backup`, not `cp`. A copy taken mid-write is a corrupt
database that looks fine until the day it is needed.

Keeps the last 14 by default (`KASBBOOK_BACKUP_KEEP`), oldest deleted first,
only ever inside its own directory.

### Nightly

```bash
sudo crontab -e
0 3 * * * /opt/kasbbook-v2/scripts/backup.sh --quiet
```

### Off the box

A backup on the same disk as the database survives a bad migration but not a
dead disk. Copy them somewhere else:

```bash
rsync -az /var/backups/kasbbook/ elsewhere:/backups/kasbbook/
```

## Restoring

```bash
sudo /opt/kasbbook-v2/scripts/restore.sh /var/backups/kasbbook/kasbbook-20260825-030000.sql.gz
```

Destroys data by design, so it says exactly what it is about to replace, shows
the target with the password masked, and makes you type `restore`.

Then it stops the services, **backs up what it is about to overwrite** —
restoring the wrong file should not be unrecoverable — restores, brings the
schema up to the running code, and starts the services with a health check.

Running it with no argument lists what is available.

## Rolling back a release

`update.sh` does this automatically on failure. To do it deliberately:

```bash
cd /opt/kasbbook-v2
sudo git log --oneline -10
sudo git reset --hard <commit>
sudo ./venv/bin/pip install -q -r requirements-v2.txt
sudo install -m 644 deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart kasbbook-bot kasbbook-api
```

**Schema first.** If the version you are going back to predates a migration,
downgrade before restarting, or the code will meet columns it does not know
about:

```bash
sudo ./venv/bin/alembic downgrade -1
```

Every migration here has a working `downgrade`, and a test asserts they roll
all the way back to base — on SQLite and on PostgreSQL.

## Health

```bash
systemctl status kasbbook-bot kasbbook-api
curl -s http://127.0.0.1:8210/readyz
cd /opt/kasbbook-v2 && sudo ./venv/bin/alembic current
```

`systemctl is-active` says `active` even for a service crash-looping under
`Restart=always`. That is why the scripts grep the journal for a traceback
instead of trusting that word, and why a non-zero `NRestarts` on an untouched
service means something is wrong.

## Datastores

```bash
cd /opt/kasbbook-v2/deploy
docker compose ps
docker compose logs postgres --tail 50
docker compose restart redis
```

Both bind to `127.0.0.1` only. Losing Redis is survivable — conversation state
is rebuilt by the next `/start`, and rate limiting falls back to per-process.
Losing PostgreSQL is not; that is what the backups are for.

## Running a second messenger

```bash
sudo cp /etc/systemd/system/kasbbook-bot.service \
        /etc/systemd/system/kasbbook-bale.service
# edit: EnvironmentFile=/opt/kasbbook-v2/.env.bale
sudo systemctl daemon-reload && sudo systemctl enable --now kasbbook-bale
```

With `KASBBOOK_PROVIDER=bale` and `BALE_BOT_TOKEN` in that file. Same database:
an account linked to both messengers is one set of books.

Add the unit name to `UNITS` in `scripts/lib.sh` so the update and health
checks cover it.

## Logs

```bash
journalctl -u kasbbook-bot -f
journalctl -u kasbbook-api --since "1 hour ago" | grep -i error
journalctl -u kasbbook-bot --since today -o cat | grep Traceback
```

`httpx` is pinned to `WARNING` because it logs full URLs at `INFO` and every
bot API puts the token in the path. Do not raise it to debug something; a token
has ended up in a journal here that way once already.

## CI

Two jobs on every push, both on Python 3.12:

| Job | What it runs |
|---|---|
| `tests` | pyflakes over `src/`, `apps/`, `tests/v2`, then the whole suite |
| `postgres` | the migration rehearsal against a real `postgres:16-alpine` |

The second exists because `ADD COLUMN NOT NULL` against a populated table is
fine on SQLite and fails on PostgreSQL — and the only place that combination
occurs is production. It cost three silent deploys before it was written.
