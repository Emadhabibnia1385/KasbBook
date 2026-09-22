# Payroll and treasury

For team and organization books, where profit is shared between people. A
personal or business book does not offer it — splitting profit between one
person is not a feature.

## The idea

```
income
  − direct costs
  ─────────────
  = net profit
  − treasury               funds the team keeps first
  ─────────────
  = distributable          split by each member's share
  ± adjustments            bonuses and deductions
  ─────────────
  = net pay                per person, paid in one or several transfers
```

Every line of that is shown on the period screen. Somebody about to be paid a
share of a number should be able to see how the number was reached.

A treasury rule may name a category, and is then charged on that category's
income alone — which is how one kind of income can be set aside in full while
everything else is divided normally. A category carries one flow, so gross and
net agree for such a rule.

### Who carries the costs

The chain above is one of two arrangements, and a book chooses between them
with `cost_policy`:

| policy | distributable | the treasury keeps |
|---|---|---|
| `before_split` (default) | income − costs − treasury | its cut |
| `from_treasury` | income − treasury | its cut − costs |

`before_split` is the conventional reading: costs come off first and a bad
month is felt by everyone. `from_treasury` is what a partnership that pays its
people off the top does — members take their share of gross income and every
cost is drawn from the treasury's own cut.

Under `from_treasury` the treasury can end a period negative, when costs
exceed the cut. That is the honest reading of the month, so it is reported
rather than clamped.

Changing the policy steers the next calculation only. A period that has already
been calculated keeps its figures frozen on its payslips, and the treasury's
allocation for a period is replaced — not added to — when it is recalculated.

It is set with `PUT /books/{id}/cost-policy`, or in the bot from the treasury
screen. Both need `MANAGE_TREASURY`, because the answer moves money between
the treasury and the people.

A payment can be taken back while its period is still open, which puts the
payslip and the wallet back where they were. A figure typed wrongly, or against
the wrong person, was otherwise permanent.

A member can be paid in any currency the book holds. The payment carries the
rate it was made at, and the payslip counts it in its own currency — forty
tethers is what forty tethers were worth, not forty toman.

## Periods

Neither issuing a payslip nor paying one closes a period. Income that arrives a
day late and the bill that comes after the members were paid belong to that
month, and refusing them only pushed the truth into the wrong one. Only a
period's status closes it — see the lifecycle below.

A payslip is a snapshot, so an entry recorded after it makes it stale. The
period screen says so, and offers to recalculate. Recalculating updates each
payslip **in place**: every payment made against it stays, and what moves is
what is still owed. That can go either way:

- income added after payment leaves the difference **owed** to the member;
- a cost under `before_split`, or an income moved out, can leave a payslip
  **below what was paid**. That is shown as `overpaid`, never folded into
  "settled"; a deduction in the next period is the usual way to take it back.

A payment in a token can land a fraction past the payslip, by up to one unit of
that token, because the exact figure is not reachable in it. That is how a
token settles, and it is not reported as an overpayment.

A calculation can be discarded as long as the period has paid nobody, which
releases both the payslips and the treasury allocation. Once someone has been
paid it is refused — payments cascade with their payslip — and recalculating is
what such a period needs instead.

A period's window can be moved and its name changed, paid or not. Moving the
window changes which transactions the period divides, so any payslips are
recalculated rather than left stale, keeping their payments. Two periods in a
book may never cover the same day: `compute_distribution` sums by date, so an
overlap divides one day's income twice.


A period is the window everything is measured over — normally a Jalali month.

```
open → calculating → awaiting_approval → approved → paid → locked
```

Only those moves are allowed (`PERIOD_TRANSITIONS`). Anything else is a bug,
not a decision.

A **locked** period refuses edits. Corrections go in a later period, which is
how accounting works — you do not go back and change last month once people
have been paid on it.

## Treasury

Money set aside before anyone is paid: an emergency reserve, a tax set-aside, a
development fund.

A **fund** is a named pot. A **rule** feeds it:

| Basis | Meaning |
|---|---|
| `gross_percent` | a percentage of income, before costs |
| `net_percent` | a percentage of profit, after costs |
| `fixed` | a flat amount each period |

Rules have an effective date range, so "we started taking 10% in Mordad" is
expressible and last year's periods are unaffected.

### Two rules about deletion

**A fund that has taken money cannot be deleted.** A paid period would be left
pointing at nothing. Deactivating it stops it taking any more, which is what
"remove" actually means once money has moved.

**A rule can always be deleted.** What past periods took is snapshotted onto
those periods as `TreasuryAllocation` rows, never recomputed — so removing the
rule cannot rewrite history.

That asymmetry is the whole design in miniature: the *decision* is mutable, the
*record of what was decided* is not.

## Shares

A `ShareRule` per member, per book, with an effective date:

| Basis | Distributable is split by |
|---|---|
| `percent` | a percentage each |
| `fixed` | a fixed amount each |
| `hours` · `days` · `points` | recorded performance for the period, times the rule's weight |
| `project` | project contribution |

Where two rules overlap, the one that started later wins.

Setting a share **closes** the previous rule rather than editing it: the old
one gets an end date the day before the new one starts, and both stay readable.
That is what stops a raise agreed today from silently rewriting what the same
person was paid last spring.

Clearing a share **closes** it the same way, the day before today, rather than
switching it off. Switched off, the rule vanished from history too, and a past
period recalculated afterwards — which a paid period can be — found no share
for the member and read every payment to them as an overpayment. A rule that
had not started yet is withdrawn outright.

A member with no share on a period's last day gets no payslip. If they already
had one and were paid on it, it stays at nothing rather than being deleted with
its payments.

**Nobody is paid until they have a share.** A calculation with no share rules
produces no payslips — so the bot refuses to run one and points at the shares
screen instead, rather than returning an empty result that looks like success.

## Performance

The three measured bases need something to measure. `⏱ کارکرد` on the period
screen records hours, days or points per member, and only lists the people
whose share is actually paid by measure — asking for hours from someone on a
flat percentage is a question with no use for the answer.

One record per member per period, so correcting a figure changes it rather than
failing on the unique constraint.

Weight-based shares split what is left **after** the fixed and percentage
claims are settled. Two people on `hours` with weight 1, at 120 and 40 hours,
take three quarters and one quarter of the remainder.

## Adjustments

A bonus or a deduction on one person's pay, before the calculation.

The value is **signed** — negative is a deduction. One field rather than a
value plus a direction, because two fields can disagree and a sign cannot.

In the bot you type `۲م` for a bonus or `-۵۰۰ک` for a deduction, and the kind
(`bonus` / `penalty`) follows from the sign rather than being a second question
asking the same thing.

Adjustments are approved separately from being recorded, so "the manager
proposed it, the owner approved it" is a real distinction.

## Calculating

`calculate()` produces one `Payslip` per member and **freezes every input onto
it**:

```
distributable_snapshot   what there was to share
share_basis_snapshot     how it was split
share_value_snapshot     this person's share, as it was then
base_share               the resulting amount
adjustments_total        what was added or taken
net_pay                  what is owed
```

Reading last year's payslip shows what was decided then, not what today's rules
would produce.

Recalculating **updates** the previous run rather than doubling it: one payslip
per member, the same payslip each time, so its payments stay with it. Treasury
allocations for the period are replaced alongside, once, as fact.

## Paying

Staged, because that is the norm: a share is often paid across several
transfers.

```
GET  payslip → net_pay 40,000,000, paid 15,000,000, outstanding 25,000,000, overpaid 0
```

`outstanding` goes negative when a recalculation leaves the payslip below what
was paid; `overpaid` is that figure less a token's settling fraction, and is
the one to show a person.

The bot offers "pay the rest" as one press — the common case by a long way, and
typing the number again is a chance to mistype it — plus a partial-payment
option.

Each `Payment` records amount, date, currency, rate and an optional reference.

## Who can see what

| Permission | |
|---|---|
| `MANAGE_PAYROLL` | open periods, calculate, record payments, manage funds |
| `VIEW_OTHERS_PAY` | see everyone's payslips |
| `LOCK_PERIOD` | close a period; owner only |

Without `VIEW_OTHERS_PAY`, `payslips()` returns only your own. That is enforced
in the service, so it holds for the bot and the API alike.

## From the bot

```
book menu → 👥 حقوق و سهم
              → ➕ دورهٔ <month>          open a period
              → the arithmetic, in full
              → 🧮 محاسبهٔ فیش‌ها          calculate
              → 💵 فیش‌ها                  payslips
                  → 💵 پرداخت کامل        or a partial amount
              → ➕ کسر/اضافه              adjustments
              → 🏦 خزانه                  funds and rules
```

## One parsing detail worth knowing

A treasury percentage is parsed as a **plain number**, not through the amount
parser. The amount parser reads `۱۰م` as ten million — which would have made a
rule for ten million percent. Percentages accept digits only.
