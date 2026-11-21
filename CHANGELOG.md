# Changelog

## Unreleased

- **Paying a loan installment on the web asks which account it comes from**, starting on the book's default, like every other form that moves money.
- **Every place that moves money can name the account.** Recurring rules keep the account they were made with (the book's default at that moment unless one is chosen) and record each date through it; paying a loan installment, buying or selling an asset, and paying into or being paid by a fund take `bank_account_id` too (left out is the book's default, null is none). The cash of an asset, a fund or a loan's principal now counts in the account's balance and in its reconciliation. An account used by a rule or a movement is switched off, never removed.
- **Bank accounts in the bot.** *🏦 حساب‌های بانکی* in a book's menu lists the accounts with this book's share and lets you make one the default; a transaction shows its account and has a button to move it to another or to none, and a quick entry says which account it went through.
- **Transfers between accounts.** Money moved from one of a book's bank accounts to another is recorded as a transfer, not as income or an expense, so no report, budget or member share moves; both balances change, and the books stay balanced. A transfer can be edited or removed; an account that has one is switched off, not deleted. Both accounts must be in the same book (moving money between two books is not this).
- **Put old transactions on an account.** For a book that predates accounts, `POST /books/{id}/bank-accounts/{bank}/assign` moves every transaction that names no account (in the book's own currency, optionally within a date range) onto it, rebuilding each entry through the ledger; closed periods are left as they were and counted.
- **Filter transactions by bank account** in the panel and in the API (`bank_account_id`, repeatable).
- **Bank accounts, shared between books.** Add an account with a bank and a holder (both required), and optionally a display name, card number, account number, Sheba and an opening balance; the card and Sheba are checked, Persian digits are read. One account can be used by several books: its balance is one, and it is always the opening balance plus what every book's transactions put in or took out — never stored, and checked two independent ways by `GET /bank-accounts/{id}/reconciliation`. Each book picks its own default account; recording a transaction chooses one (`bank_account_id`, left out means the default, null means none), and it can be changed later. A member sees only their own book's share and masked numbers; the owner sees every book's share. Reports and *Manage* chart each account's balance and how much of it belongs to which book.
- **The top bar's prices start as the dollar and 18-carat gold** instead of dollar, gold and Tether; anyone who already picked their own prices keeps them.
- **Fixed «Something went wrong — Cell count must match column count»** on the transactions page: switching between all books and one book (the book column appears or goes) no longer breaks the table.
- **Transactions pages keep a day together.** A day's entries are never split across two pages, and a day bigger than the page is a page of its own. Under the list, the page and previous/next sit at the right and a box at the left sets how many transactions a page aims for (up to ten thousand, remembered on that browser) — enough to see everything on one page — or pick 10, 20, 30, 50, 75 or 100 from a menu beside it.
- **Sign up on the web** with a username and the password typed twice; the panel's sign-in page has the form.
- **Connecting Telegram merges accounts.** If that Telegram already had an account, the bot asks first and then folds it into the web account: books, memberships, records, payslips. The web account keeps its username and password.

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
