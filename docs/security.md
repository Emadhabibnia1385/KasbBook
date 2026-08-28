# Security

## What is stored, and what is not

Nothing here ever persists a credential in a form that can be replayed.

| Credential | Column | Algorithm |
|---|---|---|
| Password | `users.password_hash` | Argon2id, via `argon2-cffi` defaults |
| Link code | `link_tokens.token_digest` | SHA-256 |
| Refresh token | `refresh_tokens.token_digest` | SHA-256 |
| API key | `api_keys.token_digest` | SHA-256 |

Argon2 for the password because it is chosen by a human and must survive an
offline attack. SHA-256 for the rest because they are 32 bytes of `secrets`
output — there is no dictionary to run against them, and the cost of Argon2 on
every request would buy nothing.

A database dump gives an attacker no usable credential.

## The three token types

They are deliberately different, and the differences are the design.

### Access token — a signed JWT

Nothing looks it up by id. It is checked by verifying a signature, which is
cheap, and it is short-lived: 30 minutes by default.

It *can* be ended early, by exactly one lever. Every token carries the
`token_generation` its account had when the token was minted, and
`revoke_all_for_user` bumps that counter — so a password change or a "sign out
everywhere" invalidates issued tokens immediately rather than leaving them
working for their remaining lifetime. The check costs nothing: the account row
is already loaded to see whether it is active.

A counter rather than a timestamp, because `iat` has one-second granularity. A
token minted and a cutoff set in the same second compare equal, and the old
token slips through — which is exactly what a live smoke test caught before
this shipped.

`typ: "access"` is in the payload and checked on the way in, so a refresh token
cannot be presented as a bearer.

### Refresh token — a random secret, stored as a digest

Looked up on every use, which is what makes it revocable. That is its whole
reason to exist.

**Rotation:** every refresh mints a new token and revokes the one it came from.

**Theft detection:** if a token that has already been exchanged is presented
again, two parties hold it and there is no way to tell which one is asking. The
entire family — every token descended from that login — is revoked. The
legitimate holder is signed out, which is a much smaller harm than the
alternative.

```
login  →  T1
T1     →  T2   (T1 revoked, replaced_by = T2)
T1     →  ✗    family revoked; T2 dies too
```

That revocation **commits before the error is raised**. It is the one place a
service commits its own work: the request is about to fail, the caller rolls
back on failure, and a rollback would undo the revocation — leaving the stolen
family alive and the detection doing nothing at all. It was written that way,
shipped that way, and a test caught it.

### API key — for programs, not people

Shown once, at creation. Does not expire on its own, because a nightly job
should not stop at 3am. An 8-character prefix is kept in the clear so a key can
be recognised in a list and revoked without being produced.

Sent as `X-API-Key`. Resolves to the same `User` as a bearer token, so no route
below has to care which arrived.

## Rate limiting

Fixed windows, per address **and** per account:

| Route | Limit |
|---|---|
| `POST /auth/login` | 5/min per IP, 10/min per identifier |
| `POST /auth/register` | 3/hour per IP |

Both, because one alone is not enough. Per-IP alone lets a botnet hammer one
account; per-account alone lets one attacker lock every user out by trying
their addresses.

Fixed windows are not the most elegant algorithm — a burst straddling a
boundary briefly gets double the budget. That is an acceptable trade for
something a login route consults on every request. What it buys is the thing
that matters: password guessing stops being free.

With Redis it is shared across workers. Without, it is per-process — correct on
one worker and useless across several, and the API logs a warning saying so at
startup rather than pretending otherwise.

## Account enumeration

A wrong password and an unknown account return the **same status and the same
body**. Two different answers would turn the login route into a tool for
finding out who has an account.

The same rule applies elsewhere: `books.require` raises `NotFound` for a
non-member rather than `PermissionDenied`, so book ids cannot be probed. Trying
to revoke someone else's API key returns 404, not 403.

## Webhooks

This is the one place where the honest answer is uncomfortable.

**Telegram** echoes a secret token we registered, in
`X-Telegram-Bot-Api-Secret-Token`. That is compared with `hmac.compare_digest`.
Real verification.

**Bale and Rubika sign nothing.** There is no header, no signature, no shared
secret. Their adapters' `verify_webhook` returns `True` and the docstring says
plainly that it cannot prove the caller is who they claim — because claiming a
check that is not happening would be worse than admitting there is none.

What protects them instead is the path: `/api/v1/webhooks/{provider}/{secret}`,
compared in constant time, 404 on a mismatch. An unconfigured provider and a
wrong secret return the same 404, so a prober cannot tell which they got wrong.

That is weaker than a signature. It is what the providers make possible.

**Polling avoids the question entirely**, and is the default.

## Passwords typed into a chat

The bot can set a password, which means someone types one into Telegram. That
is only acceptable because the message is deleted the moment it is handled —
`apps/bot/runner.py` removes every incoming message, and a test asserts the
password case specifically. Without that the password would sit in the chat, on
the device, and in every backup of both.

A delete that fails — too old, or no permission in a group — is logged and
ignored rather than failing an update that already succeeded. It is worth
knowing that this makes the guarantee best-effort rather than absolute.

Changing an existing password requires the current one. Whoever holds the
linked messenger can already read and change the books, so this buys less than
it looks; what it does buy is that a stolen phone cannot quietly take the web
side too. Setting a *first* password does not ask, because there is nothing to
ask for.

Either way, every session is revoked afterwards — refresh tokens *and*
already-issued access tokens.

## Secrets in logs

`httpx` logs full request URLs at `INFO`, and every one of these bot APIs puts
the token in the path. That is how a token ended up in a journal here once.

`apps/bot/runner.py` pins `httpx` and `httpcore` to `WARNING`. It is not
optional and it has a comment saying why.

Unhandled exceptions are logged in full and reported to the caller as
`{"detail": "something went wrong on our side"}` — an exception message can
carry a query, a path, or a value from someone else's account.

## Transport

The API binds to `127.0.0.1` only. TLS and edge rate limiting belong in the
reverse proxy already on the box, not in the application process.

CORS origins are listed explicitly and never `*`. A wildcard with credentials
enabled is a hole, not a convenience — and it is off entirely unless
`KASBBOOK_CORS_ORIGINS` is set.

`X-Forwarded-For` is trusted for rate limiting **only** when
`KASBBOOK_TRUSTED_PROXY` says a proxy is in front. Without that, anyone can set
the header and rate limiting becomes decorative.

## Process isolation

Both systemd units run with the privileges they actually need, which is none:

```
NoNewPrivileges  PrivateTmp  ProtectSystem=strict  ProtectHome
ReadWritePaths=/opt/kasbbook-v2  ProtectKernelTunables  ProtectControlGroups
```

The bot makes outbound HTTPS calls and talks to loopback. Everything else is
denied.

## What is deliberately not built

- **No 2FA.** Worth having; not yet written. On the [roadmap](./roadmap.md).
- **No password reset by email.** There is no mail path, and a reset flow
  without one is a support ticket pretending to be a feature.
- **No account deletion.** The foreign keys would block it, correctly — see
  [data-model.md](./data-model.md).
- **No unofficial provider APIs.** No reverse-engineered web-client endpoints,
  no logging in as a human with an OTP. A bot posts as a bot.
