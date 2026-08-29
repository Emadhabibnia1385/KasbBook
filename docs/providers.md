# Providers

Three messengers, one conversation layer. This page is what differs between
them and how to add a fourth.

## What an adapter is

A translator. Provider payload in, `IncomingEvent` out. `OutgoingMessage` in,
provider API call out. That is all.

An adapter has no database session, no service, and no idea what a permission
is. `test_the_adapter_never_reaches_the_database` parses every module in
`adapters/` and fails the build if one imports SQLAlchemy or a service — it
walks the import graph rather than searching text, so a comment mentioning a
model cannot fail the build and a real import cannot hide in a string.

## The three

### Telegram

The reference implementation. Supports everything in `Capabilities`: inline
buttons, message editing, deletion, file upload and download, deep links,
webhooks, polling.

Official Bot API only. `https://api.telegram.org/bot{token}/{method}`.

### Bale

Bale's bot API **is** the Telegram Bot API with a different host — same methods,
same update envelope, same inline keyboards. So `BaleAdapter` is four lines of
configuration on top of `BotApiAdapter`, the shared dialect, and inherits every
behaviour the Telegram tests already cover.

`https://tapi.bale.ai/bot{token}/{method}`, deep links at `ble.ir`.

It signs no webhooks — see [security.md](./security.md).

Only the official API is used. Bale also has a web client whose endpoints can
be observed and an account login that issues an OTP to a real phone number.
Neither belongs in a product.

### Rubika

Genuinely different, so it is a real adapter rather than a subclass. Three
differences drive everything:

**The envelope.** `{"status": "OK", "data": {...}}` — no `ok`, no `result`.

**Buttons are not callbacks.** A press arrives as an ordinary new message
carrying `aux_data.button_id`. There is no callback id, nothing is spinning,
and `answer_callback` is a documented no-op that exists so the layer above can
call it without asking which provider it is talking to.

**Keypads carry the payload in the id.** Rubika hands back `id` on a press, so
that is where the callback data goes — not a separate field.

Also: uploads are two steps (ask for a URL, then post the bytes to it), paging
uses an opaque `next_offset_id` cursor rather than a numeric offset, and there
is no long-polling.

`https://botapi.rubika.ir/v3/{token}/{method}`.

### Eitaa

Not built. Deliberately deferred — see the [roadmap](./roadmap.md). `Provider.EITAA`
exists in the enum so identities can reference it, and asking the runner for it
fails at startup with "no adapter" rather than an `AttributeError` three screens
in.

## Capabilities

Each adapter declares what it can actually do. Anything false is switched off
in the UI rather than attempted and failed.

| | Telegram | Bale | Rubika |
|---|---|---|---|
| Inline buttons | ✓ | ✓ | ✓ (as `inline_keypad`) |
| Edit a message | ✓ | ✓ | ✓ (text and keypad separately) |
| Answer a callback | ✓ | ✓ | — (nothing to answer) |
| Webhook signature | ✓ | — | — |
| Conceal text (spoiler) | ✓ | — | — |
| Long polling | ✓ | ✓ | — (cursor paging) |

## The conformance suite

`tests/test_adapters_bale_rubika.py` ends with the same assertions run
against **all three** adapters:

- declares a `Provider` and `Capabilities`
- returns a message id that can be edited later — without one, the
  single-screen UX appends forever
- actually sends the buttons it was given
- ignores an update it has no business with
- refuses a deep link with no username
- reports an unreachable provider as unreachable, not as "no updates"
- reports a refusal as a refusal
- implements the whole protocol

That last one matters more than it looks. A missing method is a crash the first
time a user opens that screen — in production, on a provider nobody tested by
hand.

## Three outcomes, not two

`fetch_updates` returns an `UpdateBatch` with three possible states:

```python
batch.ok           # updates arrived (possibly zero)
batch.refused      # the provider answered, and said no
batch.unreachable  # nothing answered at all
```

Collapsing the last two into "no updates" is how a bot spins silently against a
revoked token for a week. The runner backs off differently for each: an
unreachable provider is usually a blip and retries soon; a refusal is a revoked
token or a flood wait and backs off harder, because hammering makes both worse.

## Adding a provider

**If its API is Telegram-shaped**, it is four lines:

```python
class NewAdapter(BotApiAdapter):
    provider = Provider.NEW
    api_root = "https://api.example.com"
    deep_link_template = "https://example.com/{username}?start={payload}"
    secret_header = "X-Example-Secret"      # or "" if it signs nothing
```

**If it is not**, write a real adapter. The checklist:

1. Add the value to `Provider` in `modules/identity/models.py`.
2. Add it to `MESSENGERS` if a person can link it.
3. Write `adapters/<name>.py` implementing the protocol in `adapters/base.py`.
4. Declare honest `Capabilities`. A false one is a feature switched off, not a
   feature that fails.
5. Register it in `ADAPTERS` in `apps/bot/runner.py`.
6. Add `<NAME>_BOT_TOKEN` and `<NAME>_BOT_USERNAME` to `shared/settings.py`.
7. Add it to `ADAPTERS` in the conformance test. The suite will tell you what
   is missing.
8. Add a migration only if it needs a column. Usually it does not.

Then run one process per provider: a second unit with its own environment file,
sharing the same database.

## What is out of bounds

No reverse-engineered web-client endpoints. No logging in as a human with an
OTP sent to a real phone. No unofficial client library as a core dependency.

A bot posts as a bot. Anything else is one terms-of-service change away from
taking every deployment down at once, and it puts a real person's account at
risk to save writing an adapter.
