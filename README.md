<div align="center">

<img src="./KasbBook_LOGO.png" alt="KasbBook Logo" width="220"/>

# KasbBook

**A Telegram bot that keeps the books for a small business.**

Record income and expenses in seconds, keep business money separate from personal money,
and get daily, monthly and yearly reports on the Jalali calendar.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![python-telegram-bot](https://img.shields.io/badge/PTB-21.11-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://python-telegram-bot.org)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)
[![Stars](https://img.shields.io/github/stars/Emadhabibnia1385/KasbBook?style=flat-square&logo=github)](https://github.com/Emadhabibnia1385/KasbBook/stargazers)

**English** · [فارسی](./README.fa.md)

[Install](#install) · [How it works](#how-it-works) · [Configuration](#configuration) · [Backups](#backups-and-restore) · [Troubleshooting](#troubleshooting)

</div>

---

## What it is

KasbBook is a self-hosted Telegram bot for shopkeepers, freelancers and small
businesses. Everything happens through inline buttons — there are no commands to
memorise and nothing to install on the phone.

The interface is entirely in Persian; this document describes it in English.

**It is built around one question:** *after all the business costs, personal
spending and loan installments, how much did I actually keep this month?*

---

## Features

| | |
|---|---|
| 🧾 **Three-way ledger** | Business income, business expense, personal expense — kept apart, so business performance is never blurred by personal spending. |
| 📄 **Installments tracked separately** | A locked `قسط` (installment) category is excluded from ordinary personal spending, so loan repayments show up as their own line. |
| 📅 **Jalali reports** | Yearly and monthly reports run on the Persian calendar — Farvardin to Esfand, not January to December. |
| 🏷 **Category breakdown** | Per-category totals with share percentages and transaction counts, for any period. |
| 📥 **CSV export** | Any period exported as a UTF-8 spreadsheet (with BOM, so Excel opens Persian correctly). |
| 🗄 **Safe backups** | Manual and scheduled backups to a chat or channel, plus a validated restore that cannot silently destroy your data. |
| 👥 **Access modes** | Admin-only, shared team ledger, or public multi-tenant — one setting. |
| 🌐 **Dual date entry** | Every date field accepts Gregorian (`YYYY-MM-DD`) or Jalali (`YYYY/MM/DD`). Persian digits work everywhere. |

---

## How it works

### The ledger

Every transaction has a type:

| Type | Meaning |
|---|---|
| `work_in` | Business income |
| `work_out` | Business expense |
| `personal_out` | Personal expense (the locked `قسط` category is split out) |

### The numbers

Every daily, monthly and yearly report is built from these:

```
net                  = business income − business expenses
operational savings  = net − personal spending (excluding installments)
final savings        = operational savings − installments
```

`net` tells you whether the business itself is healthy. `final savings` tells
you what is actually left in your pocket.

### Access modes

Set under **⚙️ Settings → 🔐 Bot access**. Only the primary admin sees this menu.

| Mode | Who can use the bot | Whose books |
|---|---|---|
| **Admin only** (default) | Primary admin + admins added in the panel | Each admin keeps a private ledger |
| **Admin only + sharing on** | Same | All admins read and write **one shared** ledger |
| **Public** | Anyone who starts the bot | Every user gets their own private ledger |

Anyone not authorised gets a message containing their own numeric ID and the
primary admin's username, so they know exactly who to ask.

---

## Install

### Automatic (recommended)

On a fresh **Ubuntu** server, as root:

```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/Emadhabibnia1385/KasbBook/main/install.sh
```

```bash
chmod +x install.sh && sudo ./install.sh
```

The installer is a menu: install, update, edit config, start/stop/restart, live
logs, status, uninstall. It creates a virtualenv, writes `/opt/kasbbook/.env`
with `600` permissions, and registers a `systemd` service.

> The installer never deletes an existing `KasbBook.db`. If it has to re-clone
> the project, the database, `.env` and `backups/` are moved aside first and
> restored afterwards.

### Manual

```bash
git clone https://github.com/Emadhabibnia1385/KasbBook.git /opt/kasbbook
```

```bash
cd /opt/kasbbook && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
```

```bash
cp .env.example .env && nano .env
```

```bash
./venv/bin/python bot.py
```

---

## Configuration

Everything lives in `.env`:

```env
BOT_TOKEN=123456:ABC-your-token-from-botfather
ADMIN_CHAT_ID=123456789
ADMIN_USERNAME=your_username
```

| Variable | Required | Purpose |
|---|---|---|
| `BOT_TOKEN` | yes | Token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_CHAT_ID` | yes | Numeric Telegram ID of the primary admin; also the default backup destination |
| `ADMIN_USERNAME` | yes | Shown to unauthorised users so they know who to contact (no `@`) |
| `PRIMARY_ADMIN_USER_ID` | no | Only if the admin's *user id* differs from the chat id above |

The bot refuses to start with a clear `RuntimeError` when a required variable is
missing — it will not run half-configured.

**Getting the values**

1. **Token** — message [@BotFather](https://t.me/BotFather), send `/newbot`, follow the prompts.
2. **Chat ID** — message [@userinfobot](https://t.me/userinfobot) and copy the `Id` number.

---

## Using it

```
/start    open the main menu
/cancel   leave whatever you are in the middle of
```

**Recording a transaction** — `📌 Transactions → ➕ New transaction`, then pick a
date (today / Gregorian / Jalali), a type, a category, an amount, and an optional
note. From the daily list you can also tap `New income` / `New expense` /
`New personal` to jump straight to the category step.

**The daily list** shows the day's totals and every row, grouped by type. Long
days are paged per section — 8 rows at a time — so the keyboard never grows past
what Telegram will render.

**Editing** — tap any row to open it, then change its category, amount, note or
**date**. Moving a transaction to another day is a single flow; the list for the
new day opens automatically. Deletion always asks for confirmation first.

**Reports** — `📊 Reports` opens the all-time summary, then a Jalali year, then a
Jalali month. Every level offers **🏷 Category breakdown** and **📥 CSV export**
for that exact period.

---

## Backups and restore

Under **⚙️ Settings → 🗄 Database** (primary admin only):

- **Backup now** — a consistent snapshot taken through SQLite's own backup API, sent to you as a file.
- **Scheduled backup** — on/off, every *N* hours, delivered to a chat ID or a channel.
- **Restore** — upload a `.db` file to replace the live database.

Restore is deliberately defensive. In order:

1. The uploaded file is opened read-only and checked — `PRAGMA integrity_check`
   plus a confirmation that the `transactions`, `categories` and `settings`
   tables exist. **A file that fails is rejected before anything is touched.**
2. The current database is snapshotted **to disk** under `backups/` *and* sent to
   you on Telegram.
3. Stale `-wal` / `-shm` sidecar files are removed — they belong to the old
   database and would corrupt the new one.
4. Only then is the file swapped in. If anything fails, the on-disk snapshot is
   restored automatically and you are told so.

---

## Managing the service

```bash
systemctl status kasbbook
```

```bash
systemctl restart kasbbook
```

```bash
journalctl -u kasbbook -f
```

---

## Project layout

```
KasbBook/
├── bot.py             the whole bot: handlers, database, reports, backups
├── install.sh         installer / updater / service manager menu
├── requirements.txt   pinned dependencies
├── .env.example       configuration template
├── README.md          this file
└── README.fa.md       Persian documentation
```

**Runtime files** (created on first run, never committed):

```
KasbBook.db            SQLite database, WAL mode
backups/               local snapshots taken before each restore
venv/                  virtualenv
.env                   secrets, mode 600
```

### Schema

| Table | Holds |
|---|---|
| `transactions` | `scope`, `owner_user_id`, `date_g`, `ttype`, `category`, `amount`, `description` |
| `categories` | Per-scope, per-owner, per-type category names; `is_locked` protects `قسط` |
| `admins` | Additional admins added through the panel |
| `settings` | Access mode, sharing flag, backup configuration |

Dates are stored as Gregorian ISO strings (`date_g`), which sort correctly as
plain text; every Jalali period in a report is converted into a Gregorian
`[start, end)` pair before it reaches SQL. Categories are stored on the
transaction as text, so renaming or deleting a category never orphans history.

---

## Troubleshooting

<details>
<summary><b>The bot will not start</b></summary>

```bash
journalctl -u kasbbook -n 80 --no-pager
```

Then try it in the foreground, where startup errors are obvious:

```bash
cd /opt/kasbbook && ./venv/bin/python bot.py
```

</details>

<details>
<summary><b>Invalid token</b></summary>

Get a fresh token from [@BotFather](https://t.me/BotFather), put it in
`/opt/kasbbook/.env`, then:

```bash
systemctl restart kasbbook
```

</details>

<details>
<summary><b>The bot replies "you are not registered"</b></summary>

That message includes your numeric ID. Either add that ID under
**⚙️ Settings → 🔐 Bot access → 👥 Manage admins**, or switch the bot to public
mode. Also confirm `ADMIN_CHAT_ID` in `.env` matches the primary admin's real ID.

</details>

<details>
<summary><b>Scheduled backups never arrive</b></summary>

Check that scheduled backup is on and the destination is reachable: for a channel
the bot must be a member with permission to post, and the ID must be the `-100…`
form. Failures are logged, not silent:

```bash
journalctl -u kasbbook | grep -i backup
```

</details>

<details>
<summary><b>Starting over</b></summary>

This deletes every transaction:

```bash
cd /opt/kasbbook && rm -f KasbBook.db KasbBook.db-wal KasbBook.db-shm && systemctl restart kasbbook
```

Take a backup from inside the bot first.

</details>

---

## Links

- **Bot** — [@KasbBook_BOT](https://t.me/KasbBook_BOT)
- **Channel** — [@KasbBook](https://t.me/KasbBook)
- **Developer** — [@EmadHabibnia](https://t.me/EmadHabibnia)

## License

[MIT](./LICENSE) © Emad Habibnia

<div align="center">

Built with ❤️ for people who run small businesses.

</div>
