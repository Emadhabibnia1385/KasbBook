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

### Account deletion

There is no way to delete an account, and the foreign keys would block one: a
user owns books, books own accounts, and accounts are referenced by journal
lines that must not vanish.

That is the right default for a ledger — you should not be able to make a book
unprovable with a `DELETE` — but "no path at all" is not the right answer
either. It needs a design: transfer ownership, then anonymise the user row
while the ledger keeps its shape.

### Two-factor authentication

TOTP on the API. The token machinery is already in place, so this is a table, a
verification step at login, and recovery codes.

### Password reset

Not built, because there is no mail path. A reset flow without one is a support
ticket pretending to be a feature. It needs SMTP configuration first, and then
it is straightforward.

### Webhooks in production

The route exists and is tested; polling is what actually runs. Switching over
needs a public hostname and TLS termination, which is a deployment decision
rather than a code one.

Polling has a real advantage worth stating: it works from behind any NAT with
no inbound port, which is most of the boxes this will ever run on.

## Smaller things

| | |
|---|---|
| **Attachment types beyond photos** | Documents and voice parse already; only photos are wired to receipts. |
| **Budget periods other than monthly** | The model has `kind`; only monthly is exercised. |
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
