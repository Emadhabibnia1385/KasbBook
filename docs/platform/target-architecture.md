# Target architecture: one core, many clients

Status: **design**. Nothing here beyond what is marked *built* exists yet. The
evidence for every gap is in [platform-gap-analysis.md](./platform-gap-analysis.md).

## The shape

```text
Telegram · Bale · Rubika · future bots      Mini App · Web      Android · iOS      accountant tools · integrations
        │  (in-process)                              │  (HTTPS)                              │  (HTTPS, keys / OAuth later)
        ▼                                            ▼                                       ▼
   bot/features/*  ───────────────►   /api/v1  (versioned contract, error envelope, idempotency, scopes)
        │                                            │
        └──────────────► application services (modules/*/service.py) ◄──────────────┘
                              one rule, once; books.require is the only gate
                                            │
                      ledger · books · payroll · treasury · reports · exchange
                                            │
                             domain_events (outbox)  ──►  webhook worker, sync cursor
                                            │
                                PostgreSQL · Redis · files
```

Three rules hold the shape together. Each already holds today, and each is
guarded by a test:

1. **A rule lives in a service, exactly once.** A route and a bot feature are
   both translators. Rules found living in a client (the gap analysis lists
   `SCOPE_FOR_BOOK` twice, the foreign-currency payslip rounding and the
   one-key policy) move into the service that owns them.
2. **The bot does not go over the network to reach the core.** It calls the
   services in-process; a network hop would add a failure mode and buy
   nothing. What it must share with the API is *semantics*: the same
   service, the same permission, the same refusal. Parity tests assert this.
   One already exists (`test_a_share_set_over_http_is_what_the_bot_reports`);
   the debt-settle and close-period work added more.
3. **An adapter translates and nothing else.**
   `test_the_adapter_never_reaches_the_database` fails the build otherwise.

## What a client needs from the core, and where it stands

| Need | Today | Target | Phase |
|---|---|---|---|
| A stable contract | `/api/v1`; OpenAPI without `securitySchemes` | a snapshot-tested contract, additive-only within v1 | Foundation |
| Safe retries | **built**: `Idempotency-Key` on every financial POST, required on payslip payments | — | done |
| One error shape | **built**: `{detail, error:{code,message,request_id,fields}}`, `X-Request-Id` on every response | — | done |
| Least-privilege credentials | **built:** a key cannot manage the account (`223d9ee`) | a `Principal` with scopes and book restriction | Foundation |
| Bounded consumption | **built:** amount bound, atomic Redis limiter, `Retry-After` (`9f6c5b0`) | per-principal quotas on data routes | Foundation |
| Knowing what changed | nothing | `domain_events` + `GET …/events?after=` cursor | Foundation |
| Being told what changed | nothing | signed outbound webhooks drained from `domain_events` | Developer API |
| Media that is not a messenger file id | messenger handle only | own blob storage behind a `receipts` contract; forwarding stays the bot's optimisation | Web/Mini App |
| Notifications on more than one channel | messenger adapters hard-wired | a `Notification` service with channels (messenger, push, email, webhook) | Mobile |
| Concurrent editors | last writer wins | `revision` + `If-Match` on transactions, then the rest | Web/Mini App |
| Multi-user third-party apps | none | OAuth 2.1 / OIDC on top of the same `Principal` and scopes | Ecosystem |

## Phased roadmap

Each phase ends when its acceptance tests pass in CI. No phase starts a client
before the contract it needs exists.

**1. Foundation (P0)**, before any second client:
- the error envelope and request id;
- a contract snapshot test;
- `Idempotency-Key`;
- `Principal` with scopes and book restriction (the account-management part is
  done);
- per-principal quotas;
- the `domain_events` table, emitted inside the services.

The order and test lists are in the gap analysis §5 and §7. Owner decisions
pending:
- coarse scopes versus one per permission (recommended: coarse);
- whether the payslip payment requires `Idempotency-Key` from day one
  (recommended: yes);
- how the webhook secret is stored.

**2. Developer API (P1):**
- outbound webhooks (HMAC-SHA256 signed, timestamped, retried with backoff,
  SSRF-guarded);
- key rotation with a 24-hour overlap;
- cursor pagination and `updated_since` on lists;
- the parity gaps closed (recurring rules, search, digest settings, rate quote,
  role change, ownership transfer);
- Python and TypeScript examples generated from the OpenAPI snapshot;
- an importable collection;
- a demo book.

**3. Web panel / Mini App (P1):**
- the roadmap already notes the web panel is a front-end project on a finished
  API;
- it needs revisions (`If-Match`), receipts upload and download, and CORS
  locked to known origins;
- a Mini App authenticates with Telegram's signed `initData` exchanged for a
  normal session.

**4. Mobile (P2):**
- push through the notification service;
- offline queueing, which depends on idempotency;
- the event cursor for sync.

**5. Ecosystem (P2):**
- OAuth 2.1 with PKCE and per-app consent, on the same scopes;
- an accountant export (beyond CSV), per the existing roadmap.

## What this does not change

- **Self-hosted, single deployment.** "A hosted multi-tenant version" stays
  under *Not planned* in `docs/roadmap.md`. Multi-client is not multi-tenant.
- **No microservices.** One API process and one bot process per messenger,
  which is the current deployment. A worker for webhooks joins them in phase 2,
  as a third process type rather than a new system.
- **The ledger stays double-entry and the chart of accounts stays fixed.**
