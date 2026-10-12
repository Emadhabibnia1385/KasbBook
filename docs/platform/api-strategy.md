# API strategy

How the public API evolves without breaking the clients built on it. Status:
**policy, partly built**. Evidence is in
[platform-gap-analysis.md](./platform-gap-analysis.md).

## Versioning

- **One major version in the path: `/api/v1`.** Unversioned paths never shipped,
  so no alias is needed.
- **Within v1, changes are additive only:**
  - new routes;
  - new optional request fields;
  - new response fields;
  - new enum values only where the docs say a client must tolerate unknown
    ones.
- **A breaking change ships as `/api/v2`.** v1 then answers with
  `Deprecation: true` and a `Sunset` date, for at least one release.
- **Enforced by a test, not by care.** `tests/test_api_contract.py` will compare
  `app.openapi()` with a committed snapshot and fail on anything non-additive.
  This is foundation item P0-6, not yet built.

## The contract every response keeps

| Concern | Rule | Status |
|---|---|---|
| Money | a JSON string, with an explicit currency code. Never a float: every schema carrying a `Decimal` inherits `MoneyModel`. | built, checked |
| Amount bounds | an amount the `Numeric(28,4)` column cannot hold is a 422 with a Persian message, not a 500 | **built** (`9f6c5b0`) |
| Dates | ISO dates and tz-aware timestamps, Gregorian on the wire. Jalali is presentation, done by the client or the bot. | built |
| Errors | `detail` stays, as documented. An `error` object is added beside it: `code`, `message`, `request_id`, `fields`. Validation errors stop echoing input. | **built** |
| Request id | `X-Request-Id` accepted or generated, echoed on every response, written to the error log line | **built** |
| Throttling | 429 with `Retry-After` | **built for auth routes** (`9f6c5b0`); per-principal quotas on data routes are P0-4 |
| Pagination | cursor (`after`, `limit`) on every list that can grow; `page`/`per_page` kept where it already ships | P1 |

## Retries and concurrency

Mobile networks, webhook consumers and queue workers retry. A retried financial
request must never move money twice.

- **`Idempotency-Key`** — **built** (IETF httpapi draft semantics; see `docs/api.md`):
  - The same key with the same body replays the stored response, with
    `Idempotent-Replay: true`.
  - The same key with a different body is 422.
  - A key whose first request is still in flight is 409.
  - It is stored in the same transaction as the effect, so a crash cannot
    leave one without the other.
  - It applies to transactions, conversions, debt settle, loan pay, payslip
    payments, calculate, and adjustments.
  - It is optional everywhere except payslip payments, where it is required
    (owner decision): that request is the one that moves money out.
  - Keys are per account and route, kept 48 hours.
- **Domain-specific guards already built:**
  - A loan payment carries `expected_paid_count`, so a repeat finds the count
    moved.
  - Settling a debt twice is refused.
  - A period cannot be closed twice.
  - The bot's quick entry is claimed atomically.

  These stay now that `Idempotency-Key` exists: they make a duplicate harmless
  even when a client forgets the header.
- **Optimistic concurrency.** A `revision` on transactions, sent back as
  `If-Match`; a stale write is 412. It is P1 and needed before the web panel,
  where two people edit the same book.

## Parity with the bot

The bot and the API call the same services. Parity tests assert they reach the
same result. Some semantics still differ, or exist on one side only (gap
analysis §2):

| Use case | Status |
|---|---|
| Settling a debt asks whether to record the money | **closed**: both ask; the API takes `record_transaction` |
| Closing a period in one step | **closed**: bot «بستن دوره», API `POST …/periods/{p}/close` |
| Recurring rules, search, digest settings, live rate quote | **closed**: `…/recurring`, `…/search`, `PATCH /auth/me`, `…/rates/{code}` |
| Paying a payslip in a foreign currency, "the whole outstanding" rounding | **closed**: `PayrollService.pay_towards`; API `settles` / `rest` |
| One key per person | **closed** as a bot convenience: `AuthService.replace_api_keys`; the API issues alongside, documented |
| A member's role, handing a book over | **closed** on the API; the bot has no members screen yet (UX) |
| The default scope of an entry | **closed**: `SCOPE_FOR_BOOK` once, in the ledger; `record(scope=None)` |

`tests/test_bot_api_parity.py` holds the tests for each.

## Documentation

- `docs/api.md` and `docs/api.fa.md` are kept true in the same commit as the
  change: the debt-settle, close-period, key-restriction and hardening commits
  all updated them.
- The OpenAPI document gets `securitySchemes` (Bearer and `X-API-Key`), so
  `/docs` has an Authorize button and generated SDKs know how to authenticate
  (P0-6).
- Examples are generated from the snapshot, never hand-written (phase 2):
  - Python and TypeScript examples;
  - an importable collection;
  - curl examples.
