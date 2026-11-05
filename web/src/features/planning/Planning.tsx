import { useQueryClient } from "@tanstack/react-query";
import { Button, EmptyState, ErrorState, PageHeader, PageSkeleton, ProgressBar, SectionCard, StatusChip, Tabs, toast } from "@nyxon/nasim";
import {
	getPlanningListDebtsQueryKey,
	usePlanningListBudgets,
	usePlanningListDebts,
	usePlanningListLoans,
	usePlanningSettleDebt,
} from "@/api/generated/planning/planning";
import type { BookResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { formatAmount, formatFullDate, formatMoney } from "@/shared/format";
import { t } from "@/strings";

function Bar({ label, percent }: { label: string; percent: number }) {
	return (
		<ProgressBar aria-label={label} value={Math.min(100, percent)} className="w-full">
			<ProgressBar.Track>
				<ProgressBar.Fill />
			</ProgressBar.Track>
		</ProgressBar>
	);
}

function Row({ title, aside, children }: { title: string; aside?: React.ReactNode; children?: React.ReactNode }) {
	return (
		<li className="flex flex-col gap-2 rounded-2xl border border-border bg-surface p-4">
			<div className="flex items-center justify-between gap-3">
				<span className="font-medium">{title}</span>
				{aside}
			</div>
			{children}
		</li>
	);
}

function Budgets({ book }: { book: BookResponse }) {
	const { data = [], isLoading } = usePlanningListBudgets(book.id);
	if (isLoading) return <PageSkeleton header={false} rows={3} />;
	if (!data.length) return <EmptyState title={t.planning.noBudgets} description={t.planning.fromBot} />;
	return (
		<ul className="grid gap-3 md:grid-cols-2">
			{data.map((budget) => (
				<Row key={budget.id} title={budget.label} aside={<StatusChip tone={budget.percent_used >= 100 ? "danger" : budget.percent_used >= 80 ? "warning" : "success"} label={`${formatAmount(budget.percent_used)}٪`} />}>
					<Bar label={budget.label} percent={budget.percent_used} />
					<p className="text-sm text-muted">
						{t.planning.spent} {formatMoney(budget.spent, book.currency)} · {t.planning.remaining} {formatMoney(budget.remaining, book.currency)}
					</p>
				</Row>
			))}
		</ul>
	);
}

function Debts({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = usePlanningListDebts(book.id);
	const settle = usePlanningSettleDebt();
	if (isLoading) return <PageSkeleton header={false} rows={3} />;
	if (!data.length) return <EmptyState title={t.planning.noDebts} description={t.planning.fromBot} />;
	return (
		<ul className="grid gap-3 md:grid-cols-2">
			{data.map((debt) => (
				<Row
					key={debt.id}
					title={debt.person}
					aside={<StatusChip tone={debt.is_settled ? "success" : "warning"} label={debt.is_settled ? t.planning.settled : debt.direction === "owed_to_me" || debt.direction === "receivable" ? t.planning.toReceive : t.planning.toPay} />}
				>
					<p className="text-lg font-semibold">{formatMoney(debt.amount, book.currency)}</p>
					{debt.due_on ? <p className="text-sm text-muted">{t.planning.due} {formatFullDate(debt.due_on)}</p> : null}
					{debt.note ? <p className="text-sm text-muted">{debt.note}</p> : null}
					{debt.is_settled ? null : (
						<Button
							size="sm"
							variant="secondary"
							isPending={settle.isPending}
							onPress={async () => {
								try {
									await settle.mutateAsync({ bookId: book.id, debtId: debt.id });
									await queryClient.invalidateQueries({ queryKey: getPlanningListDebtsQueryKey(book.id) });
									toast.success(t.planning.settledToast);
								} catch (error) {
									toast.danger(error instanceof Error ? error.message : t.errors.unknown);
								}
							}}
						>
							{t.planning.settle}
						</Button>
					)}
				</Row>
			))}
		</ul>
	);
}

function Loans({ book }: { book: BookResponse }) {
	const { data = [], isLoading } = usePlanningListLoans(book.id);
	if (isLoading) return <PageSkeleton header={false} rows={3} />;
	if (!data.length) return <EmptyState title={t.planning.noLoans} description={t.planning.fromBot} />;
	return (
		<ul className="grid gap-3 md:grid-cols-2">
			{data.map((loan) => (
				<Row key={loan.id} title={loan.title} aside={<span className="text-sm text-muted">{formatAmount(loan.paid_count)} / {formatAmount(loan.installment_count)}</span>}>
					<Bar label={loan.title} percent={loan.percent_paid} />
					<p className="text-sm text-muted">
						{t.planning.installment} {formatMoney(loan.installment_amount, book.currency)} · {t.planning.remaining} {formatMoney(loan.remaining, book.currency)}
					</p>
					{loan.next_due_on ? <p className="text-sm text-muted">{t.planning.next} {formatFullDate(loan.next_due_on)}</p> : null}
				</Row>
			))}
		</ul>
	);
}

export function Planning() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.planning} description={book.name} />
			<SectionCard title={t.planning.title}>
				<Tabs
					label={t.planning.title}
					defaultSelectedKey="budgets"
					items={[
						{ id: "budgets", label: t.planning.budgets, content: <Budgets book={book} /> },
						{ id: "debts", label: t.planning.debts, content: <Debts book={book} /> },
						{ id: "loans", label: t.planning.loans, content: <Loans book={book} /> },
					]}
				/>
			</SectionCard>
		</div>
	);
}
