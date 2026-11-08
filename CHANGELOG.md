# Changelog

## 1.5.0 — 2026-11-08

The first release with a web panel. 182 commits since `1.0.0-beta.1`.

### The web panel — live at <https://kasbbook.nyxon.tech>

- Sign in through the bot on Telegram, or with a username and password. A shared **demo** account (press «ورود به حساب دمو») shows the panel with ready-made data.
- **Dashboard**, **transactions** with search, filters and attachments, **reports** with CSV, a multi-currency **wallet**, **planning** (budgets, debts, loans), and a page for **holdings** priced from the gold, coin and metal feeds.
- **Every date is shown in Jalali and Gregorian side by side**; each book has its own calendar.
- Amounts are written with a separator every three digits as they are typed; recording a transaction starts on income; a category can be added right in the form, and a category name can be both an income and an expense.
- **Wallet:** a conversion shows what can be moved, fills the amount with a quarter, half, three quarters or all of it, and fills the received amount and its worth in the book's currency from today's price.
- Filters in the transaction list close when a single choice is made, and end with a confirm button.
- An **activity log** (*My account → Events*): who did what and when, from the panel, the bot or the API, with filters and a CSV report.
- *My account → Devices* lists each device once, with its last activity; signing a device out ends all of its logins.
- Installable as an app (PWA).

### Team and payroll

- **Members and shares are one page.** A member can be added **by name only**, with no account, and linked later to a real one by email, phone, Telegram id or `@username`.
- Shares: percentage, fixed amount, days, hours, points, or a fixed weight (*project*). A share can hold for **one period only** and the previous one resumes after. Taking a member off the book ends their share from that day.
- A guide on the page explains how pay is worked out, from income to payslip.
- Payslips follow their period by themselves — there is no calculate button.
- Adjustments pick a kind and a mode, can multiply days by a daily amount, and **need nobody's approval**.
- A closed period can be **opened again** by whoever may close it.
- Periods and funds are tidied, with a menu for the rarer actions.

### Platform

- Install script rewritten for readability: a banner, numbered steps, and a summary that says where to open the panel, the API docs and the bot.
- CI runs the web panel's type check, lint, tests and build next to the Python suite; every action is on its latest major version.
- Documentation, in English and Persian, covers the panel, the new payroll rules, the activity log and the device list.
- The API reports version `1.5.0`.

### Upgrading

`sudo /opt/kasbbook/scripts/update.sh`. Two migrations run: `m6c0e3f9a814` adds the placeholder flag on users, and `n7d1f4a0b925` marks every adjustment that was waiting for approval as decided (they already counted in pay).

## 1.0.0-beta.1 — 2026-08-29

First tagged release: the bot on Telegram, Bale and Rubika, the HTTP API, the double-entry ledger, payroll and treasury.
