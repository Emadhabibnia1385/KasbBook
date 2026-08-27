---
name: kasbbook
description: Engineering constitution and safe-work protocol for KasbBook — the Persian/Jalali small-business bookkeeping bot and API (FastAPI, SQLAlchemy 2 async, PostgreSQL, Alembic, Redis, Telegram/Bale/Rubika adapters, double-entry ledger). Read it BEFORE changing anything here, and before debugging anything odd here, because failures in this project tend to be silent. Use it when the task touches src/kasbbook/, apps/bot/runner.py, migrations/, deploy/, scripts/ or tests/v2/, or the subject is this product's behaviour — books, transactions, the ledger and trial balance, categories, search, reports and CSV export, receipts, budgets, debts, loans, recurring rules, the daily digest and reminders, payroll, treasury, member shares, identities and messenger linking, auth tokens and API keys, rate limiting, webhooks, or deploying to the server. Applies even when the change looks small or the repo is unnamed. Not the separate Seamless/ConfigFlow VPN-reseller bot, which has its own skill.
---

# KasbBook — Engineering Constitution

KasbBook keeps the books for real small businesses: shopkeepers, freelancers,
small teams splitting profit. Money is exact, the calendar is Jalali, and every
transaction has a balanced double-entry journal behind it. A wrong change here
does not throw an error — it quietly records the wrong amount, or pays the
wrong share, or stops speaking and lets someone believe their books are fine.

This skill is the working protocol. The *facts* live in `docs/` (thirteen
pages); this is how to work without breaking them.

---

## 0. The one thing to know first

**Tests are the criterion of correctness here, and writing them is mandatory.**

If you have also worked in the sibling `Seamless_bot` repository, unlearn its
rule: there, tests are forbidden because they mock the boundaries where the
real bugs live. KasbBook is the opposite. It has 406 tests that run on SQLite
with no network and no token in about forty seconds, they test through the same
seams a user crosses, and they have caught real production bugs repeatedly.

Do not ship a change without running the suite. Do not add a feature without a
test for the happy path, a refusal, and an isolation case.

A fresh checkout has no virtualenv — make one before you start, or you will
reach the end of a change with nothing to run:

```bash
python3 -m venv venv
./venv/bin/pip install -q -r requirements-dev.txt
./venv/bin/pip install -q --no-deps -e .
./venv/bin/python -m pytest tests/v2 -q
```

The editable install matters: it is what makes `kasbbook` importable because it
is installed rather than because something arranged `sys.path`. Six migration
tests skip without `KASBBOOK_TEST_POSTGRES_URL`, and two packaging tests skip
below Python 3.11 — both are expected locally and both run in CI.

---

## 1. Operating principles

Ranked. When two conflict, the earlier wins.

1. **Every rule lives in a service, exactly once.** `modules/<area>/service.py`
   is where a rule goes. If it were in a route the bot would not obey it; if it
   were in a screen the API would not. Both clients call the same service, and
   a test asserts they agree.

2. **Neither client may reach past the service.** When a route or a screen
   wants something a service does not expose, add it to the service — do not
   query around it. The reports router once called `ReportService._rows()` for
   a count; the fix was a `count` field on `Summary`, which both callers got.

3. **Comment the why, never the what.** This codebase explains reasoning at
   every non-obvious decision, and that is what stops the next person
   "fixing" something deliberate. Match it. `# increment counter` is noise;
   `# The send is recorded before it is attempted: a duplicate reminder is
   worse than a missed one` is why the code survives review.

4. **Prefer a failing build to a silent wrong answer.** Almost every bug this
   project has had was silent. When you must choose between a check that is
   noisy and one that is quiet, choose noisy.

5. **Read the whole path before editing the middle.** Where does the value come
   from (callback, state, DB row, setting) and where does it go (DB write,
   journal entry, message)? Know both ends first.

6. **Simplest correct thing, every time.** Fewer lines, fewer concepts, clearer
   responsibilities. No abstraction, helper, wrapper or dependency that does
   not solve a problem you actually have. Three boring explicit lines beat one
   clever one, because the person debugging a wrong payslip at midnight is not
   in the mood to be impressed.

7. **Fix the shape, do not stack on it.** If the code you need to change is
   structurally wrong, refactor what is necessary rather than adding another
   layer on top. A workaround built over a workaround is how a codebase stops
   being changeable. Refactor only what the change requires — do not rewrite
   code that happens to be nearby.

---

## 2. Never implement an interface from memory

Check the installed version, then read that version's documentation. This
applies to a provider's bot API, a library, a database behaviour, or any
pattern you have not personally verified in this codebase.

```bash
./venv/bin/pip show sqlalchemy fastapi httpx pyjwt   # what is actually installed
```

Where documentation and memory disagree, documentation wins. Where this
project's code and the documentation disagree, **investigate before changing
either** — the code may be working around something real, and the comment
above it usually says what.

This is not a general caution; it is specific to what this project already is.
The Bale and Rubika adapters were written from published documentation and, in
the roadmap's own words, "have not been tested against their live APIs".
Anything you add there is a second guess stacked on a first one, so verify
against the provider's documentation rather than against the adapter beside
you, and say plainly which parts remain unverified.

## 3. Hard rules — verified properties of this codebase

Each of these is real, and most are enforced by a test that will fail if you
break it.

- **Money is `Decimal`, never a float, anywhere.** `shared/money.py` defines
  `Money`, a `TypeDecorator` that is `Numeric(28,4)` on PostgreSQL and
  `String(40)` on SQLite. Use `quantize()` and `to_decimal()`.

- **Money crosses HTTP as a string.** JSON's only numeric type is a float and
  `12500000.15` does not survive that round trip. `MoneyModel` in
  `api/schemas.py` does this; inherit from it for anything carrying a Decimal.

- **Dates are stored Gregorian and shown Jalali.** Convert a period to a
  `[start, end]` range with `shared/jalali.py` *before* any query. The database
  never sees a Jalali value; the user never sees a Gregorian one.

- **Every transaction writes a balanced journal entry.** `LedgerService.record()`
  does both. `trial_balance()` must stay equal — assert it in any test that
  creates or deletes financial rows.

- **`books.require(book_id, user_id, permission)` is the only gate.** Start
  every service method that touches a book with it. It raises `NotFound` — not
  `PermissionDenied` — for a non-member, so book ids cannot be probed by
  watching which error returns.

- **An adapter translates payloads and nothing else.** No session, no service,
  no permission logic. `test_the_adapter_never_reaches_the_database` parses
  every module in `adapters/` and fails the build on an import of SQLAlchemy or
  a service.

- **Services do not commit.** The caller owns the transaction. There is exactly
  one documented exception, in `AuthService.refresh` — read the comment there
  before adding a second.

- **One process runs one provider.** `KASBBOOK_PROVIDER` picks it and the
  adapter's own `provider` attribute is the source of truth downstream. Never
  hardcode `Provider.TELEGRAM`; that was a real bug that would have resolved a
  Bale update to a Telegram account with the same numeric id.

- **Screens are pure functions.** Data in, text and buttons out. No database,
  no network, no provider. That is what lets every one of them be tested
  without a token.

- **Persian is the UI language.** Screens, user-facing errors. Code, comments,
  docs and commit subjects on `v2` are English.

---

## 4. The guard tests, and what they refuse

These exist to catch a *class* of mistake rather than an instance. If one
fails, it is almost certainly right and you are almost certainly wrong.

| Test | Refuses |
|---|---|
| `test_the_adapter_never_reaches_the_database` | an adapter importing persistence |
| `test_no_two_features_share_a_callback_prefix` | two features routed by one prefix |
| `test_every_button_prefix_the_screens_emit_is_routed` | a dead-end button |
| `test_the_call_table_covers_every_outgoing_method` | an adapter method with no test |
| `test_every_adapter_implements_the_whole_protocol` | a provider missing a method |
| `test_migrations_do_not_import_application_code` | a migration that will rot |
| `test_the_migration_and_the_models_have_not_drifted` | a model changed without a migration |
| `test_alembic_runs_from_a_clean_process` | an import order that only works under pytest |
| `test_the_runner_loads_when_executed_as_a_script` | code that breaks when systemd runs it |
| `test_the_two_dependency_lists_agree` | pyproject and requirements drifting |

**Callback prefixes currently taken:** `acc bg book dt ln nav noop pf pr qk rep
rm rr sh sr td tf tx` (and `rb`/`rc` for report periods). Pick a free one; the
guard will tell you if you did not.

---

## 5. Landmines

Short version. Full accounts with symptoms in `docs/troubleshooting.md` — read
it before debugging anything odd, because the symptom rarely pointed at the
cause in any of these.

- **`ALTER TABLE ... ADD COLUMN NOT NULL` needs a `server_default`.** Fine on an
  empty table, fine on SQLite, fails on a populated PostgreSQL — which is the
  only place that combination occurs. CI rehearses migrations against a real
  PostgreSQL with rows already in the tables; that job exists because this
  reached production three deploys running.

- **`Money` and autogenerate.** If `alembic revision --autogenerate` reports a
  type change for money columns, `migrations/comparators.py` is broken. Those
  diffs are not cosmetic — each is an `ALTER COLUMN TYPE` that rewrites a table
  to the type it already has.

- **A percentage is not an amount.** `parse_amount("۵۰م")` is fifty million.
  For percentages and weights (treasury rules, member shares) parse plain
  digits, or you get a rule for fifty million percent.

- **Three modules are empty placeholders**: `modules/compensation/`,
  `modules/exchange/`, `modules/transactions/` contain only `__init__.py`.
  Their names are misleading — the real code is in `payroll/` and `ledger/`.

- **A model nothing writes to is a feature nobody can use.** `ShareRule` was
  read by `calculate()` and written by nothing, so payroll produced zero
  payslips on a real book. The tests missed it because their setup wrote share
  rules directly to the session — the setup did what the product could not.
  **When you add a model, add the path that creates it, in the same change.**

- **Coverage gaps cluster.** Two adapter methods raised `TypeError` on their
  first line and shipped, because they were the only two nothing exercised.
  Ask which methods have no test before asking which look wrong.

---

## 6. Deployment — never improvise

```bash
ssh seamless                       # connects as `claude`, not root
sudo bash /opt/kasbbook-v2/scripts/update.sh
```

That script is the only supported path. It backs up, runs the tests, migrates,
rewrites the systemd units from `deploy/`, restarts, checks health, and **rolls
back** on any failure. Do not run `git pull` and `systemctl restart` by hand;
you lose all of that.

Three things about the server that have each caused an incident:

- **`sudo` is required.** The checkout is root-owned; without it git refuses
  with "dubious ownership".
- **`systemctl is-active` says `active` for a crash-looping service**, because
  `Restart=always` keeps bringing it back. Check `NRestarts` and
  `curl 127.0.0.1:8210/readyz` too.
- **A script that updates the tree it lives in must not run from that tree.**
  `update.sh` rewrote itself mid-run once; bash kept its byte offset and
  executed a splice of two versions. It now execs from a temp copy.

---

## 7. Adding a feature

The full walkthrough with the reasoning behind each step is in
`references/adding-a-feature.md`. Read it when you are about to add one — the
order matters, and step 7 is the one people skip.

The shape, briefly: model → migration → service → screens → routing → API
route → tests. Both clients, one service. Every feature gets an isolation test
proving another account cannot reach it.

---

## 8. Where to read what

| Question | File |
|---|---|
| Why is the code shaped this way? | `docs/architecture.md` |
| How does the ledger stay balanced? | `docs/double-entry.md` |
| What is a book / identity / permission? | `docs/data-model.md` |
| Periods, shares, funds, payslips? | `docs/payroll.md` |
| Telegram vs Bale vs Rubika? | `docs/providers.md` |
| Endpoints and conventions? | `docs/api.md` |
| Tokens, hashing, what is stored? | `docs/security.md` |
| Deploy, back up, roll back? | `docs/operations.md` |
| Tests, migrations, conventions? | `docs/development.md` |
| Something is behaving oddly | `docs/troubleshooting.md` |
| What is deliberately not built? | `docs/roadmap.md` |

`docs/roadmap.md` matters more than it sounds: several things are absent on
purpose, with reasons. Check it before "fixing" an omission.

---

## 9. Working style

- **Look at git before you touch anything.** `git branch --show-current` and
  `git status`. Work happens on `v2`, which is expected to become `main`, so
  its stability is not yours to spend. Never reset, discard, force-push or
  otherwise destroy work you did not create, and never without being asked.
- **Run the suite before and after.** `pytest tests/v2 -q`. If it was red
  before you started, say so rather than absorbing someone else's failure.
- **Verify claims against the code, not memory.** This project's own docs
  carried a wrong line about budgets until it was checked.
- **Commit subjects in English on `v2`**, imperative, saying what changed for a
  user or an operator. The body explains why — half of
  `docs/troubleshooting.md` was written from commit bodies.
- **When the skill and the code disagree, the code wins.** Say so, so this
  file can be corrected.
- **Stop and ask** on anything destructive, anything touching production data,
  or a design decision with consequences you cannot see the end of.
