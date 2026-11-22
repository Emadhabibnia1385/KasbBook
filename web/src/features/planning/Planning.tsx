import { BookRequired } from "@/features/books/BookRequired";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import {
	Button,
	Collapsible,
	ConfirmDialog,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	PageHeader,
	PageSkeleton,
	ProgressBar,
	SectionCard,
	StatusChip,
	Tabs,
	toast,
} from "@nyxon/nasim";
import {
	getPlanningListBudgetsQueryKey,
	getPlanningListDebtsQueryKey,
	getPlanningListLoansQueryKey,
	usePlanningDeleteBudget,
	usePlanningDeleteDebt,
	usePlanningDebtMovements,
	usePlanningDeleteLoan,
	usePlanningListBudgets,
	usePlanningVoidDebtMovement,
	usePlanningListDebts,
	usePlanningListLoans,
	usePlanningPayInstallment,
} from "@/api/generated/planning/planning";
import type {
	BookResponse,
	BudgetResponse,
	DebtResponse,
	LoanResponse,
} from "@/api/generated/model";
import { useBanksListForBook } from "@/api/generated/banks/banks";
import { BankField } from "@/features/banks/BankField";
import { useActiveBook } from "@/features/books/useActiveBook";
import { formatAmount, formatFullDate, formatMoney } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { BudgetForm, DebtForm, IncreaseDebtForm, LoanForm, SettleForm } from "./PlanningForms";
import { daysUntil, dueText } from "./dueDates";
import { Funds } from "@/features/capital/Capital";
import { FundForm } from "@/features/capital/CapitalForms";
import { BudgetsSummary, DebtsSummary, LoanSchedule, LoansSummary } from "./Summaries";

function Bar({ label, percent }: { label: string; percent: number }) {
	return (
		<ProgressBar aria-label={label} value={Math.min(100, percent)} className="w-full">
			<ProgressBar.Track>
				<ProgressBar.Fill />
			</ProgressBar.Track>
		</ProgressBar>
	);
}

function Row({
	title,
	aside,
	children,
}: {
	title: string;
	aside?: React.ReactNode;
	children?: React.ReactNode;
}) {
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

/** What a tab is for, in a sentence or two, above everything in it. */
function Intro({ children }: { children: string }) {
	return <p className="mb-4 text-sm leading-relaxed text-muted">{children}</p>;
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
			<Intro>{t.plan.budgetsIntro}</Intro>
			<BudgetsSummary book={book} rows={data} />
			<AddBar label={t.planningForms.addBudget} onPress={() => setAdding(true)} />
			{isLoading ? (
				<PageSkeleton header={false} rows={3} />
			) : !data.length ? (
				<EmptyState title={t.planning.noBudgets} description={t.planningForms.emptyHint} />
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{data.map((budget) => (
						<Row
							key={budget.id}
							title={budget.label}
							aside={
								<StatusChip
									tone={
										budget.percent_used >= 100
											? "danger"
											: budget.percent_used >= 80
												? "warning"
												: "success"
									}
									label={`${formatAmount(budget.percent_used)}٪`}
								/>
							}
						>
							<Bar label={budget.label} percent={budget.percent_used} />
							<p className="text-sm text-muted">
								{t.planning.spent} {formatMoney(budget.spent, book.currency)} ·{" "}
								{t.planning.remaining} {formatMoney(budget.remaining, book.currency)}
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
						await queryClient.invalidateQueries({
							queryKey: getPlanningListBudgetsQueryKey(book.id),
						});
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

/** What happened to one debt: added again, paid some, received some: each with its day and account. */
function DebtHistory({ book, debt }: { book: BookResponse; debt: DebtResponse }) {
	const queryClient = useQueryClient();
	const [open, setOpen] = useState(false);
	const movements = usePlanningDebtMovements(book.id, debt.id, { query: { enabled: open } });
	const accounts = Object.fromEntries(
		(useBanksListForBook(book.id).data ?? []).map((bank) => [bank.id, bank.title]),
	);
	const voidMovement = usePlanningVoidDebtMovement();
	const [voiding, setVoiding] = useState<string | null>(null);
	const rows = movements.data ?? [];
	// Whatever the movements do not add up to is what the debt already was before they were kept.
	const increased = rows
		.filter((row) => row.kind === "increase")
		.reduce((sum, row) => sum + Number(row.amount), 0);
	const opening = Number(debt.amount) - increased;
	return (
		<div className="flex flex-col gap-2">
			<Button size="sm" variant="ghost" onPress={() => setOpen(!open)}>
				{t.plan.history}
			</Button>
			{open ? (
				<ul className="flex flex-col divide-y divide-separator rounded-xl border border-border text-sm">
					{rows.length === 0 && !movements.isLoading ? (
						<li className="p-3 text-muted">{t.plan.historyEmpty}</li>
					) : null}
					{opening > 0 && rows.length > 0 ? (
						<li className="flex items-center justify-between gap-2 px-3 py-2 text-muted">
							<span>{t.plan.opening}</span>
							<span className="tabular-nums">{formatMoney(String(opening), book.currency)}</span>
						</li>
					) : null}
					{rows.map((row) => (
						<li
							key={row.id}
							className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
						>
							<span className="flex min-w-0 flex-col">
								<span>
									<b>{row.kind === "increase" ? t.plan.kindIncrease : t.plan.kindPayment}</b>{" "}
									<span className="tabular-nums">{formatMoney(row.amount, book.currency)}</span>
								</span>
								<span className="text-xs text-muted">
									{formatFullDate(row.occurred_on)}
									{row.bank_account_id && accounts[row.bank_account_id]
										? ` · ${accounts[row.bank_account_id]}`
										: ""}
									{row.note ? ` — ${row.note}` : ""}
								</span>
							</span>
							<Button size="sm" variant="ghost" onPress={() => setVoiding(row.id)}>
								{t.plan.voidMovement}
							</Button>
						</li>
					))}
				</ul>
			) : null}
			<ConfirmDialog
				isOpen={voiding !== null}
				onOpenChange={(isOpen) => !isOpen && setVoiding(null)}
				title={t.plan.voidTitle}
				description={t.plan.voidBody}
				confirmLabel={t.plan.voidMovement}
				tone="danger"
				onConfirm={async () => {
					if (!voiding) return;
					try {
						await voidMovement.mutateAsync({
							bookId: book.id,
							debtId: debt.id,
							movementId: voiding,
						});
						await Promise.all([
							queryClient.invalidateQueries({ queryKey: getPlanningListDebtsQueryKey(book.id) }),
							queryClient.invalidateQueries({
								predicate: (query) => String(query.queryKey[0]).includes("/debts/"),
							}),
							refreshMoney(queryClient, book.id),
						]);
						toast.success(t.plan.voided);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}

function Debts({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = usePlanningListDebts(book.id);
	const remove = usePlanningDeleteDebt();
	const [adding, setAdding] = useState(false);
	const [increasing, setIncreasing] = useState<DebtResponse | null>(null);
	const [settling, setSettling] = useState<DebtResponse | null>(null);
	const [removing, setRemoving] = useState<DebtResponse | null>(null);
	return (
		<>
			<Intro>{t.plan.debtsIntro}</Intro>
			<DebtsSummary book={book} rows={data} />
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
							aside={
								<StatusChip
									tone={debt.is_settled ? "success" : "warning"}
									label={
										debt.is_settled
											? t.planning.settled
											: debt.direction === "owed_to_me" || debt.direction === "receivable"
												? t.planning.toReceive
												: t.planning.toPay
									}
								/>
							}
						>
							<p className="text-lg font-semibold">
								{formatMoney(
									debt.is_settled ? debt.amount : (debt.remaining ?? debt.amount),
									book.currency,
								)}
							</p>
							{Number(debt.paid ?? 0) > 0 && !debt.is_settled ? (
								<>
									<Bar
										label={debt.person}
										percent={(Number(debt.paid) / Number(debt.amount)) * 100}
									/>
									<p className="text-sm text-muted">
										{t.plan.paidOf} {formatMoney(debt.paid ?? "0", book.currency)} · {t.plan.leftOf}{" "}
										{formatMoney(debt.remaining ?? debt.amount, book.currency)} ·{" "}
										{formatMoney(debt.amount, book.currency)}
									</p>
								</>
							) : null}
							{debt.due_on ? (
								<p
									className={`text-sm ${
										!debt.is_settled && daysUntil(debt.due_on) < 0 ? "text-danger" : "text-muted"
									}`}
								>
									{t.planning.due} {formatFullDate(debt.due_on)}
									{debt.is_settled ? "" : ` · ${dueText(debt.due_on)}`}
								</p>
							) : null}
							{debt.note ? <p className="text-sm text-muted">{debt.note}</p> : null}
							<Actions>
								{debt.is_settled ? null : (
									<Button size="sm" variant="secondary" onPress={() => setSettling(debt)}>
										{t.plan.partPay}
									</Button>
								)}
								<Button size="sm" variant="secondary" onPress={() => setIncreasing(debt)}>
									{t.plan.more}
								</Button>
								<Button size="sm" variant="ghost" onPress={() => setRemoving(debt)}>
									{t.common.delete}
								</Button>
							</Actions>
							<DebtHistory book={book} debt={debt} />
						</Row>
					))}
				</ul>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.planningForms.addDebt} size="sm">
				<DebtForm book={book} onDone={() => setAdding(false)} />
			</Modal>
			<Modal
				isOpen={increasing !== null}
				onOpenChange={(open) => !open && setIncreasing(null)}
				title={increasing ? `${t.plan.moreTitle} ${increasing.person}` : t.plan.more}
				size="sm"
			>
				{increasing ? (
					<IncreaseDebtForm
						key={increasing.id}
						book={book}
						debt={increasing}
						onDone={() => setIncreasing(null)}
					/>
				) : null}
			</Modal>
			<Modal
				isOpen={settling !== null}
				onOpenChange={(open) => !open && setSettling(null)}
				title={settling ? `${t.plan.partTitle} ${settling.person}` : t.plan.partPay}
				size="sm"
			>
				{settling ? (
					<SettleForm
						key={settling.id}
						book={book}
						debt={settling}
						onDone={() => setSettling(null)}
					/>
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={removing?.cash_moved ? t.plan.cashDeleteTitle : t.planningForms.deleteDebtTitle}
				description={removing?.cash_moved ? t.plan.cashDeleteBody : t.planningForms.deleteDebtBody}
				confirmLabel={removing?.cash_moved ? t.plan.cashDeleteConfirm : t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({
							bookId: book.id,
							debtId: removing.id,
							// Real cash is in its history: the person has just been told, and agreed, that it goes too.
							params: removing.cash_moved ? { undo_cash: true } : undefined,
						});
						await Promise.all([
							queryClient.invalidateQueries({ queryKey: getPlanningListDebtsQueryKey(book.id) }),
							refreshMoney(queryClient, book.id),
						]);
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
	const [addKind, setAddKind] = useState<"loan" | "fund">("loan");
	const [paying, setPaying] = useState<LoanResponse | null>(null);
	const [removing, setRemoving] = useState<LoanResponse | null>(null);
	// The account an installment is paid from: empty until the book's accounts load, then the default.
	const bankForm = useForm<{ bank_account_id: string }>({ defaultValues: { bank_account_id: "" } });
	return (
		<>
			<Intro>{t.plan.loansIntro}</Intro>
			<div className="mb-4">
				<Collapsible title={t.plan.buyTitle}>
					<p className="text-sm leading-relaxed text-muted">{t.plan.buyBody}</p>
				</Collapsible>
			</div>
			<LoansSummary book={book} rows={data} />
			<AddBar label={t.plan.addInstallment} onPress={() => setAdding(true)} />
			{isLoading ? (
				<PageSkeleton header={false} rows={3} />
			) : !data.length ? (
				<EmptyState title={t.planning.noLoans} description={t.planningForms.emptyHint} />
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{data.map((loan) => {
						const finished = loan.paid_count >= loan.installment_count;
						return (
							<Row
								key={loan.id}
								title={loan.title}
								aside={
									<span className="flex items-center gap-2">
										{loan.kind === "capital" ? (
											<StatusChip tone="info" label={t.plan.capitalLoan} />
										) : null}
										<span className="text-sm text-muted">
											{formatAmount(loan.paid_count)} / {formatAmount(loan.installment_count)}
										</span>
									</span>
								}
							>
								<Bar label={loan.title} percent={loan.percent_paid} />
								<p className="text-sm text-muted">
									{t.planning.installment} {formatMoney(loan.installment_amount, book.currency)} ·{" "}
									{t.planning.remaining} {formatMoney(loan.remaining, book.currency)}
								</p>
								{loan.next_due_on ? (
									<p className="text-sm text-muted">
										{t.planning.next} {formatFullDate(loan.next_due_on)}
									</p>
								) : null}
								<LoanSchedule loan={loan} />
								<Actions>
									{finished ? (
										<StatusChip tone="success" label={t.planningForms.allPaid} />
									) : (
										<Button
											size="sm"
											variant="secondary"
											onPress={() => {
												bankForm.reset({ bank_account_id: "" });
												setPaying(loan);
											}}
										>
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
			{book.type === "personal" ? <Funds book={book} /> : null}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.plan.addInstallment} size="sm">
				<div className="flex flex-col gap-4">
					{book.type === "personal" ? (
						<div className="flex flex-col gap-1.5">
							<span className="text-sm font-medium">{t.plan.installmentKind}</span>
							<div className="flex flex-wrap gap-2">
								{(["loan", "fund"] as const).map((kind) => (
									<Button
										key={kind}
										size="sm"
										variant={kind === addKind ? "primary" : "ghost"}
										onPress={() => setAddKind(kind)}
									>
										{kind === "loan" ? t.plan.kindLoan : t.plan.kindFund}
									</Button>
								))}
							</div>
							<p className="text-sm text-muted">
								{addKind === "loan" ? t.plan.kindLoanHint : t.plan.kindFundHint}
							</p>
						</div>
					) : null}
					{addKind === "fund" && book.type === "personal" ? (
						<FundForm book={book} onDone={() => setAdding(false)} />
					) : (
						<LoanForm book={book} onDone={() => setAdding(false)} />
					)}
				</div>
			</Modal>
			<ConfirmDialog
				isOpen={paying !== null}
				onOpenChange={(open) => !open && setPaying(null)}
				title={t.planningForms.payTitle}
				description={
					paying
						? `${paying.kind === "capital" ? t.plan.capitalPayBody : t.planningForms.payBody} (${formatMoney(paying.installment_amount, book.currency)})`
						: undefined
				}
				confirmLabel={t.planningForms.payConfirm}
				onConfirm={async () => {
					if (!paying) return;
					try {
						const chosen = bankForm.getValues("bank_account_id");
						// Sending the count we saw makes a double tap or a retry a refusal, not a second payment.
						await pay.mutateAsync({
							bookId: book.id,
							loanId: paying.id,
							params: {
								expected_paid_count: paying.paid_count,
								// Empty (accounts not loaded) leaves it to the book's default; «none» is no account.
								bank_account_id: chosen === "" ? undefined : chosen,
							},
						});
						await Promise.all([
							queryClient.invalidateQueries({ queryKey: getPlanningListLoansQueryKey(book.id) }),
							refreshMoney(queryClient, book.id),
						]);
						toast.success(t.planningForms.paid);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			>
				{paying ? (
					// Chosen for this one installment, from the book's own accounts.
					<FormRoot form={bankForm} onSubmit={() => {}}>
						<BankField name="bank_account_id" bookId={book.id} />
					</FormRoot>
				) : null}
			</ConfirmDialog>
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
						await queryClient.invalidateQueries({
							queryKey: getPlanningListLoansQueryKey(book.id),
						});
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
	if (!book) return <BookRequired />;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.planning} description={book.name} />
			<SectionCard title={t.planning.title} description={t.planning.intro}>
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
