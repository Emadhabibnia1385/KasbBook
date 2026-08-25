# Double-entry

Every transaction writes two things: a `Transaction` row, which is what a
person sees, and a balanced `JournalEntry`, which is what makes the books
provable.

## Why bother

A single-entry ledger is a list. You can ask it "what did I spend on rent?" and
it answers, but you cannot ask it "does this add up?" — there is nothing to
check against.

Double-entry gives you that question. If debits and credits do not agree,
something is wrong, and you know before a customer does.

## The shape

```
Transaction                     JournalEntry
  flow: income                    ├── JournalLine  debit  1000 (cash)    250,000
  category: فروش                  └── JournalLine  credit 4000 (income)  250,000
  amount: 250,000
```

An expense is the mirror:

```
Transaction                     JournalEntry
  flow: expense                   ├── JournalLine  debit  5000 (expense)  2,000,000
  category: اجاره                 └── JournalLine  credit 1000 (cash)     2,000,000
```

## The chart of accounts

Created on demand, the first time a book records anything:

| Code | Name | Type |
|---|---|---|
| 1000 | نقد و بانک | asset |
| 1900 | خزانه | asset |
| 2000 | بدهی | liability |
| 3000 | سرمایه | equity |
| 4000 | درآمد | income |
| 5000 | هزینه | expense |

Six accounts is the minimum a book needs to record anything at all. It is
deliberately not configurable: a shopkeeper does not want to design a chart of
accounts, and a system that lets them is a system that lets them design a
broken one.

## The invariant, and where it is checked

```python
debit, credit = await ledger.trial_balance(book_id)
assert debit == credit
```

That assertion is not decoration. It runs after recording, after deleting a
transaction, after settling a debt, and after paying a loan instalment —
because those are the four places where a partial write would leave the books
unprovable.

`BalanceError` is raised by `post_entry` if lines are ever handed to it that do
not agree. It has never fired in production, which is the point: it exists so
that the day something does go wrong, it fails loudly at the write instead of
quietly at the report.

## Money never touches a float

`shared/money.py` defines `Money`, a `TypeDecorator`:

| | |
|---|---|
| PostgreSQL | `NUMERIC(28, 4)` — native exact decimal |
| SQLite | `String(40)` — the text of the Decimal, converted back on read |

Four decimal places, because a conversion rate needs them even when rials do
not. Twenty-eight digits, because inflation is a thing.

At the HTTP boundary money is a **string**, not a JSON number. JSON's only
numeric type is a float; `12500000.15` becomes `12500000.149999999` and stays
that way.

## Multi-currency

A transaction in a foreign currency stores three things:

```
original_amount    the number the person typed
original_currency  what they typed it in
conversion_rate    the rate at the moment they typed it
converted_amount   original × rate, in the book's base currency
```

The rate is captured once and **never re-applied**. Re-reading a transaction
from last year shows what it was worth then, not what today's rate would make
it. Reports sum `converted_amount`, so a book with five currencies in it still
adds up.

## Deleting a transaction

Deletes the journal entry with it, in the same unit of work. The trial balance
is asserted afterwards in the tests, because "delete the row and forget the
entry" is exactly the bug that would make a book unprovable — and it would not
show up until somebody reconciled.

## Where the entries are *not* written

Treasury allocations and payslips are records of a payroll decision, not
transactions. They are snapshotted onto the period rather than posted to the
ledger — a payslip is a statement of what someone is owed, and the money moving
is a separate, later fact.

The money that actually moves — a debt settled, a loan instalment paid, a
recurring rule firing — goes through `LedgerService.record()` like anything
else, and gets its journal entry like anything else.
