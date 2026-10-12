# Platform & API gap analysis (multi-client foundations)

Scope: self-hosted, multi-client (bots, future Mini App/Web, mobile, accountant tools, integrations). "Hosted multi-tenant" stays out of scope ([roadmap.md](../roadmap.md) "Not planned"). Research only: nothing here is implemented.
Evidence: code read on `ux-platform-redesign`, plus a black-box probe against `create_app()` on in-memory SQLite (observed responses marked **[probe]**). Paths are relative to `src/kasbbook/`. Verdict: the service seam is sound (one `books.require` gate, `MoneyModel` everywhere), but the **credential, retry-safety and contract layers were built for one client** (the owner's own scripts).

## 1. Endpoint inventory (89 operations, 57 mutating, from `app.openapi()`)

| Router (file) | Ops | Auth | Calls |
|---|---|---|---|
| `/auth` (`routers/auth.py`): register, login, refresh, logout, logout-everywhere, `me` GET/PATCH, `me/contact`, `me/password`, `me/deletion-preview`, `DELETE me`, `sessions`, `api-keys` POST/GET/DELETE | 15 | none for register/login/refresh/logout; else Bearer or `X-API-Key` | `IdentityService`, `AuthService` |
| `/identities` (`identities.py`): list, link, claim, unlink, account-login request/complete | 6 | CurrentUser | `IdentityService`, `AccountLoginService` |
| `/invitations` (`invitations.py`): list, respond | 2 | CurrentUser | `InvitationService` |
| `/books` (`books.py`): list/create/get/cost-policy, currencies GET/PUT, wallet, conversions GET/POST, members GET/POST/DELETE, categories x4, invite, transactions list/POST/GET/PATCH/DELETE | 22 | CurrentUser + `books.require` | `BookService`, `ExchangeService`, `CategoryService`, `LedgerService` |
| `/books/{id}/reports` (`reports.py`): summary, day, by-category, export.csv | 4 | CurrentUser | `ReportService` |
| `/books/{id}` planning (`planning.py`): budgets x3, debts x4 (+settle), loans x4 (+pay) | 11 | CurrentUser | `BudgetService`, `DebtService`, `LoanService` |
| `/books/{id}` payroll (`payroll.py`): periods x6, shares x3, performance x2, adjustments x3, calculate, payslips x2, payments x2, funds x3, rules x4 | 26 | CurrentUser | `PayrollService`, `TreasuryService` |
| `/healthz`, `/readyz` (`health.py`) | 2 | none | session ping |
| `POST /webhooks/{provider}/{secret}` (`webhooks.py:33`) | 1 | secret in path, `hmac.compare_digest` (:54) | `Conversation.handle` (bot) |

| Question | Answer (evidence) |
|---|---|
| Version prefix? | Yes: `api = "/api/v1"` (`api/app.py:152`); health outside it. Unversioned paths 404 **[probe: `GET /books`]**, so **no back-compat alias is needed**. Missing is a *policy*: no `Deprecation`/`Sunset` header, no contract test; version is a string constant (`routers/health.py:19`, `1.0.0-beta.1`). |
| Error envelope? | Two handlers only: `KasbBookError -> {"detail": str}`, `Exception -> 500 {"detail": "something went wrong on our side"}` (`api/errors.py:21-36`). No machine `code`. FastAPI's own errors leak through: validation = `{"detail":[{type,loc,msg,input}]}` (a list, and it **echoes `input`**), unknown route / 405 = `{"detail":"Not Found"}` **[probe]**. `detail` is a string in one case and a list in another. |
| Request id? | None: no `request_id`/`correlation` anywhere in `src/` (0 hits); log format has none (`api/app.py:86-89`). |
| Pagination? | 2 of ~32 GETs (`/transactions` page/per_page, `/conversions` limit) **[openapi]**. `/transactions` fetches *every* row then slices in Python and returns `total=len(rows)` (`books.py:298-305`). No cursor, no sort param. |
| Filters? | `since`/`until` only. No category/flow/currency/text filter; `ReportService.search` (`modules/reports/service.py:257`) is bot-only. |
| OpenAPI auth metadata? | `components.securitySchemes` is **absent [probe]**: `/docs` has no Authorize button; generated SDKs get no auth. |

## 2. Bot <-> API parity (bot areas routed in `bot/conversation.py:187-264`)

| Bot prefix / use case | API equivalent | Gap / different semantics |
|---|---|---|
| `tx`/`qk` add transaction (`_save_tx`, :2211) | `POST /books/{id}/transactions` | **Different:** bot auto-quotes a live FX rate (`exchange.quote`, :360; `_RATES`, `webhooks.py:25`) and fills `conversion_rate`; API makes the caller send it and has **no rates endpoint**. `SCOPE_FOR_BOOK` is duplicated (`conversation.py:55`, `books.py:50`) instead of living in `LedgerService`. |
| `qk` quick entry (free text) `bot/quick.py` | none | Parsing is bot-only. P2: API clients send structured data. |
| `td` receipt attach/view/delete (:617-631) | read-only flags (`books.py:382`) | **No upload/download.** `receipt_file_id`+`receipt_provider` (`ledger/models.py:149-150`) is a messenger file handle, useless to any other client. |
| `sr` search (:676) | none | `ReportService.search` has no route. |
| `rr` recurring rules (:697) | **none** | `RecurringService` has no router; no create/list/toggle. |
| `rm` reminders: digest on/hour, `reminder_days` (:756) | readable only (`UserResponse`, `schemas.py:54-63`) | `ProfileRequest` (:66) cannot change them. |
| `dl`, `rep`/`rp`/`rb`/`rc` daily list and reports | `/reports/*` | Equivalent (daily list = list with `since=until`); `/day` gives totals only. |
| `bg` `dt` `ln` budgets/debts/loans | `planning.py` | Equivalent. `settle`/`pay` are non-idempotent POSTs (section 3). |
| `cu` currencies/conversions (:1133) | `/currencies`, `/wallet`, `/conversions` | Equivalent minus live quote. |
| `tf` `sh` `pf` `pr` treasury/shares/performance/payroll (:1246-1500) | `payroll.py` | Equivalent **except** pay-in-foreign-currency (`ROUND_CEILING`, "whole outstanding") lives in `Conversation._pay_in` (:1643-1676); API takes a raw `amount`, so the same payslip can end with different residue. Both clients also `session.get(Payslip)` past the service (`payroll.py:406`, `conversation.py:1645`). |
| `acc` API-key panel (:1013-1036) | `/auth/api-keys` | **Different:** bot enforces one key per person (revokes old, :1025); API mints unlimited keys. docs/api.md ("Issuing a new one revokes the old") describes only the bot. |
| `cg`, `iv`, `acc` categories, invitations, identities, sessions | `books.py`, `invitations.py`, `identities.py`, `auth.py` | Equivalent. |
| `book` list/new/open | list/create/get | No rename/archive/delete book. |
| Roles, ownership | none | `BookService.change_role` and `transfer_ownership` have **no caller in bot or API** (tests only); `delete_book` only via account deletion (`identity/service.py:356`). Neither client can change a role. |

## 3. Current state of the foundations

| Area | State (evidence) |
|---|---|
| API key model | `api_keys` (`identity/models.py:258-273`): `token_digest` (SHA-256, unique), `prefix` (8), `name`, `expires_at`, `revoked_at`, `last_used_at`, `user_id`. **No scopes, no book restriction, no creation channel, no last IP, no rotation.** Expiry optional (`auth.py:293`; request 1-3650 days, `schemas.py:107`). `last_used_at` is written on **every** authenticated request incl. GETs (`auth.py:313`). Revoke is owner-only and 404 for strangers (good, `auth.py:325-334`). |
| Key = full user | `current_user` returns a plain `User` for both credentials (`deps.py:68-87`); credential type is invisible downstream. **[probe] a key can mint more keys (201), read deletion-preview, reach `PUT /me/password`, `POST /logout-everywhere` and `DELETE /me`** (a password-less, bot-created account is "proven by the bearer token alone", `auth.py:195-212`). |
| Bearer tokens | JWT 30 min + `token_generation` counter; refresh rotation with family theft detection (good, `docs/security.md`). `/refresh` is not rate-limited (`auth.py:110`). |
| Rate limiting | Only `/auth/login` and `/auth/register` use the limiter (`auth.py:60-96`); **no limit on any data route, none per key**. 429 body = `{"detail":"too many attempts; try again in 59 seconds"}`, **no `Retry-After` header [probe]**. Memory limiter is per-worker and never evicts (`ratelimit.py:28,38`) with attacker-chosen keys (`login:id:{identifier}`, `auth.py:96`). Redis limiter does `INCR` then `EXPIRE` non-atomically (`ratelimit.py:50-55`): a crash between them leaves an immortal counter (permanent lockout). `X-Forwarded-For` uses the **left-most** hop (`deps.py:105`), which a client controls when the proxy appends. |
| Idempotency | **None** (0 hits for `idempot`). **[probe]** the same `POST /transactions` twice with the same `Idempotency-Key` -> two 201s, two distinct ids. Same exposure: `conversions`, `loans/{id}/pay`, `payslips/{id}/payments`, `debts/{id}/settle`. |
| Concurrency | Pessimistic `FOR UPDATE` inside `update` (`ledger/service.py:469-471`), but no `revision`/`ETag`/`If-Match`; `TransactionResponse` omits `updated_at` (`schemas.py:313-331`). Two clients editing = silent last-writer-wins **[probe: blind PATCH accepted]**. Deletes are hard (`ledger/service.py:549`), so a sync client cannot learn of them. |
| Timestamps | DB columns all `DateTime(timezone=True)` (`shared/database.py:48-53`); writes use tz-aware `utcnow()` (`shared/security.py:63`). Good on PostgreSQL; on SQLite the API returns naive `2026-10-11T13:46:06` **[probe]** (tests only). `date.today()` (server-local) is used in 9 service sites (loans:158, payroll:557/598, treasury:142, budgets:125, recurring:131, reminders:97/121). |
| Money as string | **Pass.** AST check: every schema with a `Decimal` field inherits `MoneyModel` (`schemas.py:22-28`), 0 exceptions. Weak: requests accept JSON floats (12500000.15 accepted **[probe]**) and have **no digit bound**: a 30-digit amount returns **500 [probe]** (`Numeric(28,4)`). |
| Webhooks | **Inbound messenger updates only** (`webhooks.py`). No outbound events, subscriptions, signing or outbox (0 hits for `outbox`/`subscription`/`webhook_url`). |
| Audit/event trail | `audit_events` (`identity/models.py:194-205`): `user_id, action, subject(120), detail`; **no book_id, payload or source channel**. ~27 distinct actions; `transaction.created/deleted` and payment-made are not recorded (`transaction.updated` is, `ledger/service.py:427`). |
| Receipts/media | Messenger file id + provider only; no own storage, no upload route (docs/api.md "no upload endpoint yet"). |
| Notifications | Hard-wired to a messenger adapter: reminders call `adapter.send_plain` (`apps/bot/reminders.py:108-111`) for `Identity` rows of one provider (`reminders/service.py:159-168`); one process per provider; "already sent" lives in the `StateStore`, 48 h TTL (`reminders.py:63-69`), not the DB. Login proof only via messenger (`identities.py:117-122`). A web/mobile-only account gets nothing. Invitations are durable (`bot/delivery.py:23-35`), the one pattern worth generalizing. |

## 4. Gap register

Severity = impact on the multi-client goal. P0 = before any second client or integration; P1 = before web/mobile ship; P2 = hygiene.

| # | Gap | Sev | Pri |
|---|---|---|---|
| G1 | API keys are full-account, all-books, unscoped; can mint keys, set password, delete account | Critical | **P0** |
| G2 | No idempotency on financial POSTs (duplicate money on any retry) | Critical | **P0** |
| G3 | No stable error envelope/`code`, no request id, 4 different 4xx body shapes | High | **P0** |
| G4 | No limits beyond login: no per-key quota, no `Retry-After`; limiter bugs (non-atomic Redis, unbounded memory, XFF); unbounded amounts -> 500 | High | **P0** |
| G5 | No domain event log (create/delete/pay unrecorded; audit has no book/payload/source); prerequisite for outbound webhooks and sync | High | **P0** (table+emit) |
| G6 | No contract freeze: no `securitySchemes`, no snapshot test, no deprecation policy | Medium | **P0** (cheap) |
| G7 | Pagination/filter/sort on 2 of ~32 GETs; list loads all rows; no `updated_since`; hard deletes | High (mobile) | P1 |
| G8 | No optimistic concurrency (`revision`/`If-Match`) | Medium | P1 |
| G9 | Outbound signed webhooks (worker, HMAC, retries, SSRF guard) | High | P1 (needs G5) |
| G10 | Receipts locked to a messenger file id; no upload/download | Medium | P1 |
| G11 | Notifications hard-wired to messenger adapters; dedupe in Redis/state | Medium | P1 |
| G12 | Parity: recurring, search, digest settings, rate quote, role/ownership/book delete (no client at all) — **fixed** except book delete/rename and a bot members screen | Medium | P1 |
| G13 | Rules living in clients: `SCOPE_FOR_BOOK` x2, `_pay_in` rounding, one-key policy, `session.get(Payslip)` — **fixed** | Medium | P1 |
| G14 | Path/object mismatch unchecked on `adjustments/{id}/approve` (`payroll.py:307-322`); service authorizes the adjustment's own book (`payroll/service.py:728`) so no leak, but `_names(book_id)` runs with no `require` — **fixed**: every period route checks the book, approve checks the period, `_names` is gated | Low | P1 |
| G15 | `date.today()` server-local in 9 services; naive datetimes on SQLite | Low | P2 |
| G16 | `last_used_at` write per request; no key rotation/overlap; no last-used IP | Low | P2 |
| G17 | CORS `allow_methods/headers=["*"]` + credentials (`app.py:142-148`); `/docs`, `/openapi.json` public (`:134-135`) | Low | P2 |
| G18 | docs/api.md drift (one-key claim, error shape) | Low | P2 |

## 5. Minimal P0 foundation set (priority order)

### P0-1 Principal with scoped, book-restricted API keys (G1)
- Migration (with `server_default`, per SKILL landmines): `api_keys.scopes TEXT NOT NULL DEFAULT 'read,write'`; new `api_key_books(key_id FK CASCADE, book_id FK CASCADE, PK both)`; empty = all the user's books. Existing keys keep working but lose account-level powers.
- Scopes (coarse, mapped onto `Permission`): `read`, `write`, `payroll`, `export`, `events:read`. Effective right = member permission AND key scope; services untouched (they only see `user_id`, e.g. `ledger/service.py:462`).
- Seam: `current_user` (`deps.py:68`) builds `Principal(user, credential, key_id, scopes, book_ids)`; `CurrentUser` stays `principal.user` so the 89 routes don't change. Add `Security(scope("write"))` per router plus a router dependency asserting path `book_id in principal.book_ids` (404, matching `books.require`).
- `BearerOnly` on `auth.py:127,166,195,215-232` and identities link/unlink/account-login: a key gets 403 `credential_not_allowed`.
- API: `POST /auth/api-keys {name, scopes[], book_ids[], expires_in_days}`; write-scoped keys default to 365-day expiry; throttle `last_used_at` to 1/min (`auth.py:313`). `rotate` (new secret, old valid 24 h) follows in P1.
- Tests: no-`write` key -> 403 on POST tx; key bound to book A -> 404 on book B (and absent from list); key cannot mint keys/delete account/set password; legacy key still reads+writes; revoked/expired -> 401; scopes in OpenAPI.

### P0-2 `Idempotency-Key` on financial POSTs (G2)
- Table `idempotency_keys(id, principal_id, key VARCHAR(64), method, path, request_hash CHAR(64), status SMALLINT NULL, response JSON NULL, created_at, expires_at)`, `UNIQUE(principal_id, key, method, path)`.
- Header `Idempotency-Key: <opaque 8-64 chars>`; optional in v1 (breaks nobody), required for `payslips/{id}/payments`.
- Seam: `api/idempotency.py` dependency on the request session. INSERT the reservation in the same DB transaction that `get_session` commits (`deps.py:45`), so the row and the money commit atomically. Duplicate: same hash replays the stored status/body with `Idempotent-Replay: true`; different hash -> 422 `idempotency_key_reuse`; unfinished -> 409 `request_in_progress`.
- Apply to: transactions POST, conversions POST, debts `settle`, loans `pay`, payslips `payments`, `calculate`, adjustments POST/approve, treasury rules POST. TTL 48 h, purged by the reminder loop.
- Tests: duplicate POST -> one `Transaction`, `trial_balance()` unchanged; `asyncio.gather` of two identical requests -> one row; same key + other body -> 422; same key, other user -> independent; payslip payment replay does not double `paid`; error responses are not cached as success.

### P0-3 Uniform error envelope + request id (G3)
- `RequestIdMiddleware`: accept `X-Request-Id` if `^[A-Za-z0-9._-]{8,64}$`, else uuid4; contextvar; echo on **every** response; add to the log format (`app.py:86-89`).
- Envelope, additive for v1 (docs/api.md promises `detail`): `{"detail": <unchanged>, "error": {"code": "book_not_found", "message": "...", "request_id": "...", "fields": [{"loc": "body.amount", "code": "greater_than"}]}}`.
- Handlers for `StarletteHTTPException` (404/405), `RequestValidationError` (stop echoing `input`), `KasbBookError` (new class attribute `code`, default snake_case class name), `Exception` (500: request id only). 401 adds `WWW-Authenticate: Bearer`; 429 adds `Retry-After`.
- Tests: golden shape for 401, 403, 404 route, 405, 409, 422 validation, 422 domain, 429, 500; request id round-trips and appears in a log record; 500 never leaks the message; non-member 404 body identical to unknown-id 404.

### P0-4 Limits and bounds (G4)
- Per-principal fixed windows via a router dependency, key `rl:{key_id|user_id}:{class}`; classes `read` 600/min, `write` 120/min, `export` 6/min (Settings). Headers `RateLimit-Limit/Remaining/Reset` and `Retry-After`; 429 uses the P0-3 envelope.
- Fix `RedisRateLimiter` atomically (Lua, or `SET k 1 EX w NX` then `INCR`); `MemoryRateLimiter` purges expired entries on write; fingerprint takes the right-most untrusted hop (`deps.py:105`).
- Request money: `Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=4)]` on every request Decimal in `schemas.py` -> 422, not 500; body-size cap at the proxy.
- Tests: 121st write in a minute -> 429 with `Retry-After`; two principals don't share a bucket; Redis counter always has a TTL (fake client that dies after INCR); memory limiter size bounded; 30-digit amount -> 422.

### P0-5 Domain event log as the single outbox (G5)
- Table `domain_events(seq BIGINT autoincrement UNIQUE, id UUID PK, book_id FK NULL, type VARCHAR(48), version SMALLINT DEFAULT 1, actor_user_id, source VARCHAR(40) -- 'bot:telegram' | 'api:key:kb_abc12345' | 'system', subject_id UUID, data JSON, created_at tz)`; index `(book_id, seq)`. Money in `data` as strings.
- Written **inside the service**, same transaction (like `_mark_edited`, `ledger/service.py:425`): `LedgerService.record/update/delete`, `ExchangeService.convert`, `PayrollService.pay/void_payment/calculate`, debts/loans. Bot and API therefore emit identically; a rollback emits nothing. `source` comes from a small `ActorContext` fed by `Principal` / `Conversation` (default `system`).
- Read side now: `GET /api/v1/books/{id}/events?after=<seq>&limit=100` (scope `events:read`): the sync cursor for mobile/accountant tools (deletes become events) and the queue the later webhook worker drains.
- Deferred (P1, same table): `webhook_endpoints(url https-only, secret stored encrypted, events[], book_id?)`, `webhook_deliveries(event_id, endpoint_id, attempt, next_at)`; headers `X-KasbBook-Event-Id`, `X-KasbBook-Signature: t=<unix>,v1=hex(HMAC_SHA256(secret, t + "." + body))`; backoff retries; SSRF guard (resolve, block private/link-local, no redirects). The signing secret must be recoverable, so the SHA-256-only storage rule (`docs/security.md`) does not apply to it.
- Tests: each mutating service call emits exactly one event; a failed request emits none; `seq` monotonic under `gather`; non-member and out-of-scope key get 404; same event from bot path and API path; `data` contains no float.

### P0-6 Contract freeze (G6)
- Declare `HTTPBearer` + `APIKeyHeader` via `Security()` so `securitySchemes` and per-route scopes appear in OpenAPI.
- `tests/test_api_contract.py`: compare `app.openapi()` paths, params and response schemas with a committed snapshot; a diff fails unless it is additive (new optional fields) or `version` is bumped. Policy: v1 additive-only, breaking -> `/api/v2`, `Deprecation` + `Sunset` headers for one release.
- No `/api/v1` alias: unversioned routes never shipped **[probe]**.

## 6. OWASP API Security Top 10 (2023): only where evidence exists

| Risk | Evidence | Test to add |
|---|---|---|
| API1 BOLA | Good: `books.require` raises `NotFound` (`books/service.py:297-308`); tests `test_api_payroll.py:406,418,478`, `test_api_wallet.py:120`. Gap: path `book_id` not compared with the object's book on `approve` (`payroll.py:307-322`); `pay` checks it *after* acting and relies on rollback (`payroll.py:406-411`). | Parametrized "child id under another book's path -> 404, no state change" for every `/books/{id}/x/{child}` route. |
| API2 Broken authentication | Keys: no default expiry, no rotation (`auth.py:293`); `/refresh` unthrottled (`auth.py:110`); XFF left-most (`deps.py:105`). | Key expiry/rotation tests; XFF spoof test with `KASBBOOK_TRUSTED_PROXY`. |
| API3 Property-level | No finding: request models are explicit; `UserResponse` exposes only the caller's own fields. Validation errors echo `input` **[probe]**. | Validation error body must not contain request values. |
| API4 Resource consumption | Transactions list loads all rows (`books.py:298-305`); `export.csv` unbounded (`reports.py:113`); 30-digit amount -> 500 **[probe]**; memory limiter growth (`ratelimit.py:28,38`); non-atomic Redis (`:50-55`). | P0-4 tests; list with 10k rows stays under a row/query cap. |
| API5 Function-level authz | A key reaches account-destructive functions: mint key `auth.py:215`, password `:166`, logout-all `:127`, `DELETE /me` `:195` **[probe]**. | P0-1 `BearerOnly` tests. |
| API6 Sensitive business flows | Replayable money flows: `payroll.py:390` payments, `planning.py:145` loan pay, `books.py:173` conversions, `:313` transactions **[probe: duplicate 201s]**. | P0-2 tests. |
| API7 SSRF | No outbound user-supplied URL today; becomes live with outbound webhooks (G9). | SSRF guard tests ship with the webhook worker. |
| API8 Misconfiguration | CORS wildcard methods/headers with credentials (`app.py:142-148`); public `/docs` (`:134`); Bale/Rubika inbound webhooks unsigned (documented, `docs/security.md`). | CORS config test; keep path secret out of logs. |
| API9 Improper inventory | No `securitySchemes`, no deprecation policy, constant version (`health.py:19`), docs drift. | P0-6 snapshot test. |
| API10 Unsafe consumption | Not a finding: `rates/swapwallet.py` has 5 s timeout and 60 s cache. A quoted rate becomes a stored `conversion_rate` with no sanity band (unverified risk). | Reject quotes far outside the last stored rate (threshold to decide). |

## 7. Order of work and open decisions

1. P0-3 and P0-6 (additive, small, make every later change testable). 2. P0-2 (money safety). 3. P0-1 (introduces `Principal`; P0-4 buckets use it). 4. P0-5 (can start with `source='system'` and gain `Principal` after P0-1).
- Decide: coarse scopes (above) or one per `Permission`? Recommendation: coarse, mapped internally so the vocabulary grows without a migration.
- Decide: `Idempotency-Key` required from day one on `payslips/payments` only (the path that moves money out), optional elsewhere. Recommended.
- Decide: webhook signing-secret storage (encrypt under a key derived from `KASBBOOK_SECRET_KEY` vs a separate key); add it to `docs/security.md`.
- Out of scope (design only, per owner): Mini App/Web, mobile, OAuth, SDK. OAuth later maps onto the same `Principal` and scopes, which is why P0-1 comes first among the credential items.
