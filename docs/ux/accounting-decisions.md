# Accounting decisions awaiting the owner

Each item is a place where the code's behaviour is a *policy*, not an
arithmetic error. Nothing listed here is changed until the owner (and, where
marked, an accountant) picks an option. Evidence and reproductions are in
[bug-ledger.md](./bug-ledger.md) and
[accounting-domain-audit.md](./accounting-domain-audit.md).

Legend — **Rule**: established bookkeeping practice. **Product**: KasbBook's
own choice. **UX**: presentation only.

## D-1 Recurring rules: what happens to the months that were missed (ACC-001/002)

`RecurringService.run_due` has no production caller, so no rule has ever been
booked, even though the README says rules are "booked when due". Wiring it into
the reminder loop is a clear fix. The open question is what happens the first
time it runs on an existing install: every active rule's `next_run_on` sits at
its start date, so the loop will try to book every firing missed since then.

| Option | Effect |
|---|---|
| A. Catch up fully, back-dated | Books every missed rent and salary, possibly months of them, including dates inside calculated or locked payroll periods. Those raise today (ACC-002); with per-rule isolation they would be skipped and reported. |
| **B. Catch up only into open periods, and tell the owner** (recommended) | Each booked firing is a real past-dated transaction. Firings that fall in closed periods are skipped and listed in one message to the book's owner, who can record them by hand. |
| C. Skip the past; start from today | Nothing back-dated, and the books silently miss what the user believed was recorded. |

Kind: **Product**. Whichever option is picked, per-rule isolation is not a
policy: one broken rule must not stop the others.

## D-2 Settling a debt: does it book money? (ACC-003)

`docs/api.md:199` and the planning router's docstring say settling "writes the
matching transaction". `DebtService.settle` only sets `settled_at`.

| Option | Effect |
|---|---|
| A. Settling books a transaction (income for owed-to-me, expense for I-owe) | Matches the docs. **Rule** concern: if the original sale or purchase was already recorded as income or expense, booking it again double-counts. Repaying a loan you *gave* is not income in accrual terms. |
| B. Settling only closes the debt; fix the docs | No double-count risk. The user records the cash movement separately, as today. |
| **C. Ask at settle time** (recommended for UX): "Record a transaction too?", defaulting to no | Explicit, and safe in both cases. |

Kind: **needs accountant review** (cash vs accrual meaning of a debt in this product).

## D-3 Percent shares over 100% (ACC-006)

Two members at 70% and 60% are accepted, and payslips total 104M against 80M
distributable.

| Option | Effect |
|---|---|
| **A. Refuse a PERCENT share that takes the book's percent total over 100** (recommended) | Matches how treasury rules already refuse over 100. Fails loudly, at the point of entry. |
| B. Scale pro rata at calculation time | Silent; the user sees different numbers than they typed. |
| C. Allow, and warn on the period screen | Overpayment stays possible. |

Kind: **Product**, with a **Rule** floor: you cannot pay out more than is
distributable without saying where the excess comes from.

## D-4 A token wallet driven negative by a later edit or delete (ACC-007)

An expense in a token the book does not hold is refused when it is recorded.
Deleting or reducing the income that funded it afterwards is not refused.

| Option | Effect |
|---|---|
| **A. Refuse the edit or delete with "this money has already been spent: …"** (recommended) | Same check as recording, applied to the after-state. |
| B. Allow, and show the negative balance in red | Records reality when a mistake is being corrected, but a wallet balance below zero is not a real position. |

Kind: **Product**.

## D-5 Losing months and negative payslips (ACC-023), unpaid slips in a locked period (ACC-025), payments after lock (ACC-009)

**Needs accountant review.** A month whose costs exceed its income gives every
member a negative net pay that reads as settled. The audit recommends:

- clamp the distributable at zero;
- carry the loss forward as a named adjustment;
- refuse to lock a period with unpaid slips;
- refuse payments into a locked period.

These are three or four separate decisions and stay untouched until reviewed.

## D-6 Approval of adjustments (ACC-022), deactivated members (ACC-027), personal-scope expenses in team books (ACC-024), payroll and conversions with no journal entry (ACC-026)

**Product / accountant review.** Documented in the domain audit, with options.
None of them is P0.

## Not policy — fixed without waiting

These are arithmetic contradictions of the code's own documented intent:

| ID | Why it is not a policy question |
|---|---|
| ACC-004 FIXED treasury rule with a category is read as a percent | The code's own comment says "a category cannot change [a flat amount]". |
| ACC-005 deactivated fund still takes its cut | Its docstring says deactivating "stops it taking any more". |
| ACC-002 one blocked rule rolls back all others | Isolation is required under every option of D-1. |
