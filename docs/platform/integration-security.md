# Integration security

The threat model for letting programs into the books: API keys today, signed
webhooks and OAuth later. Mapped to OWASP API Security Top 10 (2023) only where
there is evidence. Each threat names the test that guards it. Evidence and
file:line references are in [platform-gap-analysis.md](./platform-gap-analysis.md) §6.

## Assets and actors

| Asset | Why it matters |
|---|---|
| The ledger of each book | someone's money; it must be both correct and private |
| Credentials: passwords, refresh tokens, API keys, webhook secrets | each one is a door |
| The account itself: contact, linked messengers, existence | taking it is taking every book on it |

**Actors:**
- the account owner;
- a member with a role;
- a program holding a key;
- an attacker holding a *leaked* key;
- an attacker holding nothing;
- a malicious webhook receiver (later);
- a malicious document opener: whoever opens an exported CSV.

## Threats, and where they stand

| # | Threat | OWASP | Status | Guard |
|---|---|---|---|---|
| T1 | A leaked key is used to mint a successor, so revoking the leaked one achieves nothing | API5 | **fixed** (`223d9ee`) | `test_an_api_key_cannot_manage_the_account_it_belongs_to` (12 routes) |
| T2 | A key takes over the account: contact, password, messenger link, closing a passwordless account | API5, API2 | **fixed** (`223d9ee`) | same |
| T3 | A key reaches every book of its owner and every permission | API1, API5 | open: P0-1 adds scopes and book restriction | to add: a key bound to book A gets 404 on B; a key without `write` gets 403 on POST |
| T4 | A retried request moves money twice | API6 | **fixed**: `Idempotency-Key` on every money-moving POST, required on payslip payments; plus `expected_paid_count` on loans and a refused second settle | `tests/test_api_idempotency.py`; the concurrent-retry race in `tests/test_concurrency_services.py` |
| T5 | Two concurrent requests both pass a balance check | API6 | **fixed** for record, pay, convert and void (book lock); tested on PostgreSQL in CI | `tests/test_concurrency_services.py` |
| T6 | Object ids probed across books | API1 | holds: `books.require` answers 404, never 403 | the isolation tests in every API file; the new `test_another_account_cannot_settle_this_debt` |
| T7 | Unbounded input crashes or exhausts the server | API4 | partial: amount bound (`9f6c5b0`); lists are not yet paginated (P1) | `tests/test_api_hardening.py` |
| T8 | A rate limit is bypassed by forging `X-Forwarded-For` | API2, API4 | **fixed**: the right-most hop is used behind the trusted proxy | `tests/test_api_hardening.py` |
| T9 | A permanent lockout from a non-atomic limiter | API4 | **fixed**: MULTI/EXEC, and a stranded counter heals | `tests/test_api_hardening.py` |
| T10 | An exported CSV runs a formula on whoever opens it | — (injection) | **fixed** (`9f6c5b0`) | `tests/test_api_hardening.py` |
| T11 | Validation errors echo request bodies, which may contain secrets, into logs and clients | API3 | open: P0-3 | to add: the 422 body contains no input values |
| T12 | A webhook receiver URL points inside the network (SSRF) | API7 | design: resolve, block private and link-local addresses, no redirects, HTTPS only | ships with the webhook worker |
| T13 | Forged or replayed webhook deliveries | — | design: `X-KasbBook-Signature: t=<unix>,v1=HMAC_SHA256(secret, t.body)`; reject a `t` older than 5 minutes; a unique event id | ships with the webhook worker |
| T14 | A permissive CORS policy combined with credentials | API8 | open: P2; lock to known origins when the web panel ships | config test |
| T15 | An inventory that drifts from the docs | API9 | partial: docs updated with each change; contract snapshot is P0-6 | P0-6 snapshot |

## Secrets at rest

| Secret | Storage | Why |
|---|---|---|
| Passwords | argon2 | — |
| Refresh tokens and API keys | SHA-256 digests (`docs/security.md`) | never needed again in the clear |
| Webhook signing secrets | encrypted under a key derived from `KASBBOOK_SECRET_KEY`, or a separate key | the server must compute HMACs with them, so a one-way digest is not an option |

**The webhook storage choice is an owner decision.** Whichever is chosen goes
into `docs/security.md` before the worker ships.

## Negative-authorization tests to keep adding

Every new route ships with:
- a refusal for a user who is not a member (404);
- a refusal for a member without the permission (403);
- an isolation case proving another account cannot reach it.

Once scopes exist, every route also gets a key without the scope, and a key
restricted to another book. The constitution already requires the first three;
the last two arrive with P0-1.
