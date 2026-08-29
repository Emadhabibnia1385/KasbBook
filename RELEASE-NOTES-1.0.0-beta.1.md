The first release of KasbBook — bookkeeping for a small business, in the
messenger that business already uses.

Type `فروش ۲۵۰ک` and it is recorded. The same account works from Telegram,
Bale and Rubika, and over an HTTP API. Money is exact, the calendar is Jalali,
and every transaction has a balanced double-entry journal behind it.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Emadhabibnia1385/KasbBook/main/scripts/install.sh | sudo bash
```

Debian or Ubuntu, Python 3.11+, Docker for the datastores. It asks for one
thing — a bot token — and generates everything else, because a signing key
somebody types is a signing key somebody can guess. Running it twice is safe.

## What is in it

**Books** — personal, business, team and organization, all under one account.
A messenger id is never the account; it is a pointer to one, so losing a
Telegram account does not lose the books.

**A double-entry ledger.** Every transaction writes a balanced journal entry,
and `trial_balance()` is asserted in the tests after recording, deleting,
settling a debt and paying an instalment.

**Multi-currency** with the rate frozen at the moment of the transaction and
never re-applied, so last year's numbers stay last year's numbers.

**Jalali reporting** by month, year, week or category, with CSV export.
Periods convert to a Gregorian range before any query: the database never sees
a Jalali value and the user never sees a Gregorian one.

**Budgets, debts, loans and recurring rules.** Rent defined once and booked
when due, catching up if the bot was down.

**Payroll and treasury** for teams — periods, member shares by percentage or
measured work, bonuses and deductions, payslips that freeze every input, staged
payment, and funds fed by rules before profit is shared.

**Accounts** — email, phone, password, sessions, and deletion. Deleting keeps
the ledger provable: books nobody else is on are destroyed, books shared with
other people must be handed over first, and an account whose records live in
someone else's book is stripped of every personal detail rather than erased.

**Three messengers** behind one adapter contract, and an HTTP API over the same
application services — so a rule cannot be enforced in one client and forgotten
in the other. Only official bot APIs; nothing reverse-engineered.

**Operations** — install, update with automatic rollback, backup, restore and
uninstall. The update script backs up first, runs the tests before touching the
schema, and puts the previous version back if the new one does not come up
clean.

## Beta, and what that means

It runs in production for its author and its tests are thorough — the suite
covers the bot, the API, the adapters and the migrations, and CI rehearses
every migration against a real PostgreSQL with rows already in the tables.

But it has not been run by many people on many books yet. Take backups;
`scripts/backup.sh` does it for you and verifies what it wrote.

Two things are worth knowing before you rely on them:

- **Bale and Rubika have not met their live APIs.** They are written from the
  published documentation and pass the same conformance suite as Telegram, but
  against mock transports. First contact with a real token may need
  adjustments.
- **Neither signs its webhooks.** Their adapters say so plainly rather than
  implying a check that is not happening; polling is the default and avoids the
  question.

[docs/roadmap.md](https://github.com/Emadhabibnia1385/KasbBook/blob/main/docs/roadmap.md)
lists what is deliberately not built, and why.

## Documentation

Thirteen pages under [docs/](https://github.com/Emadhabibnia1385/KasbBook/tree/main/docs),
in English, plus a [Persian README](https://github.com/Emadhabibnia1385/KasbBook/blob/main/README.fa.md).
The one worth reading first if something behaves oddly is
[troubleshooting.md](https://github.com/Emadhabibnia1385/KasbBook/blob/main/docs/troubleshooting.md)
— every entry in it is a failure that actually happened here.

## Note on the version

This is the second generation of the code and the first thing ever released, so
it is version 1.
