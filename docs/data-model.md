# Data model

## One account, many identities

```
User (uuid)
  ├── Identity(telegram, "555001")
  ├── Identity(bale, "900123")
  └── Identity(web)
```

A messenger id is never the account. It is a pointer *to* one.

That distinction is the reason a person can lose a Telegram account, switch to
Bale, or change a phone number without their books moving with them. The
alternative — using the Telegram id as the primary key — works right up until
the day it does not, and then it is unrecoverable.

A unique constraint on `(provider, external_id)` enforces the other direction:
one Telegram account cannot feed two sets of books.

### Linking

Two flows, both through a one-time `LinkToken` whose **digest** is stored, never
the token.

| Direction | Who starts | What the other side does |
|---|---|---|
| `FROM_WEB` | a logged-in account asks for a link | the messenger opens a deep link carrying it |
| `FROM_MESSENGER` | an unknown messenger says `/start` | the web panel claims the code it was shown |

Both expire in 15 minutes: long enough to switch apps and paste, short enough
that a leaked link is dead before anyone finds it.

A token issued for Telegram is refused if redeemed from Bale.

## Books

```
Book
  ├── type: personal | business | team | organization
  ├── base_currency
  ├── owner_user_id
  └── Membership[]  →  User, Role
```

The type is not a label. It decides the default `Scope` for a transaction, and
whether payroll exists at all — splitting profit between one person is not a
feature.

## Roles and permissions

`Role` maps to a set of `Permission`. Roles are coarse because people
understand them; permissions are fine because code needs them.

| Role | Roughly |
|---|---|
| `OWNER` | everything, including locking a period and transferring the book |
| `ADMIN` | everything except locking a period |
| `MANAGER` | records, reports, budgets, payroll |
| `MEMBER` | records their own work, sees reports |
| `VIEWER` | reads |

Every service call passes through one gate:

```python
await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
```

It raises `NotFound` — not `PermissionDenied` — when the caller is not a member
at all. A non-member is told the book does not exist, so book ids cannot be
probed by watching which error comes back.

## Transactions

```
Transaction
  flow             income | expense
  scope            personal | work | team
  category         free text, 80 chars
  original_amount / original_currency / conversion_rate / converted_amount
  occurred_on      a date, Gregorian in storage
  receipt_file_id  the provider's own id, if a photo was attached
  → JournalEntry   balanced, always
```

`scope` exists so a team book never accidentally records someone's personal
groceries. It defaults from the book type and can be overridden.

Receipts store the **provider's file id**, never the bytes. Showing one sends
that id back. Nothing is downloaded, nothing is stored, and there is no bucket
of other people's photographs to secure.

Alongside the id sit `receipt_kind`, `receipt_file_name` and
`receipt_mime_type`, because the id is opaque and says none of that. Without
them a PDF invoice and a photograph of a till roll are the same row: the screen
can only say "there is one", and sending it back has to try `sendPhoto` and
wear the rejection before reaching `sendDocument`. All three are nullable —
every receipt attached before they existed has them empty, and the code falls
back to guessing for those.

## Planning

| Model | What it holds |
|---|---|
| `Budget` | a ceiling, per category or per direction, and what has gone against it |
| `Debt` | who, how much, which way, when due — settling writes a real transaction |
| `Loan` | instalment amount and count; payments are `LoanPayment` rows each pointing at a transaction |
| `RecurringRule` | a definition plus `next_run_on`, which moves forward as it fires |

A recurring rule that has fallen behind catches up, capped at 400 firings —
a rule that somehow fell years behind should not spend an afternoon writing
transactions.

## Payroll

```
FinancialPeriod   a window, with a status
  ├── Adjustment[]   bonuses and deductions, signed, approved separately
  ├── Payslip[]      one per member, every input frozen onto it
  │     └── Payment[]   staged: a share is often paid across several transfers
  └── TreasuryAllocation[]   what the funds took, written once
```

Statuses move along a fixed path (`PERIOD_TRANSITIONS`); anything else is a
bug, not a decision. A locked period refuses edits — corrections go in a later
one, which is how accounting works.

A payslip snapshots the distributable total, the share basis, and the share
value. Re-reading last year's payroll shows what was decided then, not what
today's rules would say.

See [payroll.md](./payroll.md).

## Credentials

| Model | Stored | Not stored |
|---|---|---|
| `User.password_hash` | Argon2id | the password |
| `LinkToken.token_digest` | SHA-256 | the code |
| `RefreshToken.token_digest` | SHA-256, plus a family id | the token |
| `ApiKey.token_digest` | SHA-256, plus an 8-char prefix | the key |

The prefix is kept in the clear so a key can be named in a list and revoked
without its owner having to produce it.

### An account can start with none of them

`create_account_from_messenger` makes an account with no email, no phone and no
password — because someone pressing "make me an account" in Telegram has given
us nothing else. That account works, but it is a dead end: it cannot sign in to
the API, a colleague cannot find it to add to a book, and losing the messenger
loses the books, which is the exact failure the identity model exists to
prevent.

So the bot says so on the screen that announces the account, and the account
panel keeps saying so until an email or phone is set. `set_contact` and
`set_password` are the way out, and both are reachable from the bot and the API.

See [security.md](./security.md).

## Audit

`AuditEvent` is append-only and records anything that changes who can see what:
accounts created, identities linked and unlinked, members added and removed,
periods advanced, API keys issued and revoked, refresh tokens detected as
reused.

## Deletion

Closing an account is two different operations depending on what depends on it.

**Books nobody else is on** are destroyed entirely — transactions, journal,
budgets, debts, loans, payroll, treasury. Every foreign key to `books` is
`ON DELETE CASCADE`, so the database does almost all of it; two RESTRICT edges
(`journal_lines → accounts`, `treasury_allocations → treasury_funds`) are
cleared first by `BookService.delete_book`, because the database does not
promise to process a cascade in an order that satisfies them.

**Books shared with other people** stop the whole thing. They are not one
person's to destroy, so the operation refuses and names them; hand them over
first with `transfer_ownership`.

**The account row itself** survives only if it has to. Three foreign keys are
RESTRICT — `transactions.actor_user_id`, `adjustments.recorded_by`,
`recurring_rules.created_by_user_id` — and each one is the ledger saying a
financial record must not lose its author. When records in *other people's*
books name this person, the row is anonymised rather than deleted: no name, no
email, no phone, no password, no identities, `is_active` false, and
`token_generation` bumped so nothing in flight still works. When nothing points
at it, the row is deleted outright.

Both paths free the messenger, so somebody who closes an account and comes back
starts genuinely fresh.
