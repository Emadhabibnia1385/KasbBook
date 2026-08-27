# Adding a feature

The order below is not bureaucracy. Each step exists because skipping it has
produced a specific failure in this project.

---

## 1. Model — `modules/<area>/models.py`

Inherit `UUIDPrimaryKey, Timestamped, Base`. Money columns use `Money` from
`shared/money.py`. Enums use `Enum(TheEnum, native_enum=False, length=N)` so
they behave identically on SQLite and PostgreSQL.

Then register it in `src/kasbbook/models.py` — both the import and `__all__`.
Alembic autogenerate only sees what has been imported, and `__all__` is how
that intent is stated in a way pyflakes reads. (`# noqa` does not work:
pyflakes ignores it.)

## 2. Migration

```bash
export KASBBOOK_DATABASE_URL="sqlite+aiosqlite:///scratch.db"
./venv/bin/alembic upgrade head          # get to head FIRST
./venv/bin/alembic revision --autogenerate -m "what changed"
rm scratch.db
```

Autogenerating against a database that is not at head makes it try to create
everything.

**Read what it produced.** It is a draft, not a decision:

- A `NOT NULL` column on a table that already has rows needs a `server_default`
  — in the migration *and* in the model. Without it the migration is fine on
  SQLite and fails on production PostgreSQL, which is exactly the combination
  nothing but production has.
- If it reports type changes for money columns you did not touch, stop:
  `migrations/comparators.py` is broken.
- Write a real `downgrade`. A test asserts every migration rolls back to base.

Give the file a docstring saying what the tables are for and why they are
shaped that way. The auto-generated header alone is not enough.

## 3. Service — `modules/<area>/service.py`

This is where the rules live. Every method that touches a book starts with:

```python
await self.books.require(book_id, user_id, Permission.SOMETHING)
```

Do not commit. The caller owns the transaction — `api/deps.py` commits per
request, and the bot runner commits per update.

Raise domain errors from `shared/errors.py` (`NotFound`, `ValidationError`,
`PermissionDenied`). They carry their own status code and are translated once,
at each edge. Messages a user will see are Persian.

Return models or small dataclasses, never dicts — a renamed column should be a
failing import, not a missing key at runtime.

## 4. Screens — `bot/screens.py`

Pure functions: data in, `(text, buttons)` out. No database, no network. Wrap
user-facing text in `rtl()` so mixed Persian and digits stay readable, and
format money with `fmt()`.

Pick a callback prefix nobody uses (see the list in SKILL.md). Keep payloads
short — **a callback payload is 64 bytes**, and a Persian category or fund name
will not reliably fit. Where a button has to carry a long value, keep the list
in conversation state and reference it by index; that is what the category
suggestions do.

An empty state deserves as much care as a full one. Say what the feature is
for and what to press, rather than showing a blank list.

## 5. Routing — `bot/conversation.py`

One branch in `_callback`, dispatching your prefix to a handler method. If the
flow collects free text, add a `flow` key to the draft state and a branch in
`_text`.

Anything that acts on an existing row should look the book up **from that row**
rather than trusting a book id in the callback — a button payload is something
a user can edit.

## 6. API — `api/routers/<area>.py`

Schemas in `api/schemas.py`. Anything carrying a `Decimal` inherits
`MoneyModel`, so it serialises as a string.

Call the same service the bot calls. If you find yourself reimplementing a rule
here, stop — that is how the two clients drift, and the drift shows up in
someone's payslip rather than in a test.

Mount the router in `api/app.py`.

## 7. Tests — the step people skip

At minimum, three:

1. **The happy path**, driven the way a user drives it. For the bot that means
   building an `IncomingEvent` and asserting on the reply; for the API it means
   `ASGITransport` against the real app. Not calling the service directly —
   that skips the layer where the bug usually is.
2. **A refusal**: bad input, a missing permission, a rule violated. Assert both
   the message and that nothing was written.
3. **Isolation**: a second account cannot see or touch the first account's
   data. This is the bug class that matters most and shows up least in manual
   testing.

Then:

- **Assert the arithmetic, not the absence of an error.** `net_pay ==
  Decimal("42000000")` catches a wrong formula; "a payslip exists" does not.
- **Pin dates.** `DAY = date(2026, 8, 24)`, never `date.today()`. A test that
  reads the real clock fails on some future Tuesday for reasons nobody will
  connect to the code.
- **Do not build state the product cannot build.** If your test setup writes a
  row directly to the session, ask whether any code path can create that row.
  If none can, you have a feature nobody can reach — that is exactly how
  payroll shipped unable to produce a single payslip.
- **Assert `trial_balance()` stays equal** in any test that creates or deletes
  financial rows.

## 8. Before you call it done

```bash
./venv/bin/python -m pyflakes src/kasbbook apps tests/v2 migrations/comparators.py
./venv/bin/python -m pytest tests/v2 -q
```

Then update what the change made stale:

- `docs/` — the page covering the area, and `docs/roadmap.md` if this closed
  a gap listed there
- the test count in `README.md`, `README.fa.md`, `docs/development.md` and
  `docs/architecture.md` if it moved
- `.claude/skills/kasbbook/SKILL.md` if you added a callback prefix or changed
  an invariant

A commit whose body explains *why* is worth more than one that lists what
changed; git already knows what changed.
