# Operations

## The scripts

All under `/opt/kasbbook/scripts/`, all needing `sudo`, all sourcing
`lib.sh`.

| | |
|---|---|
| `install.sh` | from nothing to running. Idempotent. |
| `update.sh` | pull, test, migrate, restart — **and roll back if it fails** |
| `backup.sh` | dump, verify, keep the last 14 |
| `restore.sh` | put a backup back, after backing up what it replaces |
| `uninstall.sh` | remove services and checkout; `--purge` for the data too |
| `messenger.sh` | add, list or remove a second messenger |

## Updating

```bash
sudo /opt/kasbbook/scripts/update.sh
```

Rerunning the update also backs up, tests, migrates and verifies an installation
whose checkout already matches the remote commit. A matching commit alone does
not prove that a previous installation completed its migrations or restart.

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
sudo /opt/kasbbook/scripts/backup.sh
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
0 3 * * * /opt/kasbbook/scripts/backup.sh --quiet
```

### Off the box

A backup on the same disk as the database survives a bad migration but not a
dead disk. Copy them somewhere else:

```bash
rsync -az /var/backups/kasbbook/ elsewhere:/backups/kasbbook/
```

## Restoring

```bash
sudo /opt/kasbbook/scripts/restore.sh /var/backups/kasbbook/kasbbook-20260825-030000.sql.gz
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
cd /opt/kasbbook
sudo git log --oneline -10
sudo git reset --hard <commit>
sudo ./venv/bin/pip install -q -r requirements.txt
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

**Data is not code.** Rolling the code back leaves alone everything the newer
version wrote. The recurring catch-up is the case that matters: once
`KASBBOOK_RECURRING=on`, the bot books real transactions. Two ways to undo
them, and only these two:

- **restore the full backup** that `update.sh` took before updating, which puts
  every table back together, ledger and journal included; or
- **reverse each transaction through the application** — the bot's delete, or
  `DELETE /api/v1/books/{id}/transactions/{tx}`. Both go through
  `LedgerService`, which removes the transaction and its journal entry
  together and keeps the books balanced. The owner's recurring notice lists
  what was booked.

Never delete transactions, journal entries or journal lines with SQL, and never
one without the other. A transaction without its entry, or an entry without its
transaction, is a ledger that no longer proves itself — and `trial_balance()`
stops balancing. This is why the upgrade turns recurring booking off first and
runs the preview: the cheapest rollback is the one that has nothing to undo.

## Health

```bash
systemctl status kasbbook-bot kasbbook-api
curl -s http://127.0.0.1:8210/readyz
cd /opt/kasbbook && sudo ./venv/bin/alembic current
```

`systemctl is-active` says `active` even for a service crash-looping under
`Restart=always`. That is why the scripts grep the journal for a traceback
instead of trusting that word, and why a non-zero `NRestarts` on an untouched
service means something is wrong.

## The first generation

`/opt/kasbbook-first-generation` is the original bot, disabled, kept for its
SQLite database rather than its code. Nothing runs from it and nothing reads
it. It is safe to delete once you are sure you will never want those old rows —
which is a decision worth making deliberately rather than during a cleanup.

## Datastores

```bash
cd /opt/kasbbook/deploy
docker compose ps
docker compose logs postgres --tail 50
docker compose restart redis
```

Both bind to `127.0.0.1` only. Losing Redis is survivable — conversation state
is rebuilt by the next `/start`, and rate limiting falls back to per-process.
Losing PostgreSQL is not; that is what the backups are for.

## Running a second messenger

```bash
sudo /opt/kasbbook/scripts/messenger.sh add bale
```

It asks for the token and username, writes `/opt/kasbbook/.env.bale`,
generates `kasbbook-bale.service` from the Telegram unit, starts it and checks
it came up. `list` shows what this box runs; `remove <provider>` stops and
deletes one, keeping the token file so removing the wrong one is a restart
rather than a trip back to BotFather.

Same database, which is the point: an account linked to both messengers is one
set of books.

The new unit carries **two** environment files — the shared one first, its own
second — so the database URL and the signing key stay in one place and
rotating a key is one edit rather than one per messenger.

Nothing has to be registered anywhere. `UNITS` is discovered from the units on
disk, because the array in `scripts/lib.sh` used to be the documented place to
add it and `update.sh` overwrites that file — the edit survived exactly until
the next update and then vanished, dropping the second bot out of the restart
and health loops without a word.

## Recurring rules

The reminder loop books every recurring rule that has come due, on each tick.
It catches up on missed dates as well. A date inside a payroll period that has
been moved past *open* is skipped, because that period's payslips were
computed without it. A rule whose author can no longer record in the book is
paused. The book's owner gets one message listing anything booked late,
skipped or paused.

**Upgrading from a release that did not book them.** Before this release,
nothing called the booking at all, so an existing install has a backlog. Each
rule waits at its start date, and the first tick books every missed date in an
open period, up to 400 per rule. To see that before it happens:

```bash
# 1. hold booking before the update restarts the bot
echo 'KASBBOOK_RECURRING=off' | sudo tee -a /opt/kasbbook/.env
sudo bash /opt/kasbbook/scripts/update.sh

# 2. see exactly what the first run would book (it runs the real thing and rolls back)
sudo bash -c 'set -a; . /opt/kasbbook/.env; set +a; cd /opt/kasbbook && ./venv/bin/python apps/bot/recurring_preview.py'

# 3. pause or delete any rule that should not catch up, then turn booking on
sudo sed -i 's/^KASBBOOK_RECURRING=off$/KASBBOOK_RECURRING=on/' /opt/kasbbook/.env
sudo systemctl restart 'kasbbook-bot*'
```

While booking is off, nothing is lost. Switching it back on catches up every
missed date, and the bot logs a warning at start-up so that a forgotten `off`
does not quietly stop the rent.

With more than one messenger, each bot process runs the loop. A row lock stops
two of them booking the same date. The owner's notice is sent from whichever
process did the booking, so it can only reach the owner on that messenger.

## Switching between polling and webhook

```bash
# in /opt/kasbbook/.env
KASBBOOK_UPDATE_MODE=webhook
KASBBOOK_WEBHOOK_PATH=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
KASBBOOK_API_URL=https://your.host
```

Then restart both units. The bot process registers the webhook at startup and
afterwards only sends reminders; the API serves the updates.

Going back is the same file: set `KASBBOOK_UPDATE_MODE=polling` and restart.
The poller deletes the registered webhook itself, so nothing has to be
unregistered by hand.

Two things to know before switching:

- **A restart of `kasbbook-api` is now a window where updates can be lost.**
  With polling they queue at the provider and arrive afterwards; with a webhook
  the provider retries for a while and then drops them. `update.sh` restarts
  that unit.
- **The secret is in the URL**, so nginx must not log it. The block for this
  host turns off `access_log` for the webhook path; without that, every update
  writes the secret to disk.

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

Three jobs on every push, all on Python 3.12:

| Job | What it runs |
|---|---|
| `tests` | pyflakes over `src/`, `apps/`, `tests`, then the whole suite |
| `postgres` | the migration rehearsal against a real `postgres:16-alpine` |
| `services` | `tests/test_concurrency_services.py`: concurrent draft claims on a real `redis:7-alpine`, concurrent recurring runs on a real PostgreSQL |

The second exists because `ADD COLUMN NOT NULL` against a populated table is
fine on SQLite and fails on PostgreSQL — and the only place that combination
occurs is production. It cost three silent deploys before it was written.
