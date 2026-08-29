# Troubleshooting

Every entry below is a failure that actually happened in this project, what it
looked like, and what it turned out to be. They are written down because the
symptom rarely pointed at the cause.

---

## `ModuleNotFoundError: No module named 'telegram'`

**Where it appeared:** the systemd unit, then `migrations/env.py`, then uvicorn.
Three times, months apart.

**What it looked like:** a missing dependency nobody had asked for.

**What it was:** two packages answered to the name `kasbbook` — the current one
in `src/`, and the first-generation bot at the repo root. Whichever came first
on `sys.path` won, silently. The old one imports `python-telegram-bot`, which
this project no longer depends on, so the error named a module that had nothing
to do with what was being started.

The uvicorn case was the subtlest: `PYTHONPATH=/opt/kasbbook/src` was set
correctly, but `WorkingDirectory` puts the repo root ahead of `PYTHONPATH`, so
the root package still won.

**Fix:** the first generation was removed from the codebase. Before that,
each site ordered `sys.path` explicitly with a comment saying why.

**If you see it again:** something has put the repo root ahead of `src/`. Print
`sys.path` at the point of failure; do not guess.

---

## A migration ran, said nothing, and did not apply — for three deploys

**What it looked like:** deploys reported success. The bot then failed on a
column that did not exist.

**What it was:** `ALTER TABLE ... ADD COLUMN ... NOT NULL` against a table that
already had rows. Fine on an empty table, fine on SQLite (which rebuilds the
table in batch mode and applies the Python-side default), and a
`NotNullViolationError` on PostgreSQL — a combination that only occurs in
production.

It stayed invisible because the deploy script piped alembic through
`grep -E "Running upgrade|ERROR"`, and a Python traceback contains neither word.

**Fix:** three things.
1. `server_default` on the column, in both the migration and the model.
2. The deploy script no longer filters output. That is the first comment in it.
3. `tests/test_migrations_postgres.py` walks the revisions one at a time and
   seeds a row after each, which is the shape production actually has when the
   next migration arrives.

**Proof it works:** with the `server_default` removed, SQLite reports 5 passed
and the PostgreSQL rehearsal reports 4 failed.

---

## The daily digest never arrived, and neither did any error

**What it looked like:** silence. The service was active, the log was clean.

**What it was:** `TelegramAdapter.send_plain` passed its parameters to `_call`
as a positional dict where `_call` takes keyword arguments. It raised
`TypeError` on the first line of its body, every time. `send_stored_file` — the
one that shows a receipt — had the same bug.

Neither was covered. The reminder tests use a spy adapter; the receipt tests
assert on the reply object without ever handing it to Telegram. So the only two
outgoing methods nothing exercised were exactly the two that were broken.

**Fix:** one line each, plus a table of every outgoing method actually called
against a mock transport, plus a test that compares that table to the class and
fails when a method has no case.

**The lesson worth keeping:** coverage gaps cluster. Ask which methods have no
test *before* asking which ones look wrong.

---

## Refresh-token theft detection ran, logged, and undid itself

**What it looked like:** replaying a spent refresh token was correctly refused,
but the legitimate holder's newer token still worked. The family was supposed
to be dead.

**What it was:** on detecting reuse, the service revoked the whole family and
raised. Raising made the request-scoped session roll back — including the
revocation it had just written.

**Fix:** the revocation commits before the error is raised. It is the one place
a service commits its own work, and the comment there says why.

---

## Autogenerate wanted to rewrite thirty tables that had not changed

**What it looked like:** every `alembic revision --autogenerate` produced
`ALTER COLUMN ... TYPE NUMERIC(28,4)` for every money column in the schema.

**What it was:** `Money` is a `TypeDecorator` over `Numeric(28, 4)`. Alembic
compared the decorator class against the `NUMERIC` it read back from the
database, saw two different classes, and reported a change.

On PostgreSQL each of those rewrites a whole table to the type it already has.

The existing drift test could not have caught it: it ran with
`compare_type=False`, which also meant it could never have caught a *real* type
change.

**Fix:** `migrations/comparators.py` holds a `compare_type` hook that knows what
`Money` is. It lives in its own module because `env.py` only imports under
Alembic, and a rule this consequential should be testable directly.

---

## `BadRequest` was being swallowed as a network error

**What it looked like:** nothing, yet. A test caught it first.

**What it was:** in python-telegram-bot, `BadRequest` is a *subclass* of
`NetworkError`. A transient-error check written as
`isinstance(err, NetworkError)` would have quietly retried genuine API
rejections forever.

**Fix:** `type(err) is NetworkError`.

**The lesson:** check the class hierarchy of any exception you catch broadly.

---

## A callback prefix was routed twice

**What it looked like:** three unrelated tests failing on a UUID parse.

**What it was:** `rc:` meant both "report CSV" and "recurring". The first
matching branch won, and the other feature's buttons parsed a report keyword as
a UUID.

**Fix:** recurring became `rr:` — and two AST guard tests now exist: no prefix
is routed twice, and no prefix a screen emits goes unrouted. Those catch the
class, not the instance.

---

## Tests that passed today and would have failed tomorrow

**What it was:** several tests read `date.today()`. They passed on the day they
were written.

**Fix:** dates are pinned — `DAY = date(2026, 8, 24)`. A test that reads the
real clock is a test that fails on some future Tuesday for reasons nobody will
connect to the code.

---

## `dubious ownership in repository`

**What it looked like:** `git pull` refusing to run during a deploy.

**What it was:** git refuses to operate on a directory owned by another user.
The checkout is root-owned; the deploy runs under `sudo`, which is correct, but
a bare `ssh` session is not root.

**Fix:** the scripts call `git config --global --add safe.directory` for exactly
that path, and `need_root` fails early with a message that says to use `sudo`
rather than letting git produce a confusing one.

---

## The update reported success and left the API down

**What it looked like:** `update.sh` printed `✓ kasbbook-api: active, log clean,
0 restarts` and exited zero. The API was crash-looping on
`ModuleNotFoundError: No module named 'kasbbook.api'`, and the step that would
have prevented it — `pip install -e .` — plainly exists in the script that had
just been checked out.

**What it was:** the script rewrote itself while running. bash reads a script
incrementally and keeps a byte offset into the file; `git reset --hard` a few
lines down replaced `update.sh` in place, and bash carried on reading at that
same offset in the *new* content. What executed was a splice of two versions.

Two consequences, and the second is the dangerous one: a step was skipped, and
the health check reported success for a service that was down.

**Fix:** `update.sh` now copies itself and `lib.sh` to a temporary directory and
`exec`s from there before touching the working tree, guarded by an environment
variable so the second run does not recurse.

And the health check was made harder to fool:

- it compares `NRestarts` before and after the wait, because `Restart=always`
  keeps a crash-looping service `active` indefinitely and that word alone means
  very little;
- `--since "-10s"` replaces `--since "10s ago"`, an unambiguous form;
- the API additionally has to answer `/readyz`. A process that has not crashed
  is not the same as a process that serves.

**The lesson:** any script that updates the tree it lives in must not be running
from that tree. This applies to `update.sh` here and to anything shaped like it.

## Everyday checks

```bash
# is it actually running, or just started?
systemctl status kasbbook-bot kasbbook-api
journalctl -u kasbbook-bot -n 50 --no-pager

# does the API think it can reach the database?
curl -s http://127.0.0.1:8210/readyz

# is the schema where the code expects it?
cd /opt/kasbbook && ./venv/bin/alembic current

# what did the last update do?
git -C /opt/kasbbook log --oneline -5
```

A restart count above zero on a service that has not been touched means it is
crash-looping. `systemctl is-active` will still say `active`, because
`Restart=always` keeps bringing it back — which is why the install and update
scripts grep the journal for a traceback instead of trusting that word.
