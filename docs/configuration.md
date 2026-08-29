# Configuration

Everything is read from the environment, once, at startup, by
`shared/settings.py`. On a server that file is `/opt/kasbbook/.env`, mode
`600`, written by the installer.

Every value has a safe default except the two that cannot have one: a bot token
and a signing key.

## Core

| Variable | Default | Notes |
|---|---|---|
| `KASBBOOK_DATABASE_URL` | `sqlite+aiosqlite:///kasbbook.db` | SQLite by default so a developer can run the bot without standing up PostgreSQL. Production overrides it. |
| `REDIS_URL` | *(unset)* | Without it, conversation state and rate limiting are in-process — correct on one worker, wrong across several. |
| `KASBBOOK_LOG_LEVEL` | `INFO` | `httpx` and `httpcore` are pinned to `WARNING` regardless, because they log full request URLs and every one of these APIs puts the token in the path. |

## Which provider this process runs

One process, one provider.

| Variable | Default | Notes |
|---|---|---|
| `KASBBOOK_PROVIDER` | `telegram` | `telegram`, `bale` or `rubika`. An unknown value fails at startup with the list. |

Each provider reads its own credentials, so a Bale process cannot silently
start with the Telegram token:

| Provider | Token | Username | Webhook secret |
|---|---|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_BOT_USERNAME` | `TELEGRAM_WEBHOOK_SECRET` |
| Bale | `BALE_BOT_TOKEN` | `BALE_BOT_USERNAME` | — |
| Rubika | `RUBIKA_BOT_TOKEN` | `RUBIKA_BOT_USERNAME` | — |

The username is only needed to build deep links (`t.me/…?start=…`). Without it,
`create_deep_link` raises rather than producing a link that goes nowhere.

Only Telegram supports a webhook secret; it echoes the token we registered in a
header. Bale and Rubika sign nothing at all — see [security.md](./security.md)
for what is done instead.

**To run a second provider:** copy the unit and the environment file.

```bash
sudo cp /etc/systemd/system/kasbbook-bot.service /etc/systemd/system/kasbbook-bale.service
# point EnvironmentFile at /opt/kasbbook/.env.bale
# in that file: KASBBOOK_PROVIDER=bale and BALE_BOT_TOKEN=...
```

Both processes share one database, which is the point: an account linked to
both messengers is one set of books.

## The API

| Variable | Default | Notes |
|---|---|---|
| `KASBBOOK_SECRET_KEY` | **none** | Signs access tokens. The API refuses to start without it. Generate it, never type it. |
| `KASBBOOK_ACCESS_MINUTES` | `30` | Access tokens are not revocable, so they are short. |
| `KASBBOOK_REFRESH_DAYS` | `30` | Refresh tokens are looked up on every use, so they can be revoked. |
| `KASBBOOK_CORS_ORIGINS` | *(unset)* | Comma-separated. Never `*`: these endpoints carry credentials. |
| `KASBBOOK_TRUSTED_PROXY` | *(unset)* | Set only when a proxy you run is in front. It makes `X-Forwarded-For` trusted for rate limiting — without a real proxy, anyone can set that header and rate limiting becomes decorative. |
| `KASBBOOK_WEB_URL` | *(unset)* | Base URL used in links the bot sends. |
| `KASBBOOK_UPDATE_MODE` | `polling` | `polling` or `webhook`. Polling holds an outbound connection and needs nothing reachable from outside. A webhook needs a public HTTPS endpoint and loses updates that arrive while the API is restarting, because a provider retries for a while and then gives up. |
| `KASBBOOK_WEBHOOK_PATH` | *(unset)* | The unguessable segment in `/webhooks/<provider>/<secret>`. Required in webhook mode. Generate it, never choose it. |
| `KASBBOOK_API_URL` | *(unset)* | Where the API is published, e.g. `https://kasbbook.example.com`. The bot links to `<url>/docs` from its API screen; unset means no link rather than a dead one. |

To generate a key:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

## Datastores

`deploy/.env`, read by docker compose. Also written by the installer.

| Variable | Default |
|---|---|
| `POSTGRES_DB` | `kasbbook` |
| `POSTGRES_USER` | `kasbbook` |
| `POSTGRES_PASSWORD` | *(generated)* |
| `POSTGRES_PORT` | `5435` |
| `REDIS_PORT` | `6382` |

Both bind to `127.0.0.1` only. The ports are unusual because the box they were
written for already had 5432–5434 and 6380–6381 in use; change them freely.

These are deliberately **not** the host's PostgreSQL. That instance carries a
fleet of unrelated services, and sharing it would make one careless migration
everyone's problem.

## Operational

Read by the scripts, not by the application.

| Variable | Default |
|---|---|
| `KASBBOOK_HOME` | `/opt/kasbbook` |
| `KASBBOOK_BRANCH` | `main` |
| `KASBBOOK_BACKUP_DIR` | `/var/backups/kasbbook` |
| `KASBBOOK_BACKUP_KEEP` | `14` |

## Testing

| Variable | Effect |
|---|---|
| `KASBBOOK_TEST_POSTGRES_URL` | Enables `tests/test_migrations_postgres.py`. Without it those six tests skip, which is why a laptop without PostgreSQL still runs the rest of the suite. |

## A complete production file

```bash
KASBBOOK_PROVIDER=telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_BOT_USERNAME=KasbBook_BOT

KASBBOOK_DATABASE_URL=postgresql+asyncpg://kasbbook:PASSWORD@127.0.0.1:5435/kasbbook
REDIS_URL=redis://127.0.0.1:6382/0

KASBBOOK_SECRET_KEY=GENERATED-48-BYTES
KASBBOOK_ACCESS_MINUTES=30
KASBBOOK_REFRESH_DAYS=30

KASBBOOK_LOG_LEVEL=INFO
```

## If a token leaks

It has happened here. `httpx` logs full request URLs at `INFO`, and a Telegram
URL contains the token, so a debug session put one in the journal.

Rotate it at `@BotFather` (`/revoke`), put the new one in `.env`, and restart.
The old token starts returning 404 immediately, which is how you know.

The logger levels that prevent it are set in `apps/bot/runner.py` and are not
optional.
