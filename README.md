<div align="center">

<img src="./KasbBook_LOGO.png" alt="KasbBook" width="200"/>

# KasbBook

**Bookkeeping for a small business, wherever that business already talks.**

Type `فروش ۲۵۰ک` and it is recorded. The same account works from Telegram, Bale
and Rubika, and over an HTTP API. Money is exact, the calendar is Jalali, and
every transaction has a balanced journal entry behind it.

[![CI](https://img.shields.io/github/actions/workflow/status/Emadhabibnia1385/KasbBook/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Emadhabibnia1385/KasbBook/actions)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Release](https://img.shields.io/badge/release-1.0.0--beta.1-orange?style=flat-square)](https://github.com/Emadhabibnia1385/KasbBook/releases)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)

**English** · [فارسی](./README.fa.md)

### 📖 [Read the documentation](https://emadhabibnia1385.github.io/KasbBook/)

[Install](#install) · [Quick entry](#quick-entry) · [Architecture](#architecture) · [API](#the-api) · [Development](#development)

</div>

---

## What it is

A self-hosted bookkeeping bot for shopkeepers, freelancers and small teams.
Nothing to install on a phone, nothing to memorise: one line of text or a few
buttons, in the messenger people already have open.

It is also an API-first application. The bot is one client of the same
services the HTTP API exposes, which is why a permission cannot be enforced in
one place and forgotten in the other.

> **This is a beta.** It runs in production for its author and its tests are
> thorough, but it has not been run by many people on many books yet. Take
> backups — `scripts/backup.sh` does it for you — and read
> [docs/roadmap.md](./docs/roadmap.md) for what is deliberately not built.

## Install

One command on a fresh Debian or Ubuntu box:

```bash
curl -fsSL https://raw.githubusercontent.com/Emadhabibnia1385/KasbBook/main/scripts/install.sh | sudo bash
```

It checks the Python version, clones the code, starts PostgreSQL and Redis in
containers, generates the credentials it can generate, asks only for a bot
token, creates the schema, installs both services and then checks they actually
came up. Running it twice is safe.

| | |
|---|---|
| Update | `sudo /opt/kasbbook/scripts/update.sh` |
| Back up | `sudo /opt/kasbbook/scripts/backup.sh` |
| Restore | `sudo /opt/kasbbook/scripts/restore.sh <file>` |
| Remove | `sudo /opt/kasbbook/scripts/uninstall.sh` |

The update script takes a backup, runs the tests, migrates, restarts, and
**rolls itself back** if the new version does not come up clean. See
[docs/operations.md](./docs/operations.md).

## Quick entry

Most entries never touch a menu.

```
فروش ۲۵۰ک          →  income, "فروش", 250,000
اجاره ۲م           →  expense, "اجاره", 2,000,000
خرید ۱۲۵۰۰۰ دیروز  →  expense, dated yesterday
```

Persian digits, `ک` for thousand, `م` for million, Jalali dates with either
separator. Anything it cannot read, it asks about rather than guessing.

## What it does

| | |
|---|---|
| **Books** | personal, business, team, organization — one account, many books |
| **Ledger** | every transaction mirrored by a balanced double-entry journal |
| **Multi-currency** | rate captured at the moment of the transaction, never re-applied later |
| **Reports** | by month, year, week or category, in Jalali; CSV export |
| **Budgets** | a ceiling per category or per direction, with what is left |
| **Debts** | who owes whom, settled into a real transaction |
| **Loans** | instalments, what is paid, what is next |
| **Recurring** | rent and salary defined once, booked when due |
| **Payroll** | periods, member shares, bonuses and deductions, payslips, staged payment |
| **Treasury** | funds fed by rules, taken before profit is shared |
| **Reminders** | a daily digest at an hour you choose, in your own timezone |
| **Receipts** | a photo or a PDF, stored by reference on the messenger, never re-uploaded |
| **Search** | across categories and descriptions, with the total of every match |
| **Accounts** | email, phone, password, sessions — and deletion that keeps the ledger provable |
| **Sharing** | invite colleagues by email or phone, with roles and per-action permissions |
| **API** | the same services the bot uses, with rotating tokens and API keys |

## Architecture

```
                  Telegram      Bale      Rubika
                      │           │          │
                      └─────── adapters ─────┘      translate payloads, nothing else
                                  │
                    ┌─────────────┴─────────────┐
                    │      conversation         │   screens + routing, messenger-agnostic
                    └─────────────┬─────────────┘
                                  │
   HTTP API  ──────────────►  application services  ◄── every rule lives here, once
                                  │
                          domain models · ledger
                                  │
                        PostgreSQL · Redis · Alembic
```

Two clients, one set of rules. An adapter never touches the database — a test
walks the import graph and fails the build if one tries. See
[docs/architecture.md](./docs/architecture.md).

## The API

```bash
curl -X POST http://127.0.0.1:8210/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"you@example.com","password":"..."}'
```

Interactive documentation at `/docs` — the reference deployment is at
<https://kasbbook.nyxon.tech/docs>. Short-lived access tokens, rotating refresh tokens with theft
detection, API keys for programs, and rate limiting on the routes that need it.

**Money crosses the boundary as a string, never a JSON number.** JSON has one
numeric type and it is a float; `12500000.15` does not survive that round trip,
and a bookkeeping API that loses rials is not a bookkeeping API.

See [docs/api.md](./docs/api.md).

## Development

```bash
git clone https://github.com/Emadhabibnia1385/KasbBook.git
cd KasbBook && python3 -m venv venv
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest tests -q
```

The suite runs on SQLite with no network and no token, in about forty
seconds. The migration tests additionally rehearse against a real
PostgreSQL when `KASBBOOK_TEST_POSTGRES_URL` is set, which is what CI does,
because that is where the interesting failures live.

See [docs/development.md](./docs/development.md).

## Documentation

| | |
|---|---|
| [Getting started](./docs/getting-started.md) | install, first run, first book |
| [Architecture](./docs/architecture.md) | the layers and why they are where they are |
| [Configuration](./docs/configuration.md) | every environment variable |
| [Data model](./docs/data-model.md) | accounts, identities, books, permissions |
| [Double-entry](./docs/double-entry.md) | how the ledger stays balanced |
| [Payroll & treasury](./docs/payroll.md) | periods, shares, funds, payslips |
| [Providers](./docs/providers.md) | Telegram, Bale, Rubika, and adding one |
| [The API](./docs/api.md) | endpoints, auth, conventions |
| [Security](./docs/security.md) | tokens, hashing, what is stored and what is not |
| [Operations](./docs/operations.md) | deploy, back up, restore, roll back |
| [Development](./docs/development.md) | tests, migrations, conventions |
| [Troubleshooting](./docs/troubleshooting.md) | real failures and what caused them |
| [Roadmap](./docs/roadmap.md) | what is deliberately not built yet |

The same pages are published as a site — searchable, and in Persian as well:

| | |
|---|---|
| 🇬🇧 English | <https://emadhabibnia1385.github.io/KasbBook/> |
| 🇮🇷 فارسی | <https://emadhabibnia1385.github.io/KasbBook/fa/> |

## License

MIT. See [LICENSE](./LICENSE).
