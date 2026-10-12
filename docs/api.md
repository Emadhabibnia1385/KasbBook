# The API

Interactive documentation at `/docs` on your own deployment; the reference
one is at [kasbbook.nyxon.tech/docs](https://kasbbook.nyxon.tech/docs). This page covers the
conventions the OpenAPI schema cannot express.

Base path: `/api/v1`. Health checks sit outside it, at `/healthz` and
`/readyz`.

## Conventions

### Money is a string

```json
{ "converted_amount": "12500000.1500", "original_currency": "IRR" }
```

Never a JSON number. JSON has one numeric type and it is a float;
`12500000.15` does not survive that round trip. Parse it with a decimal type on
your side — `Decimal` in Python, `BigDecimal` in Java, a decimal library in
JavaScript. Do **not** parse it into a `Number`.

### Dates are ISO, periods are Jalali

`occurred_on` is `2026-08-25`. But a report period is `1403-05` — Mordad of
1403 — converted to a Gregorian range before the query runs.

| Period | Means |
|---|---|
| `1403-05` | one Jalali month |
| `1403` | one Jalali year |
| `week` | the current week |
| *(omitted)* | everything |

### Errors

Every error has one shape:

```json
{
  "detail": "این دفتر پیدا نشد",
  "error": {
    "code": "not_found",
    "message": "این دفتر پیدا نشد",
    "request_id": "6f1c2e0a9b8d4c7e8f00112233445566"
  }
}
```

- **`detail`** is unchanged from earlier versions: a sentence, or for a request
  that does not validate, a list of `{loc, msg, type}`.
- **`error.code`** is stable and meant for a program to branch on, rather than
  matching a sentence:
  - `not_found`, `permission_denied`, `auth_error`;
  - `validation_error`, `invalid_request`;
  - `too_many_attempts`;
  - `key_required`, `key_reused`, `key_in_flight`, `key_malformed`;
  - `method_not_allowed`, `internal_error`.
- **`error.fields`** appears on `invalid_request` and gives `loc`, `code` and
  `message` for each field. The value that was sent is **never echoed back**,
  because it can be a password.

| Status | Meaning |
|---|---|
| 404 | not found |
| 403 | denied |
| 422 | invalid |
| 409 | conflict |
| 401 | unauthenticated, with `WWW-Authenticate: Bearer` |
| 429 | rate limited, with a `Retry-After` header in seconds |

An amount of 10^24 or more is a 422.

An unhandled exception is a 500 with the code `internal_error` and a fixed
message. The real error is in the log, never in the response; the log line
carries the same `request_id`.

**Every response**, success or failure, carries an `X-Request-Id` header. Send
your own (8 to 64 characters of letters, digits, `.`, `_` or `-`) and it is kept,
so your logs and ours line up. Anything else is replaced with a fresh id.

### Not-found means not-yours

Asking for a book you are not a member of returns **404**, not 403. Revoking
someone else's API key returns 404. This is deliberate: a 403 would confirm the
id exists.

### Retries: `Idempotency-Key`

A request that moves money can be retried safely. Send an `Idempotency-Key`
header — any 8 to 64 characters of letters, digits, `.`, `_`, `:` or `-`; a UUID
is ideal — and a retry gets the first answer back instead of doing the work
again.

| | |
|---|---|
| Same key, same request | the stored answer, same status and body, with `Idempotent-Replay: true` |
| Same key, different request | **422**: the key belongs to another request |
| Same key, first request still running | **409**: retry shortly and the stored answer comes back |
| Malformed key | **400** |
| A request that failed | nothing is stored — the key is free to retry with a corrected request |

Keys are per account and per route, and kept for **48 hours**.

Guarded routes:
- `POST …/transactions`
- `POST …/conversions`
- `POST …/debts/{id}/settle`
- `POST …/loans/{id}/pay`
- `POST …/periods/{id}/calculate`
- `POST …/periods/{id}/adjustments`
- `POST …/payslips/{id}/payments`

The key is optional on all of them except **`…/payslips/{id}/payments`**, where
it is **required (400 without it)**. That is the request that moves money out
of the book, so it is the one a retry must never repeat.

## Getting a key without leaving Telegram

Account → 🔌 API issues one. It is shown once, concealed behind a tap, and
never again: only a SHA-256 digest is stored, which is what makes a leaked
database worth nothing. Issuing a new one from the bot revokes every key the
account has, so there is never a second key nobody remembers creating.

`POST /auth/api-keys` issues alongside the keys already there instead: one key
per program is what lets one be revoked without stopping the others. Both are
`AuthService` methods (`replace_api_keys`, `issue_api_key`), so the difference
is a choice each client makes, not a rule one of them reimplements.

## Authenticating

Either a bearer token or an API key. Both resolve to the same account, but
only a person's bearer token may manage the account itself — keys, profile,
contact, password, sessions, closing it, and messenger links answer an API key
with 403.

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" ...
curl -H "X-API-Key: kb_..." ...
```

### Register and sign in

```bash
curl -X POST /api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"display_name":"عماد","email":"you@example.com","password":"at-least-8"}'
```

```json
{
  "access_token": "eyJ...",
  "refresh_token": "xK9...",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

An email or a phone is required — an account with no way to be reached cannot
be recovered.

### Staying signed in

```bash
curl -X POST /api/v1/auth/refresh -d '{"refresh_token":"xK9..."}'
```

**Store the new refresh token and discard the old one.** Every refresh rotates.
Presenting a spent token revokes the entire family and signs the session out —
that is theft detection working, not a bug. See [security.md](./security.md).

### The account itself

| | |
|---|---|
| `PATCH /auth/me` | display name, timezone, locale; the daily digest's `digest_enabled`, `digest_hour` (0–23, your own time) and `reminder_days` (0–60, how early a due instalment or debt is mentioned) |
| `PUT /auth/me/contact` | the email or phone this account is reached and recovered by |
| `PUT /auth/me/password` | set or change it — **ends every session, including yours** |

Changing a password signs everything out — refresh tokens and already-issued
access tokens alike, so the bearer you used to make the request stops working
too. Somebody doing it because they fear a leak expects exactly that. Sign in
again afterwards.

An API key is unaffected: it belongs to a program, and a nightly job should not
stop at 3am because a person changed their password.

An address another account already holds is refused with a 422 that does not
confirm the address is registered.

| | |
|---|---|
| `GET /auth/me/deletion-preview` | what closing would destroy, and what would block it |
| `DELETE /auth/me` | closes it — irreversible, no grace period |

`DELETE /auth/me` needs the account's password when it has one; an account with
none is proven by the bearer token alone. It returns 422 when a shared book
blocks it. There is no id to pass: a token can only close its own account.

| | |
|---|---|
| `POST /auth/logout` | ends this session |
| `POST /auth/logout-everywhere` | ends all of them |
| `GET /auth/sessions` | where this account is signed in |

### Keys for programs

```bash
curl -X POST /api/v1/auth/api-keys -H "Authorization: Bearer $T" \
  -d '{"name":"nightly export","expires_in_days":365}'
```

The response is the **only** time the key appears. Listing keys returns the
prefix, never the key.

## Books and transactions

| | |
|---|---|
| `GET /books` | books this account can see |
| `POST /books` | `{"name":"مغازه","type":"business","currency":"IRR"}` |
| `GET /books/{id}/members` · `POST` · `DELETE /{user_id}` | membership |
| `PATCH /books/{id}/members/{user_id}` | `{"role":"accountant"}` — any role but owner |
| `PUT /books/{id}/owner` | `{"user_id":…}` — hand the book to another active member; you stay as admin. Owner only |
| `GET /books/{id}/transactions` | `?since=&until=&page=&per_page=`, newest first |
| `GET /books/{id}/search` | `?q=اجاره&page=&per_page=` — category and description, newest first, with `total_amount` over every match |
| `POST /books/{id}/transactions` | see below |
| `GET`/`DELETE /books/{id}/transactions/{tx}` | one transaction |
| `GET /books/{id}/currencies` · `PUT /{code}` | which currencies this book may hold |
| `GET /books/{id}/wallet` | what it holds, per currency |
| `GET`/`POST /books/{id}/conversions` | move value between two of them |
| `GET /books/{id}/rates/{code}` | today's price of one `code` in the book's currency, or `null` when none is known |

```bash
curl -X POST /api/v1/books/$BOOK/transactions \
  -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"flow":"income","category":"فروش","amount":"250000","occurred_on":"2026-08-25"}'
```

A transaction carries `has_receipt`, `receipt_kind` and `receipt_file_name`.
The file id itself is not returned: it is opaque and scoped to the messenger
holding the file, so it would mean nothing here and handing it out only widens
what a leak exposes. Attaching a receipt is a bot flow — there is no upload
endpoint yet.

`scope` is optional and defaults from the book type. `currency` defaults to the
book's own, and a different one must be a currency the book has enabled and
must carry `conversion_rate` — that rate is frozen on the transaction and never
re-applied. An expense in a currency the book does not hold enough of is
refused; the base currency is exempt.

`GET /rates/{code}` is the figure the bot fills in when someone records tether:
offer it, and send it back as `conversion_rate` if the person accepts it. It is
a suggestion, never applied by itself, because an over-the-counter deal is often
not the market price. `null` means no price is known right now; ask for one.

`POST /books` also takes `currency`, and omitting it now means the same default
the bot uses. It used to mean `IRR`, which is why a book created in the bot
refused every transaction posted to it here.

Adding a member requires that person to already have an account; they are found
by email or phone.

## Reports

| | |
|---|---|
| `GET /books/{id}/reports/summary` | `?period=1403-05` → income, expense, net, count |
| `GET /books/{id}/reports/by-category` | `?flow=expense&period=` → totals and shares |
| `GET /books/{id}/reports/export.csv` | the period as a file, Jalali dates included; text cells starting `= + - @` get a leading `'` |
| `GET /books/{id}/reports/day` | `?date=2026-03-19` → the daily list's split: business, personal, installments, savings |

## Budgets, debts, loans, recurring

| | |
|---|---|
| `GET`/`PUT /books/{id}/budgets` | a ceiling per category; `PUT` because a category has one |
| `DELETE /books/{id}/budgets/{budget}` | |
| `GET`/`POST /books/{id}/debts` | `?include_settled=true` to see closed ones |
| `POST /books/{id}/debts/{debt}/settle` | closes it; `{"record_transaction": true}` also records the money (income if owed to you, expense if you owed). Off by default: if the original sale or purchase is already recorded, recording the payment too counts it twice. A second settle is 422. |
| `GET`/`POST /books/{id}/loans` | instalment amount and count, not a total |
| `POST /books/{id}/loans/{loan}/pay` | records one instalment and its expense |
| `GET`/`POST /books/{id}/recurring` | a rent, a salary, a subscription, booked every `daily`/`weekly`/`monthly` (a Jalali month) from `starts_on` |
| `PATCH /books/{id}/recurring/{rule}` | `{"is_active": false}` pauses, `true` resumes; what it booked stays |
| `DELETE /books/{id}/recurring/{rule}` | the rule goes; what it booked stays |

A loan is described by what one instalment costs and how many there are,
because that is how a loan is described to a person: "twelve of 4,000,000".

A recurring rule is booked by the same loop as the bot's, in the book's own
scope. A `starts_on` in the past is booked back to it on the next run, as the
bot's is, so check the date before sending one. Creating a rule honours
`Idempotency-Key`: a duplicated rule books everything twice, every period.

## Payroll and treasury

Team and organization books only. Every route calls the same service the bot
calls, so a share set here is what Telegram reports and a payslip calculated in
Telegram is what this returns.

| | |
|---|---|
| `GET`/`POST /books/{id}/periods` | list, or open one |
| `PATCH /books/{id}/periods/{p}` | rename, or move the window; payslips are recalculated, payments kept |
| `DELETE /books/{id}/periods/{p}` | only while it has issued no payslip |
| `GET /books/{id}/periods/{p}/distribution` | income − costs − treasury = distributable (never below zero; `shortfall` is a losing month's loss) |
| `POST /books/{id}/periods/{p}/status/{status}` | only the documented transitions |
| `POST /books/{id}/periods/{p}/close` | to locked in one step; 422, with nothing moved, if there are no payslips, they are stale, or anyone is owed |
| `GET`/`PUT /books/{id}/shares` | who takes what; `PUT` end-dates the previous rule |
| `DELETE /books/{id}/shares/{user}` | stop paying this member from today; past periods keep the rule |
| `GET`/`PUT /books/{id}/periods/{p}/performance` | hours, days, points — for measured bases |
| `GET`/`POST /books/{id}/periods/{p}/adjustments` | bonuses and deductions, signed |
| `POST …/adjustments/{a}/approve` | recording and approving are separate |
| `POST /books/{id}/periods/{p}/calculate` | payslips, every input frozen onto them; again, updates them in place and keeps their payments |
| `DELETE /books/{id}/periods/{p}/payslips` | discard the calculation — refused once anyone has been paid |
| `GET /books/{id}/periods/{p}/payslips` | everyone's, or only yours, by permission |
| `GET /books/{id}/payslips/{slip}` | one payslip, by the same rule; someone else's is 404 |
| `POST /books/{id}/payslips/{slip}/payments` | staged; instalments are the norm; any currency the book holds |
| `DELETE /books/{id}/payslips/{slip}/payments/{pay}` | take a payment back while the period is open |
| `GET`/`POST`/`DELETE /books/{id}/funds` | treasury funds |
| `GET`/`POST`/`DELETE /books/{id}/funds/{f}/rules` | what feeds them |

`calculate` returns **422**, not an empty list, when no member has a share. A
run that produces nothing because the question was never answered is not an
empty result.

A payment defaults to the payslip's own currency. Another must be one the book
has enabled and holds enough of, and must carry `conversion_rate` into the
payslip's currency; the payslip counts it at that rate, and each payment in the
response carries its rate so the list reconciles with `paid`. A rate sent with
the payslip's own currency is ignored, as it is on a transaction. `reference`
is at most 80 characters.

Say how much with exactly one of:

| | |
|---|---|
| `amount` | what is handed over, in `currency` |
| `settles` | how much of the payslip this clears, in the payslip's currency; the service works out the amount |
| `rest: true` | everything still owed |

`settles` and `rest` are the bot's "pay" and "pay all", through the same
arithmetic: in another currency the amount is rounded **up** to the fourth
decimal, so a payslip paid off in tether is paid off rather than left a few
toman short that no amount of tether could clear. That lands at most one unit
of the token past the figure, so `outstanding` can read slightly below zero
while `overpaid` stays zero.

```bash
curl -X POST /api/v1/books/$BOOK/payslips/$SLIP/payments \
  -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"amount":"50","currency":"USDT","conversion_rate":"229867"}'

curl -X POST /api/v1/books/$BOOK/payslips/$SLIP/payments \
  -H "Authorization: Bearer $T" -H "Idempotency-Key: $(uuidgen)" \
  -H 'Content-Type: application/json' \
  -d '{"rest":true,"currency":"USDT","conversion_rate":"229867"}'
```

Every route under a period checks the period is in the path's book, and 404s
otherwise, as a payslip and a payment always have.

Deleting a fund that has already taken money is refused — a paid period would
be left pointing at nothing. Deactivate it instead. Deleting a *rule* is always
safe, because what past periods took is snapshotted rather than recomputed.

## Webhooks

`POST /api/v1/webhooks/{provider}/{secret}`

Always answers 200, even for an update that fails — a provider that receives an
error retries, and retrying a poisoned update forever is worse than dropping it
and logging why.

Only reachable when this process is configured to serve webhooks. Otherwise
every path returns 404. See [security.md](./security.md) for what the secret in
the path is doing there.

## Health

| | |
|---|---|
| `GET /healthz` | answers without touching anything; safe to poll hard |
| `GET /readyz` | runs a query; 503 when the database is unreachable |

A process that cannot reach its database is up but not useful, and those are
the deploys that look fine and are not.
# Categories, transaction editing, invitations and account switching

Transaction responses include `activity` with `kind` (`created` or `edited`),
`user_id`, `display_name` and the UTC `at` timestamp. Detail and list endpoints
use the same authorized, batched ledger-service attribution as the bot. The bot
shows either original creation or the latest edit, with the date/time converted
to the book's local Jalali calendar. Category/name, amount, description and
receipt edits update the displayed editor. Original creator/date remain stored.
Historical edited rows lacking reliable editor attribution show an unknown
editor rather than assigning the edit to the creator or guessing from timestamps.

Book categories are shared by all transaction flows. `GET/POST
/api/v1/books/{book_id}/categories`, `PATCH/DELETE
/api/v1/books/{book_id}/categories/{category_id}` use `CategoryService`.
Reading requires transaction visibility. Creation requires `create_category`,
which is granted to owners, admins, accountants and members; renaming and
deletion still require transaction editing. Viewers cannot create categories.
A category with any transaction cannot be deleted. Renaming also updates the
existing category budget, recurring and treasury filters without merging them.

Category creation requires `flow: "income"` or `flow: "expense"`. Category PATCH
accepts name, flow, or both. `GET .../categories?flow=income` (or expense) uses
the same service filter as the bot's transaction picker. A classified category
cannot be used for the opposite transaction flow, including free-text/API
entries. Category type changes affect future recording only: historical
transaction flows, frozen amounts and journal lines remain unchanged.
Legacy categories have `flow: null` and appear as unclassified in management;
choose their type explicitly. They are excluded from the filtered picker until
classified. Their existing transactions remain usable without rewriting history.

`PATCH /api/v1/books/{book_id}/transactions/{transaction_id}` accepts `category`,
`amount` and `description`. Money is a string. Amount means the original
currency amount and retains the stored conversion rate. `description: null`
clears it; null category/amount and empty patches are refused. Financial dates
with calculated payslips or a non-open payroll period are protected. Loan
payment amounts must be changed through their own workflow.

`POST /api/v1/books/{book_id}/invitations` accepts a supported messenger provider,
username or numeric `identifier`, and a non-owner `role`. The recipient must
already have started that provider's bot. Delivery is queued durably for that
provider's poller, webhook activity or reminder loop. `GET /api/v1/invitations`
lists the current user's pending invitations; `POST
/api/v1/invitations/{invitation_id}/respond` accepts `{"accept": true}` or false.
Invitations expire after seven days. Membership is granted only on acceptance,
while the inviter still has member-management permission.

`POST /api/v1/identities/account-login/request` accepts an owned `identity_id`
and destination email/phone `identifier`. It returns only `challenge_id` and
`expires_in`. Proof goes to an existing identity on the same messenger; no
email or SMS delivery is implied. `POST /api/v1/identities/account-login/complete`
accepts the identity, challenge and code. Invalid proof returns `success: false`
so failed attempts are committed. Successful switching invalidates both
accounts' existing access/refresh sessions; authenticate again afterward.
