# The API

Interactive documentation at `/docs`. This page covers the conventions the
OpenAPI schema cannot express.

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

```json
{ "detail": "این دفتر پیدا نشد" }
```

Domain errors carry their own status: 404 not found, 403 denied, 422 invalid,
409 conflict, 401 unauthenticated, 429 rate limited. Validation failures come
from Pydantic in its own shape, with the offending field.

Unhandled exceptions are always `{"detail": "something went wrong on our
side"}` with a 500. The real error is in the log, never in the response.

### Not-found means not-yours

Asking for a book you are not a member of returns **404**, not 403. Revoking
someone else's API key returns 404. This is deliberate: a 403 would confirm the
id exists.

## Authenticating

Either a bearer token or an API key. Both resolve to the same account.

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
| `GET /books/{id}/transactions` | `?since=&until=&page=&per_page=`, newest first |
| `POST /books/{id}/transactions` | see below |
| `GET`/`DELETE /books/{id}/transactions/{tx}` | one transaction |

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
book's base currency; a different one captures a conversion rate at that moment
and never re-applies it.

Adding a member requires that person to already have an account; they are found
by email or phone.

## Reports

| | |
|---|---|
| `GET /books/{id}/reports/summary` | `?period=1403-05` → income, expense, net, count |
| `GET /books/{id}/reports/by-category` | `?flow=expense&period=` → totals and shares |
| `GET /books/{id}/reports/export.csv` | the period as a file, Jalali dates included |

## Budgets, debts, loans

| | |
|---|---|
| `GET`/`PUT /books/{id}/budgets` | a ceiling per category; `PUT` because a category has one |
| `DELETE /books/{id}/budgets/{budget}` | |
| `GET`/`POST /books/{id}/debts` | `?include_settled=true` to see closed ones |
| `POST /books/{id}/debts/{debt}/settle` | writes the matching transaction |
| `GET`/`POST /books/{id}/loans` | instalment amount and count, not a total |
| `POST /books/{id}/loans/{loan}/pay` | records one instalment and its expense |

A loan is described by what one instalment costs and how many there are,
because that is how a loan is described to a person: "twelve of 4,000,000".

## Payroll and treasury

Team and organization books only. Every route calls the same service the bot
calls, so a share set here is what Telegram reports and a payslip calculated in
Telegram is what this returns.

| | |
|---|---|
| `GET`/`POST /books/{id}/periods` | list, or open one |
| `GET /books/{id}/periods/{p}/distribution` | income − costs − treasury = distributable |
| `POST /books/{id}/periods/{p}/status/{status}` | only the documented transitions |
| `GET`/`PUT /books/{id}/shares` | who takes what; `PUT` end-dates the previous rule |
| `DELETE /books/{id}/shares/{user}` | stop paying this member |
| `GET`/`PUT /books/{id}/periods/{p}/performance` | hours, days, points — for measured bases |
| `GET`/`POST /books/{id}/periods/{p}/adjustments` | bonuses and deductions, signed |
| `POST …/adjustments/{a}/approve` | recording and approving are separate |
| `POST /books/{id}/periods/{p}/calculate` | payslips, every input frozen onto them |
| `GET /books/{id}/periods/{p}/payslips` | everyone's, or only yours, by permission |
| `POST /books/{id}/payslips/{slip}/payments` | staged; instalments are the norm |
| `GET`/`POST`/`DELETE /books/{id}/funds` | treasury funds |
| `GET`/`POST`/`DELETE /books/{id}/funds/{f}/rules` | what feeds them |

`calculate` returns **422**, not an empty list, when no member has a share. A
run that produces nothing because the question was never answered is not an
empty result.

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
