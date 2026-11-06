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

### Dates are ISO, periods follow the book's calendar

`occurred_on` is `2026-08-25`. But a report period is `1403-05` — Mordad of
1403 on a Jalali book, May of the year 1403 on a Gregorian one — converted to a
Gregorian range before the query runs. Each book has a `calendar` (`jalali`, the
default, or `gregorian`), chosen when it is made (`POST /books`, field
`calendar`) and changeable with `PUT /books/{id}/calendar`. Changing it moves
nothing that was recorded: the same days are grouped into different months from
then on. The Gregorian week runs Monday to Sunday, the Jalali one Saturday to
Friday. `GET /auth/me` carries `suggested_currency` and `suggested_calendar`,
what a new book would start with for the time zone the account is in.

| Period | Means |
|---|---|
| `1403-05` | one month of the book's calendar |
| `1403` | one year of the book's calendar |
| `week` | the current week |
| `w:N` | the week N weeks back (`w:0` is this one, `w:1` last week) |
| `2026-10-01..2026-10-31` | any stretch of days, first to last inclusive (at most ten years); its comparison period is the same number of days straight before it |
| *(omitted)* | everything |

### Errors

```json
{ "detail": "این دفتر پیدا نشد" }
```

Domain errors carry their own status: 404 not found, 403 denied, 422 invalid,
409 conflict, 401 unauthenticated, 429 rate limited (with a `Retry-After`
header in seconds). An amount of 10^24 or more is a 422. Validation failures come
from Pydantic in its own shape, with the offending field.

Unhandled exceptions are always `{"detail": "something went wrong on our
side"}` with a 500. The real error is in the log, never in the response.

### Not-found means not-yours

Asking for a book you are not a member of returns **404**, not 403. Revoking
someone else's API key returns 404. This is deliberate: a 403 would confirm the
id exists.

## Getting a key without leaving Telegram

Account → 🔌 API issues one. It is shown once, concealed behind a tap, and
never again: only a SHA-256 digest is stored, which is what makes a leaked
database worth nothing. Issuing a new one revokes the old, so there is never a
second key nobody remembers creating.

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
| `PATCH /auth/me` | display name, timezone, locale, and the digest: `digest_enabled`, `digest_hour` (0-23), `reminder_days` (0-60) |
| `PUT /auth/me/contact` | the email or phone this account is reached and recovered by |
| `PUT /auth/me/username` | the name the web login takes next to the password (3-32 characters: a-z, 0-9, `.`, `_`; starts with a letter) |
| `POST /auth/me/password/reset-code` | for a forgotten current password: sends a one-time code (valid 10-20 minutes, three requests per 10 minutes) to the messenger most recently used; send it back as `reset_code` in place of `current_password` |
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
| `DELETE /auth/sessions/{id}` | signs one device out and leaves the others |
| `POST /auth/guest` | a throwaway account for looking around; signing out (`/auth/logout`) deletes it and everything in it |

Every new account starts with one personal book, «حساب‌داری شخصی». `/auth/login` takes the
email, the phone **or the username** as its `identifier`.

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
| `GET /books/{id}/transactions` | `?since=&until=&page=&per_page=`, newest first |
| `POST /books/{id}/transactions` | see below |
| `GET`/`DELETE /books/{id}/transactions/{tx}` | one transaction |
| `GET /transactions` | the same list across every book the account can see (`?book_id=` repeated to narrow it); each item names its book, and `totals` is one line per base currency |
| `GET /books/{id}/currencies` · `PUT /{code}` | which currencies this book may hold |
| `GET /books/{id}/wallet` | what it holds, per currency |
| `GET`/`POST /books/{id}/conversions` | move value between two of them |

```bash
curl -X POST /api/v1/books/$BOOK/transactions \
  -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"flow":"income","category":"فروش","amount":"250000","occurred_on":"2026-08-25"}'
```

A transaction carries `has_receipt`, `receipt_kind` and `receipt_file_name`.
The file id itself is not returned: it is opaque and scoped to the messenger
holding the file, so it would mean nothing here and handing it out only widens
what a leak exposes. Attaching a receipt from the bot stores the messenger's file id. From the web
there are files of our own, under
`/books/{id}/transactions/{tx}/attachments`: `GET` lists them, `POST` (multipart
field `file`) adds one, `GET /{attachment}` downloads it and `DELETE
/{attachment}` removes it. A file is a JPEG, PNG, WebP, GIF or PDF of at most
1.5 MB (the reverse proxy refuses bigger bodies anyway), at most five per
transaction; the type is read from the bytes, so a renamed file is refused.
`attachment_count` on the transaction says how many there are.

A receipt the bot stored is not one of these files: it is the messenger's, and
`GET /books/{id}/transactions/{tx}/receipt` fetches it from Telegram for the
caller (up to 8 MB, type read from the bytes, nothing kept). Any failure — a
deleted file, a receipt held by a different messenger — is a 404.

`scope` is optional and defaults from the book type. `currency` defaults to the
book's own, and a different one must be a currency the book has enabled and
must carry `conversion_rate` — that rate is frozen on the transaction and never
re-applied. An expense in a currency the book does not hold enough of is
refused; the base currency is exempt.

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
| `GET /books/{id}/reports/search` | `?q=&page=&per_page=` → matching transactions (category or description, two characters at least) and the total over every match |
| `GET /books/{id}/reports/day` | `?date=2026-03-19` → the daily list's split: business, personal, installments, savings |

### Analytics (the web panel's charts)

All under `/books/{id}/analytics/`, read-only, gated by the same `view_reports` permission. A
`period` is `1405-08`, `1405` or `week`; left out it means the current month. Money and percentages
are strings; a figure that does not exist (a percent of zero, a day that has not happened) is `null`,
never `0`. A currency conversion is not a transaction and is in none of them.

| | |
|---|---|
| `GET …/cashflow` | `?months=12` (≤ 24) → income, expense, net, savings rate and a running net per Jalali month |
| `GET …/weekday` | `?period=` → income and expense per weekday, Saturday first |
| `GET …/scope-split` | `?period=` → totals for work, personal and team (always all three) |
| `GET …/compare` | `?period=` → this period against the one before, absolute and percent, plus the biggest categories |
| `GET …/top-categories` | `?period=&flow=expense&limit=8` → each category with its share and its change since the last period |
| `GET …/category-monthly` | `?months=6&flow=expense&top=6` → each month split by category: the biggest `top` over the window, the rest folded into «سایر» (`is_other`); every month lists the same segments in the same order |
| `GET …/cumulative` | `?period=` → running income, expense and net by day, beside the previous period's net on the same day number |
| `GET …/overview-kpis` | `?period=` → balance, savings rate, average daily expense, biggest expense, runway in days |
| `GET …/budget-vs-actual` | `?period=1405-08` → each budget's use, and how much of the month has passed |

## Budgets, debts, loans

| | |
|---|---|
| `GET`/`PUT /books/{id}/budgets` | a ceiling per category; `PUT` because a category has one |
| `DELETE /books/{id}/budgets/{budget}` | |
| `GET`/`POST /books/{id}/debts` | `?include_settled=true` to see closed ones |
| `POST /books/{id}/debts/{debt}/settle` | pays it: with no `amount` the whole of what is left (and it closes), with a smaller `amount` a part payment (it stays open with less left; every debt shows `paid` and `remaining`); `{"record_transaction": true}` also records the money paid (income if owed to you, expense if you owed). Off by default: if the original sale or purchase is already recorded, recording the payment too counts it twice. A second settle is 422. |
| `GET`/`POST /books/{id}/loans` | instalment amount and count, not a total |
| `POST /books/{id}/loans/{loan}/pay` | records one instalment and its expense |

A loan is described by what one instalment costs and how many there are,
because that is how a loan is described to a person: "twelve of 4,000,000".

## Recurring rules

| | |
|---|---|
| `GET`/`POST /books/{id}/recurring` | rules, soonest first; `POST` takes `flow`, `category`, `amount`, `period` (`daily`, `weekly`, `monthly`), `starts_on`, `mode` and `first_booked` |
| `PATCH /books/{id}/recurring/{rule}` | change `mode`, `amount` or `description` from now on |
| `GET /books/{id}/recurring/pending`, `GET /recurring/pending` | due dates of rules that ask first, waiting for an answer (one book, or every book the caller can reach) |
| `POST /books/{id}/recurring/occurrences/{id}/confirm` | record that date as a transaction on its own day; an optional `amount` changes only this one |
| `POST /books/{id}/recurring/occurrences/{id}/skip` | leave that date unrecorded |

A rule's `mode` is `ask` (the default for rules made through the API) or `auto`. An `ask` rule
records nothing when a date comes due: the date waits in the pending list until someone with
permission to record confirms or skips it. An `auto` rule records on its own, as every rule did
before this existed. `first_booked: true` says the first date was just recorded by hand, so the
schedule starts from the one after it.
| `POST /books/{id}/recurring/{rule}/toggle` | pause or resume |
| `DELETE /books/{id}/recurring/{rule}` | what the rule already booked stays |

Rules are booked by the reminder loop, not by these routes.

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
| `POST /books/{id}/payslips/{slip}/payments` | staged; instalments are the norm; any currency the book holds |
| `DELETE /books/{id}/payslips/{slip}/payments/{pay}` | take a payment back while the period is open |
| `GET`/`POST`/`DELETE /books/{id}/funds` | treasury funds |
| `GET`/`POST`/`DELETE /books/{id}/funds/{f}/rules` | what feeds them |
| `POST /books/{id}/funds/{f}/toggle` | switch a fund off or back on; an off fund takes nothing from periods calculated afterwards, its rules untouched |
| `POST /books/{id}/funds/{f}/rules/{r}/toggle` | switch a rule off or back on, dates untouched; reversible, unlike `…/close` |
| `POST /books/{id}/funds/{f}/rules/{r}/close` | end a rule on a date: periods up to it still use it, later ones do not |

`calculate` returns **422**, not an empty list, when no member has a share. A
run that produces nothing because the question was never answered is not an
empty result.

A payment defaults to the payslip's own currency. Another must be one the book
has enabled and holds enough of, and must carry `conversion_rate` into the
payslip's currency; the payslip counts it at that rate, and each payment in the
response carries its rate so the list reconciles with `paid`. A rate sent with
the payslip's own currency is ignored, as it is on a transaction. `reference`
is at most 80 characters.

```bash
curl -X POST /api/v1/books/$BOOK/payslips/$SLIP/payments \
  -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"amount":"50","currency":"USDT","conversion_rate":"229867"}'
```

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
`amount`, `description` and `book_id`: a different `book_id` moves the entry to that book
(its files and its journal entry go with it) when the account may record there, the
books share a base currency, the currency is enabled in the target and neither
period is closed; otherwise it is refused and nothing changes. Money is a string. Amount means the original
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

## Market prices

| Endpoint | |
|---|---|
| `GET /market/rates` | live prices, each with `value` (a string), `source`, `fetched_at`, `age_seconds` and `stale` |

`?pairs=USDT/IRT,TON/USDT` picks pairs (at most 20); without it you get the
handful a shop owner watches. A pair the market does not publish is **left out**,
never guessed or inverted. The provider is SwapWallet's public price list,
which needs no key; the API keeps its answer for about a minute, so polling
once a minute costs the provider one request however many people are watching.

If the provider is unreachable the last good prices come back with
`stale: true` and their real `age_seconds`. With nothing remembered at all the
answer is **503** and a Persian sentence.
