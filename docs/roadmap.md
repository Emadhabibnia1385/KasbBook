# Roadmap

What is deliberately not built, and why. A roadmap that only lists intentions
is a wish list; this one is mostly about decisions.

## Deferred on purpose

### The web panel

Nothing is built. The API it would sit on is finished — auth, books,
transactions, reports, planning — so this is a front-end project, not a
back-end one.

Deferred because the people using this are in Telegram. A panel is for the
cases a chat is genuinely bad at: a long transaction list, a spreadsheet-shaped
report, managing many members at once.

### Eitaa

Not built. `Provider.EITAA` exists in the enum so identities can reference it,
and asking the runner for it fails at startup with "no adapter" rather than an
`AttributeError` three screens in.

Eitaa's bot API is thinner than the others', and its Mini App is where the real
surface is — which makes it a web project too.

## Worth building next

### Password reset

Not built, because there is no mail path. A reset flow without one is a support
ticket pretending to be a feature. It needs SMTP configuration first, and then
it is straightforward.

Note that an account with a linked messenger is not locked out by a forgotten
password: it can set a new one from the bot. Reset matters for the account that
has drifted away from its messenger, which is precisely the one a mail path
would serve.

## Done since this page was written

### Webhooks in production

Built and running. `KASBBOOK_UPDATE_MODE=webhook` moves update delivery to the
API process; the bot process registers the webhook at startup and afterwards
only sends reminders. Switching back is the same setting.

Polling keeps a real advantage worth stating, and remains the default: it works
from behind any NAT with no inbound port, and it does not lose updates while
the API restarts. Webhook mode trades that for not holding a connection open.

The first thing it cost was a secret in the journal — the path carries the
secret, nginx was told not to log it, and uvicorn's own access log had not
been. See [security.md](./security.md).

### Account deletion

Built. `DELETE /auth/me` with a preview endpoint, immediate and irreversible,
refusing while a shared book would be orphaned. It is on this page's history
rather than its future because the entry that said the foreign keys made it
impossible was wrong: they made it *careful*, not impossible.

## Smaller things

| | |
|---|---|
| **Budget periods other than monthly** | Both `kind` values are used, but the window is hardcoded to the Jalali month in `BudgetService.status`; there is no period column. |
| **Exports beyond CSV** | A real accountant wants something their software imports. |

## Not planned

**Two-factor authentication.** Declined by the owner. The token machinery
would have made it cheap — a table, a step at login, recovery codes — so this
is a product decision rather than a cost one, and it can be revisited without
anything needing to be undone first.

**Unofficial provider APIs.** No reverse-engineered web-client endpoints, no
logging in as a human with an OTP. A bot posts as a bot. Anything else is one
terms-of-service change away from taking every deployment down at once.

**A hosted multi-tenant version.** This is self-hosted software. Running other
people's books means being responsible for other people's money, and that is a
different product with different obligations.

**Rewriting the ledger to be "simpler".** The double-entry journal is the
reason the books are provable. A single-entry list would be less code and
would silently lose the ability to answer "does this add up?".

**A configurable chart of accounts.** Six accounts is the minimum a book needs.
A system that lets a shopkeeper design their own is a system that lets them
design a broken one.

## Known gaps

Stated rather than hidden:

- **Bale and Rubika have not been tested against their live APIs.** They are
  written against the published documentation and covered by the same
  conformance suite as Telegram, with mock transports. That proves the shapes
  and the logic; it does not prove the remote end agrees. First contact with a
  real token may need adjustments.
- **The reminder loop sends before it confirms.** Deliberate — a duplicate
  reminder is worse than a missed one — but it means a delivery failure costs
  that day's digest.
- **In-process rate limiting is per-worker.** Correct on one worker, wrong
  across several. Redis fixes it and the API warns at startup when it is
  missing.
- **Recurring catch-up is capped at 400 firings.** A rule years behind will not
  fully catch up in one run. It will over several, and the cap stops one call
  spending an afternoon writing transactions.
