# Development

## Setting up

```bash
git clone https://github.com/Emadhabibnia1385/KasbBook.git
cd KasbBook
python3 -m venv venv
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/pip install --no-deps -e .
./venv/bin/python -m pytest tests -q
```

The editable install is what makes `kasbbook` importable because it is
installed, rather than because something arranged `sys.path` first. That
arrangement has broken three times — see [troubleshooting.md](./troubleshooting.md).

The suite runs on SQLite, in process: no network, no bot token, no database
server, nothing that reaches outside the checkout. A clone and the dev
requirements are the whole setup, and CI is what says it passes.

A stopwatch reading stood here — "about forty seconds" — and it had rotted. It
went the way the README's test-count badge went in `1100f63`, and for the same
reason: a measured number in prose is a promise to re-measure it forever. A
runtime rots more quietly than a count, because nobody is reminded of it by
running the thing.

Six migration tests skip unless `KASBBOOK_TEST_POSTGRES_URL` is set — that is
what lets a laptop without PostgreSQL still run everything else.

```bash
export KASBBOOK_TEST_POSTGRES_URL=postgresql+asyncpg://kasbbook:pw@127.0.0.1:5435/kasbbook_test
./venv/bin/python -m pytest tests/test_migrations_postgres.py -q
```

## Lint

```bash
./venv/bin/python -m pyflakes src/kasbbook apps tests migrations/comparators.py
```

pyflakes only — no formatter, no import sorter. It catches the things that are
actually bugs: undefined names, unused imports, unreachable code.

Note that **pyflakes ignores `# noqa`**. When imports exist for a side effect —
as in `models.py`, where Alembic autogenerate only sees what has been imported
— say so with `__all__`, which the linter reads, rather than a comment it does
not.

## Conventions

**Comments explain why, not what.** `# increment the counter` above `count += 1`
is noise. `# The send is recorded before it is attempted: a duplicate reminder
is worse than a missed one` is the reason the next person does not "fix" it.

**Tests are named as sentences.**
`test_reusing_a_spent_token_signs_the_whole_family_out` tells you what broke
from the failure line alone.

**Dates are pinned.** `DAY = date(2026, 8, 24)`, never `date.today()`. A test
that reads the real clock fails on some future Tuesday for reasons nobody
connects to the code.

**Money is `Decimal`.** Never a float, anywhere, including in a test.

**Persian is the UI language.** Screens, errors a user sees, commit subjects on
`main`. Code, comments and these docs are English.

**A service's own refusal, if it is Persian, is user-facing copy.**
`screens.user_message()` passes a message that already contains Persian
straight through to the person, so a sentence raised in
`modules/<area>/service.py` is held to the same vocabulary, digit and
half-space rules as a screen. Two guards apply them:
`tests/test_bot_ux_fixes.py` over `bot/`, and `tests/test_copy_rules.py` over
`modules/` and `shared/`, which reads the first argument of every error it
finds raised there. The alternative is to raise it in English and map it in
`screens/common.py`, which is where an error the API also answers with
belongs.

## Adding a feature

The shape most features take:

1. **Model** — `modules/<area>/models.py`, registered in `src/kasbbook/models.py`
   so autogenerate can see it.
2. **Migration** — `alembic revision --autogenerate`. Read what it produced; it
   is a draft, not a decision. Add `server_default` for any `NOT NULL` column
   on a table that already has rows.
3. **Service** — `modules/<area>/service.py`. Every rule lives here, and it
   starts with `await self.books.require(...)`.
4. **Screens** — the feature's module in `bot/screens/`. Screens are pure
   functions. Shared code goes only in `screens/common.py`. Export each new
   screen explicitly from `screens/__init__.py`. Pick a callback prefix that is
   not taken; the guard test will tell you if it is. Keep each payload within
   64 bytes. Then run `tests/test_screens_architecture.py`.

   Build the keyboard from `back_row()`, `cancel_row()` and `rows_of()` rather
   than writing the glyphs and the row nesting out by hand. That is not
   tidiness: hand-written rows are how «انصراف» came to be spelled two ways
   depending on which feature you were in. The layout grammar they enforce —
   the primary action alone, peers paired, a destructive action on its own row,
   back or cancel last, never more than three to a row — is in
   [conversation-design.md](./conversation-design.md).
5. **Routing** — the feature in `bot/features/` that owns the area: add the
   prefix to its `prefixes` (and the draft flow to its `flows`, if it reads text).
6. **API** — a router in `api/routers/`, calling the same service.
7. **Tests** — at least: the happy path, one refusal, and one isolation test
   proving another account cannot reach it.

### Migrations

```bash
export KASBBOOK_DATABASE_URL="sqlite+aiosqlite:///scratch.db"
./venv/bin/alembic upgrade head
./venv/bin/alembic revision --autogenerate -m "what changed"
```

Autogenerate against a database **already at head**, or it will try to create
everything.

Migrations carry no application imports — `render_item` in `env.py` emits
`sa.Numeric(28, 4)` rather than `kasbbook.shared.money.Money`, so a migration
still applies years from now after the class has moved. A test enforces it.

If autogenerate reports a type change for money columns, `compare_type` in
`migrations/comparators.py` is broken. Those diffs are not cosmetic: on
PostgreSQL each is an `ALTER COLUMN TYPE` that rewrites a whole table to the
type it already has.

## The guard tests

Some tests exist to catch a *class* of mistake rather than an instance. Worth
knowing before you trip one:

| Test | Refuses |
|---|---|
| adapter import graph | an adapter importing SQLAlchemy or a service |
| callback prefix collisions | two features routed by the same prefix |
| dead-end buttons | a prefix a screen emits that nothing routes |
| outgoing-method coverage | an adapter method with no test case |
| migration imports | a migration importing application code |
| model/migration drift | a model changed without a migration |
| script entry point | `runner.py` failing when run as a script, as systemd runs it |

The last one is there because importing a module and executing it as a script
are different, and that difference took the bot down once.

## Testing style

**Test through the seam a user crosses.** Conversation tests build an
`IncomingEvent` and assert on the reply — the same path a button press takes.
API tests use `ASGITransport` against the real app. Only adapter tests mock,
and only at HTTP.

**Assert the arithmetic, not just the absence of an error.** A payroll test
that checks `net_pay == Decimal("42000000")` catches a wrong share formula. One
that checks a payslip exists does not.

**Isolation tests are not optional.** Every feature gets one proving a second
account cannot reach the first account's data. That is the bug class that
matters most and shows up least in manual testing.

## Repository layout

```
src/kasbbook/     the package: adapters, bot, api, modules, shared
apps/bot/         the runnable entry point and the reminder loop
migrations/       alembic env, comparators, versions
deploy/           compose file and the two systemd units
scripts/          install, update, backup, restore, uninstall
tests/         everything
docs/             these files
```

## The documentation site

`docs/` is both what GitHub shows and what the published site is built from, so
there is one copy and it cannot be right in one place and stale in the other.

```bash
./venv/bin/pip install "mkdocs-material>=9.5,<10"
./venv/bin/mkdocs serve      # http://127.0.0.1:8000, reloads as you edit
./venv/bin/mkdocs build --strict
```

`--strict` is what CI runs: a broken internal link fails the build instead of
waiting for a reader to find it. Adding a page means adding it to `nav` in
`mkdocs.yml` — a file that is not in the nav still builds, but nothing links to
it.

## Commits

English subjects, in the imperative, saying what changed for a user or
an operator. The body explains **why** — especially when the change is small
and the reason is not obvious.

A commit that fixes a bug should say what the bug looked like. Half of
[troubleshooting.md](./troubleshooting.md) was written from commit bodies.
