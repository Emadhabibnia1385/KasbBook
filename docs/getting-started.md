# Getting started

## On a server

```bash
curl -fsSL https://raw.githubusercontent.com/Emadhabibnia1385/KasbBook/v2/scripts/install.sh | sudo bash
```

You need Debian or Ubuntu, Python 3.11 or newer, and Docker if you want the
installer to provide PostgreSQL and Redis for you. It will ask for one thing: a
bot token from [@BotFather](https://t.me/BotFather).

Everything else it generates — the database password, the signing key — because
a secret a person chooses is a secret a person can guess.

Running it again is safe. It repairs a half-finished install, leaves an
existing `.env` alone, and adds anything missing from it.

When it finishes:

```
✓ kasbbook-bot is running
✓ kasbbook-api is running
✓ the API answers /readyz
```

If it does not say that, it prints the last fifteen log lines and exits
non-zero rather than claiming success. See [troubleshooting.md](./troubleshooting.md).

## On a laptop

No Docker, no PostgreSQL, no token needed for the tests.

```bash
git clone -b v2 https://github.com/Emadhabibnia1385/KasbBook.git
cd KasbBook
python3 -m venv venv
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest tests -q
```

To actually run the bot, you need a token and a database. SQLite is the
default, so this is enough:

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_BOT_USERNAME=YourBot
export KASBBOOK_DATABASE_URL="sqlite+aiosqlite:///kasbbook.db"
./venv/bin/alembic upgrade head
./venv/bin/python apps/bot/runner.py
```

And the API:

```bash
export KASBBOOK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
PYTHONPATH=src ./venv/bin/uvicorn --factory kasbbook.api.app:create_app --reload
```

Then open `http://127.0.0.1:8000/docs`.

## First run, as a user

**1. Say `/start`.** The bot has never seen this messenger account, so it hands
you a one-time code and asks you to claim it. That code is how a Telegram
account becomes attached to a KasbBook account rather than *being* one — see
[data-model.md](./data-model.md) for why that distinction matters.

**2. Make a book.** Personal, business, team or organization. The type is not
cosmetic: a team book gets payroll and member shares, a personal one does not,
and the default scope for a transaction follows from it.

**3. Record something.** Either press through the buttons, or just type:

```
فروش ۲۵۰ک
```

Income, category "فروش", 250,000. Behind it, a balanced journal entry was
written; `trial_balance()` on that book now returns two equal numbers.

**4. Ask for a report.** Reports run on the Jalali calendar. `1403-05` is
Mordad of 1403 — converted to a Gregorian range before the query, so the
database never sees a Jalali value and you never see a Gregorian one.

## What to set up next

| | |
|---|---|
| **Reminders** | A daily digest at an hour you choose, in your timezone. On by default at 21:00 — a bookkeeping tool that never speaks first is one people forget to open. |
| **Budgets** | A ceiling per category. The bot warns as you approach it, not after. |
| **Recurring rules** | Rent, salary, subscriptions. Defined once, booked when due, and it catches up if the bot was down. |
| **A second messenger** | Link Bale or Rubika to the same account from the identities screen. Same books, different app. |

## Where things live on a server

```
/opt/kasbbook/          the checkout, the venv, .env
/opt/kasbbook/deploy/   docker-compose.yml, deploy/.env
/var/backups/kasbbook/     the last 14 dumps
/etc/systemd/system/       kasbbook-bot.service, kasbbook-api.service
```

```bash
journalctl -u kasbbook-bot -f      # what the bot is doing
journalctl -u kasbbook-api -f      # what the API is doing
sudo /opt/kasbbook/scripts/update.sh
```
