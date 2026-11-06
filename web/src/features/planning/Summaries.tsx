import { Collapsible, StatCard } from "@nyxon/nasim";
import type {
	BookResponse,
	BudgetResponse,
	DebtResponse,
	LoanResponse,
} from "@/api/generated/model";
import { monthWindow } from "@/features/payroll/calendar";
import {
	calendarOf,
	currentPeriod,
	formatAmount,
	formatFullDate,
	formatMoney,
} from "@/shared/format";
import { t } from "@/strings";
import { daysUntil, dueText } from "./dueDates";

const Figure = ({ children }: { children: string }) => (
	<span className="text-lg sm:text-xl">{children}</span>
);

/** What all the ceilings add up to this month, how much is spent and how much a day is left to spend. */
export function BudgetsSummary({ book, rows }: { book: BookResponse; rows: BudgetResponse[] }) {
	if (rows.length === 0) return null;
	const cal = calendarOf(book.calendar);
	const end = monthWindow(currentPeriod(cal), cal).ends_on;
	const daysLeft = Math.max(1, daysUntil(end) + 1);
	// A ceiling on all expenses already contains the ceilings on single categories, so when there is
	// one it is the figure; otherwise the categories add up. Income ceilings are not spending.
	const overall = rows.find((row) => row.kind === "flow" && row.label === t.common.expense);
	const counted = overall ? [overall] : rows.filter((row) => row.kind !== "flow");
	const sum = (pick: (row: BudgetResponse) => string) =>
		counted.reduce((total, row) => total + Number(pick(row)), 0);
	const limit = sum((row) => row.limit);
	const spent = sum((row) => row.spent);
	const left = Math.max(0, limit - spent);
	const over = rows.some((row) => row.percent_used >= 100);
	const near = rows.some((row) => row.percent_used >= 80 && row.percent_used < 100);
	return (
		<div className="mb-4 flex flex-col gap-3">
			<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard
					label={t.plan.budgetTotal}
					value={<Figure>{formatMoney(String(limit), book.currency)}</Figure>}
				/>
				<StatCard
					label={t.plan.budgetSpent}
					value={<Figure>{formatMoney(String(spent), book.currency)}</Figure>}
				/>
				<StatCard
					label={t.plan.budgetLeft}
					value={<Figure>{formatMoney(String(left), book.currency)}</Figure>}
				/>
				<StatCard
					label={`${formatAmount(daysLeft)} ${t.plan.daysLeft}`}
					value={
						<Figure>{`${formatMoney(String(Math.round(left / daysLeft)), book.currency)}`}</Figure>
					}
					hint={t.plan.perDay}
				/>
			</div>
			<p className={`text-sm ${over ? "text-danger" : near ? "text-warning" : "text-muted"}`}>
				{over ? t.plan.overBudget : near ? t.plan.nearBudget : t.plan.onTrack}
			</p>
		</div>
	);
}

/** The open claims and debts, and how many have passed their due date. */
export function DebtsSummary({ book, rows }: { book: BookResponse; rows: DebtResponse[] }) {
	const open = rows.filter((row) => !row.is_settled);
	if (open.length === 0) return null;
	const left = (row: DebtResponse) => Number(row.remaining ?? row.amount);
	const mine = (row: DebtResponse) =>
		row.direction === "owed_to_me" || row.direction === "receivable";
	const receivable = open.filter(mine).reduce((total, row) => total + left(row), 0);
	const payable = open.filter((row) => !mine(row)).reduce((total, row) => total + left(row), 0);
	const overdue = open.filter((row) => row.due_on && daysUntil(row.due_on) < 0).length;
	return (
		<div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
			<StatCard
				label={t.plan.receivable}
				value={<Figure>{formatMoney(String(receivable), book.currency)}</Figure>}
			/>
			<StatCard
				label={t.plan.payable}
				value={<Figure>{formatMoney(String(payable), book.currency)}</Figure>}
			/>
			<StatCard label={t.plan.overdue} value={<Figure>{formatAmount(overdue)}</Figure>} />
		</div>
	);
}

/** What is still owed across the loans, what they ask each period, and the closest due date. */
export function LoansSummary({ book, rows }: { book: BookResponse; rows: LoanResponse[] }) {
	const open = rows.filter((row) => row.paid_count < row.installment_count);
	if (open.length === 0) return null;
	const left = open.reduce((total, row) => total + Number(row.remaining), 0);
	const perPeriod = open.reduce((total, row) => total + Number(row.installment_amount), 0);
	const next = open
		.map((row) => row.next_due_on)
		.filter((day): day is string => Boolean(day))
		.sort()[0];
	return (
		<div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
			<StatCard
				label={t.plan.loansLeft}
				value={<Figure>{formatMoney(String(left), book.currency)}</Figure>}
			/>
			<StatCard
				label={t.plan.perPeriod}
				value={<Figure>{formatMoney(String(perPeriod), book.currency)}</Figure>}
			/>
			<StatCard
				label={t.plan.nextInstallment}
				value={<Figure>{next ? formatFullDate(next) : "—"}</Figure>}
				hint={next ? dueText(next) : undefined}
			/>
		</div>
	);
}

/** Every instalment of a loan with its due date; the ones already paid are ticked. */
export function LoanSchedule({ loan }: { loan: LoanResponse }) {
	const dates = loan.due_dates ?? [];
	if (dates.length === 0) return null;
	return (
		<Collapsible title={t.plan.schedule} description={t.plan.scheduleHint}>
			<ol className="flex flex-col gap-1 text-sm">
				{dates.map((day, index) => {
					const paid = index < loan.paid_count;
					return (
						<li
							key={day}
							className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2 ${paid ? "bg-success-soft text-muted" : ""}`}
						>
							<span className="flex flex-col">
								<b className="font-semibold">
									{t.plan.installmentNo} {formatAmount(index + 1)}
								</b>
								<span className="text-xs text-muted">{formatFullDate(day)}</span>
							</span>
							<span className={`whitespace-nowrap ${paid ? "text-success" : "text-muted"}`}>
								{paid ? `✓ ${t.plan.paidMark}` : dueText(day)}
							</span>
						</li>
					);
				})}
			</ol>
		</Collapsible>
	);
}
