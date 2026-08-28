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

### ~~Account deletion~~ — built

Books nobody else is on are destroyed with everything in them. Books shared
with other people are not one person's to destroy, so the whole operation
refuses until they are handed over, naming them.

What happens to the account row depends on what still points at it.
`transactions.actor_user_id`, `adjustments.recorded_by` and
`recurring_rules.created_by_user_id` are RESTRICT — the ledger saying a
financial record must not lose its author. If records in other people's books
name this person, the row survives with every personal detail stripped: no
name, no email, no phone, no password, no identities, no way in. Otherwise the
row goes.

See [data-model.md](./data-model.md).

### Two-factor authentication

TOTP on the API. The token machinery is already in place, so this is a table, a
verification step at login, and recovery codes.

### Password reset

Not built, because there is no mail path. A reset flow without one is a support
ticket pretending to be a feature. It needs SMTP configuration first, and then
it is straightforward.

Note that an account with a linked messenger is not locked out by a forgotten
password: it can set a new one from the bot. Reset matters for the account that
has drifted away from its messenger, which is precisely the one a mail path
would serve.

### Webhooks in production

The route exists and is tested; polling is what actually runs. Switching over
needs a public hostname and TLS termination, which is a deployment decision
rather than a code one.

Polling has a real advantage worth stating: it works from behind any NAT with
no inbound port, which is most of the boxes this will ever run on.

## Smaller things

| | |
|---|---|
| **Budget periods other than monthly** | Both `kind` values are used, but the window is hardcoded to the Jalali month in `BudgetService.status`; there is no period column. |
| **Exports beyond CSV** | A real accountant wants something their software imports. |

## Not planned

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
