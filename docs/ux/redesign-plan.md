# Redesign plan (merged audit)

This plan merges three audits:

- [current-flow-audit.md](./current-flow-audit.md): UX and conversation, with
  transcripts in [`transcripts/before/`](./transcripts/before/).
- [accounting-domain-audit.md](./accounting-domain-audit.md) and
  [bug-ledger.md](./bug-ledger.md): accounting and bugs.
- [platform-gap-analysis.md](../platform/platform-gap-analysis.md): platform
  and API.

Policy questions are in [accounting-decisions.md](./accounting-decisions.md).

The orchestrator verified the highest-impact claims against the source before
ranking them:

| ID | Verified by |
|---|---|
| ACC-001 | no caller of `run_due` in `src/` or `apps/` |
| ACC-003 | `debts/service.py:74-82` does not book a transaction |
| ACC-004 | `payroll/service.py:427-431` takes the category branch before the basis check |
| B1 | the stale-button reproduction, rerun |
| SEC-1 | `api/routers/auth.py:215`, where `CurrentUser` accepts an API key |

## Baseline

The suite showed 698 passed, 18 failed, 1 error and 9 skipped, and pyflakes
was clean. **None of the failures is a product regression.**

| Failures | Root cause |
|---|---|
| 10 in `test_bot_payroll_treasury.py` | The fixtures are pinned to Shahrivar while the bot reads `date.today()`, which is now Mehr (ENV-001). |
| 8 in the shell tests | A repository path containing a space is passed to bash unquoted (ENV-002). |
| 1 error | Windows temp-directory permission (ENV-003). |

## P0: proposed for implementation now

Ordered by user harm. Each is a small slice: a red test, then the minimal
change, then the scoped tests and the full suite.

| # | ID | Problem | Fix (sketch) | Kind |
|---|---|---|---|---|
| 1 | ACC-004 | A FIXED treasury rule with a category takes `value% × category income` (5M becomes 5,000,000,000,000) | Use the category branch only for percent bases | arithmetic bug |
| 2 | ACC-005 | A deactivated fund still takes its cut | Skip rules whose fund is inactive | arithmetic bug |
| 3 | ACC-006 | Percent shares can total over 100%, so payslips overpay the distributable | Refuse at `set_share` (D-3 option A) | needs **D-3** |
| 4 | ACC-001/002 | Recurring rules never book; when they do run, one bad rule rolls back all the others | Run `run_due` from the reminder loop; isolate each rule with a savepoint; report skipped firings | needs **D-1** |
| 5 | B1 | A stale quick-entry button records a *different, newer* draft | Put a short draft nonce in the callback; a mismatch says "this message is old" and shows the current draft | UX/data bug |
| 6 | B2 | A double tap on confirm records twice (concurrent webhook mode) | Consume the draft atomically (compare-and-clear of the nonce), so a second tap finds no draft | data bug |
| 7 | SEC-1 | An API key can mint new keys, so revoking a leaked key does not lock the attacker out. It can also log out every session, and on a passwordless account close the account | Track the principal kind; key-management and account routes require a person's token | security |
| 8 | API-1 | No idempotency on financial POSTs: a retry creates duplicates | `Idempotency-Key` header on create-transaction, pay, convert, loan-pay and settle; a stored response is replayed | foundation |
| 9 | API-2 | Error bodies come in four shapes; there is no request id; a 30-digit amount returns 500 (ACC-017) | One envelope `{error:{code,message,request_id}}`, an `X-Request-ID` header, and a clean 422 for an amount out of range | foundation |
| 10 | B5 | "انصراف" on the new-book prompt does not cancel; the next line becomes a book | Treat cancel as a cancel in every text-input state | UX/data bug |
| 11 | ENV-001/002 | Baseline red on Windows and after Shahrivar | Pin the clock in the payroll bot tests; quote paths with `shlex.quote` in the shell tests (test code only) | test health |

## P0 journeys (UX), after the bugs above

| Journey | Steps now → target | Change |
|---|---|---|
| First run → first transaction | 13 → 4–5 | After the first book is created, land directly on "send your first transaction like: فروش ۵۰۰ هزار" with a two-button fallback |
| Quick entry confirm | shows amount and category → also book, date and note | Context line on the confirm screen; the parser's uncertain cases ("۲ عدد نان ۲۰۰۰۰", "۳۰ هزار و ۵۰۰") ask instead of guessing (B3) |
| Back / cancel / stale | inconsistent | Shared vocabulary: «بازگشت» goes to the real parent, «انصراف» clears the draft and says so, an expired state says «این پیام قدیمی است» and offers the current screen |
| Error copy | silent re-asks, English leaks (B4, ACC-028) | Cause + example for every text prompt; no English or internal message reaches a user |

## P1 (next wave, not started)

- ACC-007: a negative wallet after an edit or delete (D-4).
- ACC-008: the bot's close-period button does nothing.
- ACC-009: payments are accepted on a locked period.
- ACC-011: loan overpayment and a double press.
- ACC-012: server UTC used where the book's day is required.
- ACC-013/014: adjustment validation.
- ACC-018: CSV formula injection.
- ACC-019: a zero debt is accepted.
- ACC-020: `%` in search is a wildcard.
- B3: parser ambiguity, if not finished in the journeys above.
- B6–B12 from the UX audit.
- The 25 Persian copy rewrites.
- Rate-limit fixes: atomic Redis, Retry-After, LRU eviction.
- Pagination.
- Outbox / domain events; outbound webhooks need these.
- The book-restricted, scoped API key model (SEC-1 is only its first slice).

## P2 and design-only

**P2**: the remaining ACC items, the decisions in D-5 and D-6, and the
optimistic-concurrency revisions.

**Design-only, not to be built without the owner's approval:** web panel, Mini
App, Android/iOS, OAuth 2.1/OIDC, SDKs and the integration ecosystem. They are
described in the platform gap analysis and the roadmap.

## Architecture

The conversation refactor is deferred until the P0 fixes land.

Splitting `conversation.py` and `screens.py` by feature is still the
direction, but it is a large mechanical diff. Doing it before the bug fixes
would make each fix harder to review. The P0 fixes touch:

- `bot/conversation.py`: quick-entry nonce, cancel;
- `bot/screens.py`: copy;
- `modules/payroll/service.py`, `modules/recurring/service.py`,
  `apps/bot/reminders.py`;
- `api/deps.py`, `api/routers/auth.py`, `api/errors.py`, and a new
  idempotency table with its migration.

## Acceptance criteria per slice

- A red test first. Then the scoped tests, the full suite, pyflakes and
  `git diff --check`.
- Every financial fix asserts exact amounts and `trial_balance()`.
- Every bot change has a transcript assertion; a stale or double tap has its
  own test.
- Every API change has a refusal test and an isolation test (another user, and
  an API key).
- One commit per slice, subject in English, on branch `ux-platform-redesign`.

## Status — P0 wave 1 (approved: financial and security items only)

Items 8 and 9 (idempotency, error envelope) were deferred by the owner.

| # | ID | Status | Commit | Regression tests |
|---|---|---|---|---|
| 1 | ACC-004 | fixed | `7af96fa` | `test_payroll.py::test_a_flat_rule_naming_a_category_takes_its_flat_amount`, `…percentage_rule_naming_a_category_still_reads_that_category` |
| 2 | ACC-005 | fixed | `7af96fa` | `test_payroll.py::test_a_deactivated_fund_takes_nothing_more` |
| 3 | ACC-006 (D-3 = refuse) | fixed | `83693bc`, `b6a5277` | `test_payroll.py::test_percentage_shares_cannot_promise_more_than_everything`, `…future_share_cannot_overlap…`, `…already_over_100_percent_refuses_to_calculate`; bot: `test_bot_payroll_treasury.py::test_a_share_that_would_pass_100_is_refused_in_the_bot_with_the_free_room` |
| 4 | ACC-001/002 (D-1 = open periods + notice) | fixed | `fb07f80` | `test_recurring_search_reminders.py::test_a_date_in_a_closed_period_is_skipped…`, `…author_left_the_book_is_paused…`; `test_reminder_loop.py::test_the_loop_books_recurring_rules_that_came_due`, `…late_catch_up_is_told_to_the_owner_once` |
| 5 | B1 | fixed | `15140ed` | `tests/test_bot_stale_and_cancel.py` |
| 6 | B2 | fixed | `15140ed` | `tests/test_bot_stale_and_cancel.py` (two `asyncio.gather` races) |
| 7 | SEC-1 | fixed | `223d9ee` | `test_api_auth.py::test_an_api_key_cannot_manage_the_account_it_belongs_to` (12 routes), `…key_still_does_the_work…` |
| 10 | B5 | fixed | `15140ed` | `tests/test_bot_stale_and_cancel.py` |
| 11 | ENV-001/002 | fixed (test code only) | `b6a5277` | the 18 baseline failures now pass |
| — | ENV-003 | environmental | — | passes with `--basetemp` outside the user's Temp |

Last full run: `pytest tests --basetemp <scratch>` → **760 passed, 0 failed, 9
skipped** (Postgres-only and packaging tests, as expected); pyflakes clean;
`git diff --check` clean.

**Not yet verified:**
- Redis `GETDEL` runs only through a unit path, against no live Redis. It
  needs Redis 6.2+; the deploy runs Redis 7.
- `FOR UPDATE SKIP LOCKED` on the recurring run is a no-op on SQLite and has
  not been exercised against PostgreSQL.
- A recurring notice reaches the owner only on a messenger whose reminder loop
  performed the run. With two messengers configured, the owner may hear about
  a run on only one of them, or on neither.

## Status — wave 2 (deployment safety, P1, Persian UX, refactor)

| Area | Item | Commit |
|---|---|---|
| Deploy safety | `KASBBOOK_RECURRING` switch, real-run preview (`apps/bot/recurring_preview.py`), per-rule notice that fits one message, MULTI/EXEC draft claim (works on Redis < 6.2), CI job racing real Redis 7 + PostgreSQL 16 | `ceb91e8` |
| Security | amounts beyond the column refused (422), CSV formula injection, LIKE wildcards, atomic Redis limiter, `Retry-After`, limiter eviction, right-most `X-Forwarded-For` | `9f6c5b0` |
| Financial | D-5, D-5b, ACC-013/014 adjustments, ACC-016 allocation snapshot, ACC-012 book day | `14c6012` |
| Financial | D-4 wallet cannot go negative through an edit or delete | `ef921b9` |
| Financial | a refused bot step keeps nothing it began (per-update savepoint) | `c2cd1a2` |
| Financial | D-2 debt settle asks; ACC-019 zero debt | `2e6eb83` |
| Financial | ACC-011 loan overpayment and double press | `bd15495` |
| Financial | ACC-008 close a period from the bot or API; shortfall shown | `66d0121` |
| Financial | conversions and voids on the book lock (ACC-021) | `5775e26` |
| UX | B3 parser, B4, B6–B12, first-run path, ~65 copy changes, `transcripts/after/` | `f016d47` |
| Refactor | feature contract + registry; payroll moved | `b1bb03e`, `8517cbd` |

**Still verified only in CI** (the services job): the Redis claim under 50
concurrent pops, four recurring loops on PostgreSQL, two concurrent conversions,
two concurrent payslip payments. The test bodies were run sequentially on
SQLite to check they are correct; the races themselves need the real services.
