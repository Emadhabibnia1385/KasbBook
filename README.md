<div align="center">

<img src="./KasbBook_LOGO.png" alt="KasbBook Logo" width="220"/>

# KasbBook

**A Telegram bot that keeps the books for a small business.**

Type `فروش 250000` and it's recorded. Business money stays separate from personal money,
loans know how many installments are left, and every report runs on the Jalali calendar.

[![CI](https://img.shields.io/github/actions/workflow/status/Emadhabibnia1385/KasbBook/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Emadhabibnia1385/KasbBook/actions)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![python-telegram-bot](https://img.shields.io/badge/PTB-21.11-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://python-telegram-bot.org)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)

**English** · [فارسی](./README.fa.md)

[Install](#install) · [Quick entry](#quick-entry) · [How it works](#how-it-works) · [Features](#what-it-does) · [Backups](#backups-and-restore) · [Development](#development)

</div>

---

## What it is

KasbBook is a self-hosted Telegram bot for shopkeepers, freelancers and small
businesses. Everything happens through inline buttons or a single line of text —
there is nothing to install on the phone and nothing to memorise.

The interface is entirely in Persian; this document describes it in English.

**It is built around one question:** *after all the business costs, personal
spending and loan installments, how much did I actually keep this month?*

---

## Quick entry

The fastest path is not a menu. Send a line and it is recorded:

```
فروش 250000              → income "فروش", 250,000, today
اجاره ۱٫۲م بابت مرداد     → expense "اجاره", 1,200,000, note "بابت مرداد"
1405/05/31 خدمات ۵۰۰ک    → on that Jalali date, 500,000
```

The category decides the type, so nothing else needs saying. If the category is
new, or exists in more than one group, the bot asks once and remembers.

**Amounts** accept whatever you'd naturally type: `250000`, `۲۵۰,۰۰۰`, `250k`,
`۲۵۰ک`, `1.2m`, `۱٫۲م`, `2 میلیون`, `1.5 میلیارد`.

**Dates** accept either calendar and either separator — `1405/05/31`, `1405-5-31`,
`2026-08-22` — plus `امروز`, `دیروز` and `فردا`. Persian and Arabic-Indic digits
work everywhere.

---

## What it does

| | |
|---|---|
| ⚡ **One-line entry** | Type the category and amount. No menus, no taps. |
| 🧾 **Four-way ledger** | Business income, business expense, personal income, personal expense — kept apart, so business performance is never blurred by personal life. |
| 📄 **Real loan tracking** | Define a loan once; the bot tells you how many installments remain, how much is left, and when the last one falls. |
| 🔁 **Recurring transactions** | Rent, salary, subscriptions — defined once, booked automatically, with catch-up if the bot was offline. |
| 📅 **Jalali reports** | Yearly and monthly reports run Farvardin to Esfand, not January to December. |
| 📈 **Period comparison** | Every month and year is shown against the one before it, with direction and percentage. |
| 📆 **Custom ranges** | Any two dates, not just whole months and years. |
| 🔎 **Search** | Find transactions by category or note, paged, with a running total. |
| 🎯 **Budgets** | A monthly ceiling per category or per group, with a progress bar and a warning the moment a spend crosses it. |
| 🤝 **Debts and receivables** | Who owes you, who you owe, and when it is due — tracked separately, so it never distorts income. |
| 📉 **Trend chart** | Six or twelve months of income, expense, net or savings as a bar chart. |
| 🧾 **Receipts** | Attach a photo or file to any transaction and pull it back up later. |
| ↩️ **Undo** | A deleted transaction can be put back with one tap. |
| 🔔 **Reminders** | An end-of-day summary and a heads-up before each installment falls due. |
| 🏷 **Category breakdown** | Per-category totals with share percentages and counts, for any period. |
| 📥 **CSV export** | Any period as a UTF-8 spreadsheet (with BOM, so Excel opens Persian correctly). |
| 💱 **Currency** | تومان, ریال, or anything you name. Shown on every figure. |
| 🗄 **Safe backups** | Manual and scheduled backups to a chat or channel, plus a validated restore that cannot silently destroy your data. |
| 👥 **Access modes** | Admin-only, shared team ledger, or public multi-tenant — one setting. |

---

## How it works

### The ledger

| Type | Meaning |
|---|---|
| `work_in` | Business income |
| `work_out` | Business expense |
| `personal_in` | Personal income from outside the business |
| `personal_out` | Personal expense (the locked `قسط` category is split out) |

### The numbers

Every daily, monthly and yearly report is built from these:

```
net                  = business income − business expenses
operational savings  = net + personal income − personal spending (excluding installments)
final savings        = operational savings − installments
```

`net` tells you whether the business itself is healthy. `final savings` tells
you what is actually left in your pocket.

### Loans

A loan is a title, an installment amount, a count and a start date. Tapping
**ثبت پرداخت قسط** books one installment as a personal expense in the locked
`قسط` category, linked back to its loan. The bot then reports progress —
*8 of 24 paid (33%), 32,000,000 remaining, last installment Mehr 1406*.

Deleting a loan keeps its payments: that money really did move.

### Budgets

Set a monthly ceiling on a single category (`اجاره`) or a whole group (all
business expenses). The budget screen shows a bar per budget, and recording a
transaction that pushes one past 80% — or over the line — says so straight away.
Budgets are per Jalali month and never block a transaction; they inform, they do
not police.

### Debts and receivables

A credit sale is income you already recorded *and* money someone still owes you.
KasbBook keeps that second half in its own ledger: person, direction, amount,
optional due date. **Debts never create transactions**, so nothing is counted
twice; settling one moves it to history and out of the totals.

### Access modes

Set under **⚙️ Settings → 🔐 Bot access**. Only the primary admin sees this menu.

| Mode | Who can use the bot | Whose books |
|---|---|---|
| **Admin only** (default) | Primary admin + admins added in the panel | Each admin keeps a private ledger |
| **Admin only + sharing on** | Same | All admins read and write **one shared** ledger |
| **Public** | Anyone who starts the bot | Every user gets their own private ledger |

Public mode is rate limited per user (transactions per day, categories in total)
so an open bot cannot be used to fill the disk. Admin mode is unrestricted.

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
> restored afterwards. Updating snapshots the database before pulling.

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

**Recording** — send one line (see [Quick entry](#quick-entry)), or walk the menu:
`📌 Transactions → ➕ New transaction`. From the daily list, the four buttons at
the top jump straight to the category step for that day.

**The daily list** shows the day's totals and every row, grouped by type. Long
days are paged per section — 8 rows at a time — so the keyboard never grows past
what Telegram will render.

**Editing** — tap any row to open it, then change its category, amount, note or
**date**. Moving a transaction to another day is a single flow. Deletion always
asks for confirmation first.

**Reports** — `📊 Reports` opens the all-time summary, then a Jalali year, then a
Jalali month; monthly and yearly views include a comparison with the previous
period. Every level offers **🏷 Category breakdown** and **📥 CSV export**, and the
root adds **🔎 Search** and **📆 Custom range**.

**Everything else** lives under `⚙️ Settings`: loans (`📄 اقساط و وام‌ها`),
debts (`🤝 طلب و بدهی`), budgets (`🎯 بودجه‌ها`), recurring transactions
(`🔁 تراکنش‌های تکرارشونده`), reminders (`🔔 یادآورها`) and currency (`💱 واحد پول`).

**Reminders** — turn on the end-of-day summary (and pick its hour) or the
installment heads-up (and how many days of warning). Both go to the primary
admin.

---

## Backups and restore

Under **⚙️ Settings → 🗄 Database** (primary admin only):

- **Backup now** — a consistent snapshot taken through SQLite's own backup API, sent to you as a file.
- **Scheduled backup** — on/off, every *N* hours, delivered to a chat ID or a channel.
- **Restore** — upload a `.db` file to replace the live database.

Restore is deliberately defensive. In order:

1. The uploaded file is opened read-only and checked — `PRAGMA integrity_check`
   plus a confirmation that the expected tables exist. **A file that fails is
   rejected before anything is touched.**
2. The current database is snapshotted **to disk** under `backups/` *and* sent to
   you on Telegram.
3. Stale `-wal` / `-shm` sidecar files are removed — they belong to the old
   database and would corrupt the new one.
4. Only then is the file swapped in. If anything fails, the on-disk snapshot is
   restored automatically and you are told so.

An older backup restores fine: the schema is versioned, and migrations run
automatically on the restored file (taking their own snapshot first).

---

## Schema and migrations

The database carries a `schema_version`. On startup, any pending migration runs
in order, after a pre-migration snapshot is written to `backups/`. Migrations are
idempotent — a half-applied upgrade resumes rather than corrupts.

| Table | Holds |
|---|---|
| `transactions` | `scope`, `owner_user_id`, `date_g`, `ttype`, `category`, `amount`, `description`, `loan_id`, `receipt_file_id` |
| `categories` | Per-scope, per-owner, per-type category names; `is_locked` protects `قسط` |
| `loans` | Title, installment amount, installment count, start date |
| `recurring` | A transaction template plus a period and the next due date |
| `budgets` | A monthly ceiling per category or per group |
| `debts` | Person, direction, amount, due date, settlement time |
| `admins` | Additional admins added through the panel |
| `settings` | Schema version, access mode, sharing flag, currency, backup configuration |

Dates are stored as Gregorian ISO strings (`date_g`), which sort correctly as
plain text; every Jalali period in a report is converted into a Gregorian
`[start, end)` pair before it reaches SQL. Categories are stored on the
transaction as text, so renaming or deleting a category never orphans history.

---

## Development

```bash
pip install -r requirements-dev.txt
```

```bash
python tests/smoke_test.py
```

The smoke test needs no network and no Telegram token. It builds the whole
`Application` (which compiles every handler pattern), runs a real v1 database
through the migrations, and exercises the parsing, report, loan, recurring, CSV
and backup-validation logic against a throwaway database.

Its most valuable check is structural: **every `callback_data` that any keyboard
can emit is matched against every registered handler pattern**, so a button that
would do nothing fails the build instead of reaching a user. Keyboards are also
audited against Telegram's size limits.

CI runs the test plus `pyflakes` on Python 3.9, 3.11 and 3.12 for every push.

---

## Project layout

```
KasbBook/
├── bot.py                  entry point (10 lines)
├── kasbbook/
│   ├── config.py           environment, constants, logging
│   ├── store.py            connection, schema, migrations, snapshots
│   ├── jalali.py           calendar conversions and period ranges
│   ├── parsing.py          amount and date parsers
│   ├── text.py             RTL rendering, keyboards, safe edits
│   ├── money.py            currency and money formatting
│   ├── access.py           permissions, scope resolution, quotas
│   ├── states.py           conversation state constants
│   ├── menus.py            navigation keyboards
│   ├── categories.py       category storage and keyboards
│   ├── ledger.py           transactions, totals, daily list, detail view
│   ├── reports.py          reports, breakdown, trend, search, CSV
│   ├── loans.py            loans and installment schedules
│   ├── recurring.py        recurring rules and their job
│   ├── budgets.py          monthly ceilings and warnings
│   ├── debts.py            debts and receivables
│   ├── backups.py          backup delivery and the database menu
│   ├── reminders.py        daily digest and installment reminders
│   ├── handlers/           one module per screen group
│   └── app.py              handler registration
├── install.sh              installer / updater / service manager menu
├── tests/smoke_test.py     offline test suite
├── .github/workflows/      CI
├── requirements.txt        pinned runtime dependencies
├── requirements-dev.txt    test and lint tooling
├── .env.example            configuration template
├── README.md               this file
└── README.fa.md            Persian documentation
```

Modules are layered, and the test suite fails the build on a circular import or
a module that grows past 900 lines. `kasbbook/__init__.py` re-exports the public
surface, so anything can be reached from one place without flattening the code.

**Runtime files** (created on first run, never committed):

```
KasbBook.db            SQLite database, WAL mode
backups/               snapshots taken before each restore and migration
venv/                  virtualenv
.env                   secrets, mode 600
```

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
<summary><b>A quick-entry line was not understood</b></summary>

The line needs a category and an amount, in that order: `فروش 250000`. When the
amount comes first, only the next single word is taken as the category — put the
category first if it is more than one word. The bot never guesses: if it cannot
read the line, it says so rather than recording the wrong thing.

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
