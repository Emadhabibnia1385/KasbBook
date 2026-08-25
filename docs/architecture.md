# Architecture

## The shape

```
  Telegram          Bale            Rubika
      │               │               │
      ▼               ▼               ▼
 ┌─────────────────────────────────────────┐
 │  adapters/     translate payloads       │   no database, no rules
 └───────────────────┬─────────────────────┘
                     ▼
 ┌─────────────────────────────────────────┐
 │  bot/          screens + routing        │   no provider names
 └───────────────────┬─────────────────────┘
                     │
 ┌───────────────────┼─────────────────────┐
 │  api/  ───────────┤                     │   parse, call, translate errors
 └───────────────────┼─────────────────────┘
                     ▼
 ┌─────────────────────────────────────────┐
 │  modules/*/service.py                   │   every rule, exactly once
 └───────────────────┬─────────────────────┘
                     ▼
 ┌─────────────────────────────────────────┐
 │  modules/*/models.py  ·  shared/        │
 └───────────────────┬─────────────────────┘
                     ▼
        PostgreSQL   ·   Redis   ·   Alembic
```

Two clients — the bot and the HTTP API — sit on one set of application
services. That is the whole design in a sentence, and everything below is a
consequence of it.

## Why the seams are where they are

### Adapters translate and nothing else

`MessagingAdapter` is a protocol: payload in, `IncomingEvent` out; `OutgoingMessage`
in, provider call out. An adapter has no session, no service, and no idea what
a permission is.

This is enforced rather than asked for. `test_the_adapter_never_reaches_the_database`
parses every module in `adapters/` and fails if any of them imports SQLAlchemy
or a service. It walks the import graph rather than searching the text, so a
comment mentioning a model cannot fail the build and a real import cannot hide
inside a string.

The payoff was measurable: adding Bale took four lines of configuration,
because Bale's API *is* the Telegram Bot API with a different host, and the
dialect lives in `adapters/botapi.py` once.

### The conversation layer names no provider

`bot/conversation.py` routes callbacks and `bot/screens.py` renders them.
Screens are pure functions — data in, text and buttons out — so all 71 of them
are tested without a token, a network, or a database.

The provider arrives as a constructor argument, taken from `adapter.provider`.
It used to be hardcoded to `Provider.TELEGRAM` in the runner, which meant a
Bale update would have resolved to whichever Telegram account shared its
numeric id. The test that runs the same loop against Bale is what found it.

### Rules live in services, once

If a rule were in a route, the bot would not obey it. If it were in a screen,
the API would not. So `books.require(book_id, user_id, permission)` is the one
gate, and both clients pass through it.

The corollary is that neither client may reach past it. When the reports route
wanted a transaction count it did not query for one — `Summary` gained a
`count` field, and both callers got it.

### Money is a Decimal everywhere and a string at the edge

`shared/money.py` defines `Money`, a `TypeDecorator` that is `Numeric(28, 4)`
on PostgreSQL and `String(40)` on SQLite. Nothing is ever a float.

At the HTTP boundary money is serialised as a **string**, because JSON's only
numeric type is a float and `12500000.15` does not survive that round trip.

### The calendar is Jalali, the storage is not

Dates are stored as ordinary `date` columns. A period like `1403-05` is
converted to a Gregorian `[start, end]` range *before* any query runs, in
`shared/jalali.py`. The database never sees a Jalali value, and the user never
sees a Gregorian one.

## The identity model

A KasbBook account is a `User` with a UUID. A Telegram account is an
`Identity` pointing at it.

```
   User (uuid)
     ├── Identity(telegram, 555001)
     ├── Identity(bale, 900123)
     └── Identity(web)
```

No messenger id is ever the account. A person can lose a Telegram account,
change a phone number, or move to Bale, and their books do not move with it.
A unique constraint on `(provider, external_id)` is what stops one messenger
account feeding two sets of books.

## The ledger

Every transaction writes a `Transaction` row **and** a balanced `JournalEntry`
with at least two `JournalLine`s. `trial_balance()` sums debits and credits for
a book and the tests assert they agree — after recording, after deleting, after
settling a debt, after paying a loan instalment.

See [double-entry.md](./double-entry.md).

## What runs where

| Process | Unit | What it is |
|---|---|---|
| Bot | `kasbbook-bot` | polls one provider, handles updates, runs the reminder loop beside the poller |
| API | `kasbbook-api` | uvicorn, two workers, bound to loopback |
| PostgreSQL | container | isolated from the host instance on purpose |
| Redis | container | conversation state and rate limiting |

One process runs one provider. A Bale bot is a second copy of the unit with its
own environment file — never one process holding two identities.

## Directory map

```
src/kasbbook/
  adapters/      base.py (the protocol), botapi.py (the shared dialect),
                 telegram.py, bale.py, rubika.py
  bot/           conversation.py, screens.py, quick.py, state.py
  api/           app.py, deps.py, schemas.py, errors.py, ratelimit.py, routers/
  modules/       identity, books, ledger, budgets, debts, loans, recurring,
                 reports, reminders, treasury, payroll
  shared/        money, jalali, parsing, settings, database, errors, security
  models.py      the registry Alembic autogenerate reads

apps/bot/        runner.py (the entry point), reminders.py
migrations/      alembic env, comparators, versions/
deploy/          docker-compose.yml, the two systemd units
scripts/         install, update, backup, restore, uninstall, lib
tests/v2/        379 tests
```

## Deliberate non-choices

- **No ORM lazy loading across the async boundary.** Relationships that a
  caller needs are `lazy="selectin"`; a payslip built in memory sets
  `payments=[]` explicitly rather than triggering a load nobody can await.
- **No service commits.** The caller owns the transaction — with exactly one
  exception, documented where it happens: refresh-token theft detection
  commits its revocation before raising, because the caller rolls back on
  failure and the revocation must survive the failure it causes.
- **No `select *` into a dict.** Services return models or small dataclasses,
  so a renamed column is a failing import rather than a missing key at runtime.
