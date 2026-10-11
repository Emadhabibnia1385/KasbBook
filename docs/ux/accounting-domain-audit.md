# Accounting domain audit

Branch `ux-platform-redesign`, 2026-10-11 (Jalali 1405-07-19). Audit only: no product code or existing test changed. Findings with reproductions are in [bug-ledger.md](./bug-ledger.md) (ACC-xxx / ENV-xxx). Scratch tests live outside the repo, in `.../scratchpad/acct/`.

Method: traced each chain through the services (`ledger`, `reports`, `exchange`, `recurring`, `debts`, `loans`, `payroll`, `treasury`), then wrote tests that assert the intended behaviour and ran them on the repo's SQLite harness. A "confirmed" item is one of those tests failing. Nothing was exercised on PostgreSQL, so concurrency items are only suspected.

## 1. Chains reviewed

Verdict key: OK = traced and probed, no defect found; issues = see ledger IDs.

### 1.1 Transaction -> journal entry -> balances / reports. Verdict: sound core, two edge defects

What holds (probed):
- `record()` posts exactly one balanced entry (cash vs income/expense, `converted_amount`); `update()` rebuilds it through `post_entry`, `delete()` cascades it away. Trial balance stayed equal in every scenario I ran, including edit of amount, edit of date across periods, delete after payments, delete of a loan-installment transaction (progress rolls back correctly).
- Sign convention: one positive amount plus a flow; negative is refused (`ValidationError`), zero or sub-unit amounts raise `BalanceError` ("moves nothing"). Journal lines are never negative.
- Reports sum `converted_amount` frozen at record time; Jalali month ranges tile with no gap or overlap in 1403-1405, and Esfand 1403 has 30 days (leap) while 1404 has 29. A transaction on 1403/12/30 lands in Esfand only.
- Retro edits: `update`/`delete` check the transaction's current date, and `update` also checks the destination date, against `_require_open_date`; any period that is not OPEN refuses.

Defects: ACC-015 (the rate is stored to 4 places but the converted amount is computed from the unrounded rate, so a no-op edit changes the amount by 0.001 and the journal with it), ACC-017 (amounts >= 10^24 escape as a raw `decimal.InvalidOperation`, so the API returns 500), ACC-018 (CSV formula cells), ACC-020 (`%` wildcard in search), ACC-028 (English strings reach users).

Note that `Money` rounds half-up to four places everywhere, which is consistent. Percent shares are quantized per member, so the sum can differ from the pie by a fraction of a rial; that is immaterial and I did not log it.

### 1.2 Conversion -> wallet balances. Verdict: arithmetic right, guards incomplete

- Balances are derived (transactions by original currency, minus payroll payments by currency, plus/minus conversions). Convert 40 of 100 USDT into 4,000,000 IRT: USDT 60, IRT 4,000,000, trial balance equal, reports unchanged (income 10,000,000 only). Converting more than held is refused. All as the constitution says.
- The "cannot spend what you do not hold" rule is enforced only at record time. Editing token income down, deleting it, or editing a token expense up drives the wallet negative (ACC-007, P1).
- A conversion accepts any implied rate (1 USDT -> 1 IRT passes); only the base value of a token-to-token swap is requested. There is no way to delete or void a mistaken conversion (ACC-028).
- A conversion creates no journal entry and no realised FX gain or loss (ACC-026, policy P-6).

### 1.3 Recurring -> booked transaction. Verdict: broken end to end

- Rules never fire: `run_due` has no production caller (ACC-001, P1). The tests that exercise it call it directly, which is why the suite is green.
- Once wired: one failing rule aborts all rules and rolls back the batch (ACC-002), and monthly recurrence drifts off the 31st and Esfand 30 for good (ACC-010).
- What is right: idempotency (running twice books once, because `next_run_on` advances), catch-up loop, the 400 cap (documented), daily/weekly stepping, each firing goes through `ledger.record` and so is balanced and period-checked.

### 1.4 Debt settlement -> real transaction. Verdict: the transaction does not exist

`DebtService.settle` stamps `settled_at` and nothing else (ACC-003, P1). `docs/api.md:199`, the route docstring and `docs/double-entry.md:114` promise a booked transaction; the module docstring says the opposite ("kept away from the ledger on purpose"). Debts have no currency, and a zero-value debt is accepted (ACC-019). See P-1 for the decision. Settling twice silently re-stamps the date; there is no un-settle.

### 1.5 Loan installment -> outstanding balance. Verdict: correct while used as designed

- Each installment is a real expense (category "قسط", scope PERSONAL) with a `LoanPayment` link. `progress()` counts links; `remaining_amount = installment x remaining_count`; deleting the transaction removes the link and restores the balance. Editing the amount of an installment transaction is refused (good).
- Defects: no upper bound on payments and no duplicate guard (ACC-011); the default payment date is the server's UTC date (ACC-012); the installment is always PERSONAL scope, which matters in team books (ACC-024, P-5).
- Outstanding is nominal (count x amount), not interest-aware or amount-aware. That is a simplification, not a bug; flagged for the accountant only if loans with unequal installments are expected.

### 1.6 Payroll period -> treasury cut -> member shares -> adjustments -> payslips -> payments / reversal. Verdict: arithmetic is right on the happy path; several guards missing

Probed and fine:
- `before_split` and `from_treasury` formulas, per-rule `max(cut, 0)`, a rule effective on the period's last day, recalculation updates payslips in place and keeps payments, allocations are replaced rather than added, the overpaid view after a retroactive delete (50,000,000 overpaid after the income was removed; documented).
- `pay()`: the payslip's own currency is forced to rate 1; tokens need a rate rounded to four places first; compares in payslip currency; a second "pay in full" is refused ("nothing left"); a USDT payment lowers the wallet and `void_payment` restores it exactly.
- Bot and API share `pay()`, `calculate()`, `void_payment()`. The bot "pay the rest" is a single press.

Defects: ACC-004 (FIXED + category read as percent, 50,000x cut), ACC-005 (deactivated fund still takes), ACC-006 (shares may exceed 100%), ACC-008 (bot cannot lock or advance a period), ACC-009 (payment into a LOCKED period), ACC-013/014 (adjustment kind vs sign; non-member), ACC-016 (allocation snapshot lies), ACC-021 (no lock on `pay`, suspected).

Policy / accountant items: ACC-022 (approval is decorative), ACC-023 (loss month), ACC-024 (scope), ACC-025 (lock with unpaid slips), ACC-026 (no journal for payouts), ACC-027 (leavers).

### 1.7 Cross-cutting

- **Calendar:** Jalali <-> Gregorian conversion and month/year ranges are correct, including leap Esfand and the Esfand/Farvardin boundary. The weak point is not the conversion but *which "today"*: `jalali.today_in(timezone)` was introduced for the UTC server, yet `date.today()` is still used in about fifteen places (ACC-012), including the bot's "new period" and share start dates. Within 00:00-03:30 Tehran time every day, and so on the first of each month, they use yesterday.
- **Bot vs API drift:** treasury categories (API only, source of ACC-004), adjustment kind (bot derives it from the sign, API trusts the caller, ACC-013), period lifecycle (API only, ACC-008). Everything else I compared shares the same service call.
- **Idempotency:** payroll "pay in full" and `calculate` are idempotent; loan installments and debt settlement are not (ACC-011, ACC-003).

## 2. Policy decisions for the owner / accountant

I have not changed any policy. Each item lists the options and what changes.

**P-1. Should settling a debt create a transaction? (ACC-003)**
- A. Yes: settle books income (owed to me) or expense (I owe) for the debt amount on the settle date, linked to the debt. *Impact:* matches the documents; settled debts then appear in reports, cash and the payroll pie (a collected receivable inflates that month's distributable, a paid supplier lowers it). Needs a currency and a guard against settling twice.
- B. No (keep the module's stated intent): debts are memoranda. *Impact:* then `docs/api.md:199`, the route docstring and `double-entry.md:114` must be corrected; money actually received or paid has to be typed separately as a transaction, and it is easy to forget.
- C. Ask on settle: "record it as a transaction?" *Impact:* flexibility, but two behaviours to document and test.

**P-2. Do unapproved adjustments count? (ACC-022)**
- A. Only approved ones count (what the docs imply). *Impact:* needs an approval step in the bot before calculating; the existing shortfall test and any book that never approves would change.
- B. All count, approval is only a flag (today). *Impact:* docs and the "approved" badge should say so; segregation of duties is then advisory.
- C. All count but the period cannot go to `approved` while any adjustment is pending. *Impact:* closes the gap without changing calculation.

**P-3. What happens in a loss month? (ACC-023)**
- A. Clamp distributable and percent/weight shares at zero; carry the loss forward. *Impact:* nobody "owes" the business; FIXED shares still need a rule (pay anyway, or cap at available).
- B. Allow negative payslips as a charge for the next period (today, but pay() refuses and nothing explains it). *Impact:* needs an explicit "carried deficit" line and a way to settle it.
- C. Refuse to calculate with a negative distributable, with a message. *Impact:* simplest, but blocks legitimate fixed-salary books.

**P-4. Must percent shares total exactly 100? (ACC-006)**
- A. Refuse a set that exceeds 100 (my recommendation regardless of the rest); allow under 100 and treat the remainder as retained.
- B. Require exactly 100 for percent-only books. *Impact:* simplest to reason about, but forces edits when a member leaves.
- C. Normalise to 100 at calculate time. *Impact:* hides data-entry mistakes.

**P-5. Which scopes enter the team distributable? (ACC-024)** Today every expense counts, including a member's PERSONAL spending and every loan installment (scope is hard-coded PERSONAL).
- A. Only `team` (and `work`) scope enter the pie; personal scope is ignored. *Impact:* the loan module should take the book's scope, and existing team books may see their pies grow.
- B. Keep all scopes (today), and stop loan payments being PERSONAL in team books.
- C. Let the owner mark which categories are "not shared costs". *Impact:* most flexible, new UI.

**P-6. Journal and FX treatment of payouts and conversions (ACC-026).** Today: payroll payments and conversions are wallet-only; the ledger's cash account does not move for payouts; a token's valuation changes between receipt and payment are not recognised; a token payment is credited to the payslip at the payment-time rate.
- A. Leave it (documented) and add a reconciliation view "ledger cash vs wallet".
- B. Post a journal entry per payout (debit payable/equity, credit cash) and per conversion with a realised gain/loss account. *Impact:* real accounting, but breaks the "six accounts, not configurable" rule and the trial-balance tests; needs the accountant.
- C. Post payouts only.

**P-7. May a period reach PAID or LOCKED while payslips are unsettled, and may payments continue after the lock? (ACC-025/009)**
- A. Refuse PAID while any payslip has `remaining > 0`; refuse payments on LOCKED. *Impact:* matches the vocabulary; blocks "lock now, finish paying later".
- B. Allow lock, but payments after lock go to the next period as a carried balance.
- C. Keep as is; treat lock as a ledger freeze only (then ACC-009 stays).

**P-8. Leavers (ACC-027).** A deactivated member keeps their share rule and gets a payslip. Options: (A) keep, and show "former member" on the slip; (B) end share rules on deactivation (`effective_to` = leave date); (C) ask the owner at removal.

**P-9. Debts: currency and partial settlement.** The model is one number in the base currency. If tokens or part-payments are expected, debts need a currency and a paid amount; otherwise state that they are single-shot memoranda.

## 3. Baseline failures (698 passed, 18 failed, 1 error, 9 skipped)

| Group | Count | Cause | Class |
|---|---|---|---|
| `tests/test_bot_payroll_treasury.py` | 10 | The data are pinned to `DAY = 2026-08-24` (1405/06/02) but the bot opens "this month" from `date.today()`. Since 23 Sep 2026 that is Mehr 1405, so the screen shows `1405/07/01..30` with 0 income. With a plugin that pins `date.today()` to the same day the whole file passes (48/48). | Time-dependent test, plus the product half logged as ACC-012. Not a regression. (ENV-001) |
| `tests/test_install_prompts.py` | 4 | `bash` is fed `C:\Users\Yekta PC\...` unquoted: backslashes are eaten and the space splits it (`bash: line 3: C:UsersYekta: No such file`). With a space-free POSIX path in copies, they pass. | Test-harness / environment (Windows). (ENV-002) |
| `tests/test_messengers.py` | 4 failed + 1 error | The 4 failures are the same quoting problem. The error is `PermissionError` creating `pytest-of-Yekta PC` under Temp; with `--basetemp` elsewhere it falls through to the quoting failure. | Environment. (ENV-002/003) |

None of the 18 indicates a product regression. The 654 other tests pass here, and nothing in the audit contradicts the suite: the defects above are mostly gaps the suite never asserted, which is the pattern the constitution warns about ("a model nothing writes to", "a method with no caller").

## 4. Suggested order

1. ACC-001 + ACC-002 (rules that never fire are the largest silent error); then ACC-003 once P-1 is decided.
2. ACC-004, ACC-005, ACC-006, ACC-007: each pays or withholds the wrong money without any error.
3. ACC-008/009 together with P-7 (period lifecycle in the bot).
4. ACC-012 (one sweep replacing `date.today()` with the book's day), then ENV-001 can drop its plugin by injecting the same clock.
5. The remaining P2 items in any order.
