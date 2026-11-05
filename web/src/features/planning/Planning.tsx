import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, PageSkeleton, ProgressBar, SectionCard, StatusChip, Tabs, toast } from "@nyxon/nasim";
import {
	getPlanningListBudgetsQueryKey,
	getPlanningListDebtsQueryKey,
	getPlanningListLoansQueryKey,
	usePlanningDeleteBudget,
	usePlanningDeleteDebt,
	usePlanningDeleteLoan,
	usePlanningListBudgets,
	usePlanningListDebts,
	usePlanningListLoans,
	usePlanningPayInstallment,
} from "@/api/generated/planning/planning";
import type { BookResponse, BudgetResponse, DebtResponse, LoanResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { formatAmount, formatFullDate, formatMoney } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { BudgetForm, DebtForm, LoanForm, SettleForm } from "./PlanningForms";

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

function Actions({ children }: { children: React.ReactNode }) {
	return <div className="flex flex-wrap gap-2">{children}</div>;
}

/** The button that opens a tab's "new …" form, set apart from its list. */
function AddBar({ label, onPress }: { label: string; onPress: () => void }) {
	return (
		<div className="mb-3 flex justify-end">
			<Button size="sm" onPress={onPress}>
				{label}
			</Button>
		</div>
	);
}

function Budgets({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = usePlanningListBudgets(book.id);
	const remove = usePlanningDeleteBudget();
	const [adding, setAdding] = useState(false);
	const [removing, setRemoving] = useState<BudgetResponse | null>(null);
	return (
		<>
			<AddBar label={t.planningForms.addBudget} onPress={() => setAdding(true)} />
			{isLoading ? (
				<PageSkeleton header={false} rows={3} />
			) : !data.length ? (
				<EmptyState title={t.planning.noBudgets} description={t.planningForms.emptyHint} />
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{data.map((budget) => (
						<Row key={budget.id} title={budget.label} aside={<StatusChip tone={budget.percent_used >= 100 ? "danger" : budget.percent_used >= 80 ? "warning" : "success"} label={`${formatAmount(budget.percent_used)}٪`} />}>
							<Bar label={budget.label} percent={budget.percent_used} />
							<p className="text-sm text-muted">
								{t.planning.spent} {formatMoney(budget.spent, book.currency)} · {t.planning.remaining} {formatMoney(budget.remaining, book.currency)}
							</p>
							<Actions>
								<Button size="sm" variant="ghost" onPress={() => setRemoving(budget)}>
									{t.common.delete}
								</Button>
							</Actions>
						</Row>
					))}
				</ul>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.planningForms.addBudget} size="sm">
				<BudgetForm book={book} onDone={() => setAdding(false)} />
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.planningForms.deleteBudgetTitle}
				description={t.planningForms.deleteBudgetBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, budgetId: removing.id });
						await queryClient.invalidateQueries({ queryKey: getPlanningListBudgetsQueryKey(book.id) });
						toast.success(t.planningForms.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</>
	);
}

function Debts({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = usePlanningListDebts(book.id);
	const remove = usePlanningDeleteDebt();
	const [adding, setAdding] = useState(false);
	const [settling, setSettling] = useState<DebtResponse | null>(null);
	const [removing, setRemoving] = useState<DebtResponse | null>(null);
	return (
		<>
			<AddBar label={t.planningForms.addDebt} onPress={() => setAdding(true)} />
			{isLoading ? (
				<PageSkeleton header={false} rows={3} />
			) : !data.length ? (
				<EmptyState title={t.planning.noDebts} description={t.planningForms.emptyHint} />
			) : (
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
							<Actions>
								{debt.is_settled ? null : (
									<Button size="sm" variant="secondary" onPress={() => setSettling(debt)}>
										{t.planning.settle}
									</Button>
								)}
								<Button size="sm" variant="ghost" onPress={() => setRemoving(debt)}>
									{t.common.delete}
								</Button>
							</Actions>
						</Row>
					))}
				</ul>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.planningForms.addDebt} size="sm">
				<DebtForm book={book} onDone={() => setAdding(false)} />
			</Modal>
			<Modal isOpen={settling !== null} onOpenChange={(open) => !open && setSettling(null)} title={settling ? `${t.planningForms.settleTitle} ${settling.person}` : t.planning.settle} size="sm">
				{settling ? <SettleForm key={settling.id} book={book} debt={settling} onDone={() => setSettling(null)} /> : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.planningForms.deleteDebtTitle}
				description={t.planningForms.deleteDebtBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, debtId: removing.id });
						await queryClient.invalidateQueries({ queryKey: getPlanningListDebtsQueryKey(book.id) });
						toast.success(t.planningForms.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</>
	);
}

function Loans({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = usePlanningListLoans(book.id);
	const pay = usePlanningPayInstallment();
	const remove = usePlanningDeleteLoan();
	const [adding, setAdding] = useState(false);
	const [paying, setPaying] = useState<LoanResponse | null>(null);
	const [removing, setRemoving] = useState<LoanResponse | null>(null);
	return (
		<>
			<AddBar label={t.planningForms.addLoan} onPress={() => setAdding(true)} />
			{isLoading ? (
				<PageSkeleton header={false} rows={3} />
			) : !data.length ? (
				<EmptyState title={t.planning.noLoans} description={t.planningForms.emptyHint} />
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{data.map((loan) => {
						const finished = loan.paid_count >= loan.installment_count;
						return (
							<Row key={loan.id} title={loan.title} aside={<span className="text-sm text-muted">{formatAmount(loan.paid_count)} / {formatAmount(loan.installment_count)}</span>}>
								<Bar label={loan.title} percent={loan.percent_paid} />
								<p className="text-sm text-muted">
									{t.planning.installment} {formatMoney(loan.installment_amount, book.currency)} · {t.planning.remaining} {formatMoney(loan.remaining, book.currency)}
								</p>
								{loan.next_due_on ? <p className="text-sm text-muted">{t.planning.next} {formatFullDate(loan.next_due_on)}</p> : null}
								<Actions>
									{finished ? (
										<StatusChip tone="success" label={t.planningForms.allPaid} />
									) : (
										<Button size="sm" variant="secondary" onPress={() => setPaying(loan)}>
											{t.planningForms.payInstallment}
										</Button>
									)}
									<Button size="sm" variant="ghost" onPress={() => setRemoving(loan)}>
										{t.common.delete}
									</Button>
								</Actions>
							</Row>
						);
					})}
				</ul>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.planningForms.addLoan} size="sm">
				<LoanForm book={book} onDone={() => setAdding(false)} />
			</Modal>
			<ConfirmDialog
				isOpen={paying !== null}
				onOpenChange={(open) => !open && setPaying(null)}
				title={t.planningForms.payTitle}
				description={paying ? `${t.planningForms.payBody} (${formatMoney(paying.installment_amount, book.currency)})` : undefined}
				confirmLabel={t.planningForms.payConfirm}
				onConfirm={async () => {
					if (!paying) return;
					try {
						// Sending the count we saw makes a double tap or a retry a refusal, not a second payment.
						await pay.mutateAsync({ bookId: book.id, loanId: paying.id, params: { expected_paid_count: paying.paid_count } });
						await Promise.all([queryClient.invalidateQueries({ queryKey: getPlanningListLoansQueryKey(book.id) }), refreshMoney(queryClient, book.id)]);
						toast.success(t.planningForms.paid);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.planningForms.deleteLoanTitle}
				description={t.planningForms.deleteLoanBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, loanId: removing.id });
						await queryClient.invalidateQueries({ queryKey: getPlanningListLoansQueryKey(book.id) });
						toast.success(t.planningForms.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</>
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
