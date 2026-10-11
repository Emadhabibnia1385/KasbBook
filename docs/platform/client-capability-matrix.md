# Client capability matrix

What each client can do, and what it falls back to when it cannot. A feature is
designed once, in the services; this table is how each surface presents it.
Bale and Rubika columns describe the adapters as written against the providers'
published documentation, which `docs/roadmap.md` notes are untested against the
live APIs.

Legend: ✅ supported · ◐ degraded (fallback noted) · — not available · *planned*

| Capability | Telegram | Bale | Rubika | Web / Mini App *(planned)* | Mobile *(planned)* | API key (program) |
|---|---|---|---|---|---|---|
| Inline buttons, edit-in-place | ✅ | ✅ | ✅ | ✅ | ✅ | n/a |
| Callback data ≤ 64 bytes | ✅ enforced | ✅ | ✅ | n/a | n/a | n/a |
| Conceal a secret (spoiler) | ✅ | ◐ shown plainly (no spoiler markup) | ◐ shown plainly; it used to be dropped, fixed in this branch | ✅ | ✅ | n/a |
| Delete the user's typed message (passwords) | ✅ | ✅ | ✅ | n/a | n/a | n/a |
| Receipt: forward by file id | ✅ | ✅ | ✅ | — needs blob storage (P1) | — needs blob storage | — upload is P1 |
| File download (CSV export) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `export.csv` |
| Proactive messages (digest, due dates, recurring notices) | ✅ | ✅ | ✅ | — needs notification service | — needs push (P2) | — needs webhooks (P1) |
| Quick entry in free text | ✅ | ✅ | ✅ | ✅ (can reuse `bot/quick.py` server-side) | ✅ | — structured only |
| Jalali display | ✅ | ✅ | ✅ | client-side | client-side | Gregorian on the wire |
| Payroll and treasury | ✅ | ✅ | ✅ | ✅ (wide tables suit the web) | ◐ read-mostly | ✅ |
| Close a period | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `…/close` |
| Settle a debt and record the money | ✅ asks | ✅ asks | ✅ asks | ✅ | ✅ | ✅ `record_transaction` |
| Safe retry of money movements | ✅ nonce / atomic claim | ✅ | ✅ | needs `Idempotency-Key` (P0) | needs `Idempotency-Key` (P0) | ◐ loans only today |
| Concurrent editing | n/a, one person per chat | n/a | n/a | needs `If-Match` (P1) | needs `If-Match` | needs `If-Match` |
| Manage the account (keys, password, contact, close) | ✅ | ✅ | ✅ | ✅ (bearer) | ✅ (bearer) | — **refused** by design (403) |

## Fallback rules

- **A capability missing on one messenger degrades. It never disappears
  silently.** The adapter conformance suite checks each provider implements the
  whole protocol (`test_every_adapter_implements_the_whole_protocol`). Where a
  provider cannot do something, the adapter does the nearest safe thing. A
  refused edit becomes a new message, on every provider. A secret that cannot be
  concealed is shown plainly rather than dropped: the Rubika adapter used to drop
  it, so an API key issued there reached nobody.
- **A client without a channel for proactive messages still has the data.** The
  recurring notice, the due-date warnings and the digest are all reconstructible
  from the API. The notification service (P1/P2) adds channels; it does not move
  the rules.
- **The capability set is data, not code paths.** When the web panel ships, the
  API will expose `GET /api/v1/capabilities` (per client type: which features are
  enabled on this deployment), so a client hides what this install does not
  offer instead of failing on it.
