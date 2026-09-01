<div class="kb-hero" markdown>

<span class="kb-hero__badge">● <b>1.0.0-beta.1</b> · Python 3.12 · FastAPI · MIT</span>

# Keep the books<br><span class="kb-accent">where the business already talks.</span>

<p class="kb-hero__sub">
Type <code>فروش ۲۵۰ک</code> and it is recorded. One account across Telegram,
Bale and Rubika, and an HTTP API over the same rules. Money is exact, the
calendar is Jalali, and every transaction has a balanced double-entry journal
behind it.
</p>

<div class="kb-hero__actions" markdown>
[Get started](getting-started.md){ .md-button .md-button--primary }
[Live API reference](https://kasbbook.nyxon.tech/docs){ .md-button }
</div>

</div>

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Emadhabibnia1385/KasbBook/main/scripts/install.sh | sudo bash
```

Debian or Ubuntu, Python 3.11+, Docker for the datastores. It asks for one
thing — a bot token — and generates everything else, because a signing key
somebody types is a signing key somebody can guess. Running it twice is safe.

!!! warning "This is a beta"

    It runs in production for its author and its tests are thorough, but it has
    not been run by many people on many books yet. Take backups —
    `scripts/backup.sh` does it for you and verifies what it wrote — and read
    the [roadmap](roadmap.md) for what is deliberately not built.

## What it does

<div class="grid cards" markdown>

-   __Books and a real ledger__

    Personal, business, team and organization books under one account. Every
    transaction writes a balanced journal entry, so the books can be *proved*,
    not just read. See [double-entry](double-entry.md).

-   __Money that stays exact__

    `Decimal` everywhere, `NUMERIC(28,4)` in PostgreSQL, and a **string** over
    HTTP — because JSON's only numeric type is a float and `12500000.15` does
    not survive that round trip.

-   __Jalali, properly__

    A period like `1403-05` becomes a Gregorian range *before* any query runs.
    The database never sees a Jalali value and the reader never sees a
    Gregorian one.

-   __One account, many messengers__

    A messenger id is never the account — it points at one. Lose a Telegram
    account and the books stay. See [the data model](data-model.md).

-   __Payroll for teams__

    Periods, member shares, recorded work, bonuses and deductions, payslips
    that freeze every input, staged payment, and a treasury taken before profit
    is shared. See [payroll](payroll.md).

-   __An API over the same rules__

    Not a second implementation. Both the bot and the API call the same
    services, so a rule cannot be enforced in one and forgotten in the other.
    See [the API](api.md).

</div>

## How it is put together

```
  Telegram          Bale            Rubika
      │               │               │
      ▼               ▼               ▼
 ┌─────────────────────────────────────────┐
 │  adapters/     translate payloads       │   no database, no rules
 └───────────────────┬─────────────────────┘
                     ▼
 ┌─────────────────────────────────────────┐
 │  bot/          screens + routing        │   no provider names
 └───────────────────┬─────────────────────┘
                     │
 ┌───────────────────┼─────────────────────┐
 │  api/  ───────────┤                     │   parse, call, translate errors
 └───────────────────┼─────────────────────┘
                     ▼
 ┌─────────────────────────────────────────┐
 │  modules/*/service.py                   │   every rule, exactly once
 └───────────────────┬─────────────────────┘
                     ▼
        PostgreSQL   ·   Redis   ·   Alembic
```

Two clients, one set of rules. [Why the seams are where they are](architecture.md).

## If something looks wrong

[Troubleshooting](troubleshooting.md) is the page to read first. Every entry in
it is a failure that actually happened in this project, written as symptom →
cause → fix — because in almost every one of them, the symptom pointed
somewhere else.

## Where to go next

| | |
|---|---|
| Install it and record something | [Getting started](getting-started.md) |
| Understand the shape | [Architecture](architecture.md) |
| Call it from a script | [The API](api.md) |
| Run it for other people | [Operations](operations.md) · [Security](security.md) |
| Change it | [Development](development.md) |

Persian readers: the project's [README is also in Persian](https://github.com/Emadhabibnia1385/KasbBook/blob/main/README.fa.md).
