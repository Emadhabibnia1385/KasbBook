import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	FormRoot,
	RadioGroupField,
	SelectField,
	SubmitButton,
	SwitchField,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getPlanningListBudgetsQueryKey,
	getPlanningListDebtsQueryKey,
	getPlanningListLoansQueryKey,
	usePlanningCreateDebt,
	usePlanningCreateLoan,
	usePlanningIncreaseDebt,
	usePlanningSetBudget,
	usePlanningSettleDebt,
} from "@/api/generated/planning/planning";
import type { BookResponse, DebtResponse } from "@/api/generated/model";
import { BankField } from "@/features/banks/BankField";
import { bankValue } from "@/features/banks/bankValue";
import { CategoryChips } from "@/features/books/CategoryChips";
import { pickedDay, todayPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { formatMoney, toAscii } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

// Money stays a string from the keyboard to the API: validated here, never turned into a number to send.
const amountRule = z
	.string()
	.transform(toAscii)
	.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, {
		error: t.planningForms.badAmount,
	});

const budgetSchema = z
	.object({
		target: z.enum(["expense", "income", "category"]),
		category: z.string().trim().max(80),
		amount: amountRule,
	})
	.refine((value) => value.target !== "category" || value.category.length > 0, {
		path: ["category"],
		error: t.planningForms.needBudgetCategory,
	});
type BudgetValues = z.input<typeof budgetSchema>;

export function BudgetForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const setBudget = usePlanningSetBudget();
	const form = useForm<BudgetValues>({
		resolver: zodResolver(budgetSchema),
		defaultValues: { target: "expense", category: "", amount: "" },
	});
	const target = useWatch({ control: form.control, name: "target" });
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = budgetSchema.parse(raw);
				try {
					await setBudget.mutateAsync({
						bookId: book.id,
						data:
							values.target === "category"
								? { kind: "category", target: values.category, amount: values.amount }
								: { kind: "flow", target: values.target, amount: values.amount },
					});
					await queryClient.invalidateQueries({
						queryKey: getPlanningListBudgetsQueryKey(book.id),
					});
					toast.success(t.planningForms.budgetSaved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<SelectField
				name="target"
				label={t.planningForms.budgetFor}
				options={[
					{ value: "expense", label: t.planningForms.budgetForExpense },
					{ value: "income", label: t.planningForms.budgetForIncome },
					{ value: "category", label: t.planningForms.budgetForCategory },
				]}
			/>
			{target === "category" ? (
				<>
					<TextField name="category" label={t.planningForms.budgetCategory} isRequired />
					<CategoryChips
						bookId={book.id}
						flow="expense"
						onPick={(name) =>
							form.setValue("category", name, { shouldValidate: true, shouldDirty: true })
						}
					/>
				</>
			) : null}
			<TextField
				name="amount"
				label={t.planningForms.budgetLimit}
				description={t.planningForms.budgetHint}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

const debtSchema = z.object({
	person: z.string().trim().min(1, { error: t.planningForms.needPerson }).max(120),
	direction: z.enum(["owed_to_me", "i_owe"]),
	amount: amountRule,
	due_on: z.string(),
	note: z.string().max(300),
	// The day the money moved, and the account when it really did: empty until the book's accounts load.
	occurred_on: z.string().min(1, { error: t.days.needDate }),
	bank_account_id: z.string(),
});
type DebtValues = z.input<typeof debtSchema>;

export function DebtForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const create = usePlanningCreateDebt();
	const form = useForm<DebtValues>({
		resolver: zodResolver(debtSchema),
		defaultValues: {
			person: "",
			direction: "owed_to_me",
			amount: "",
			due_on: "",
			note: "",
			occurred_on: todayPicker(),
			bank_account_id: "",
		},
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = debtSchema.parse(raw);
				try {
					await create.mutateAsync({
						bookId: book.id,
						data: {
							person: values.person,
							direction: values.direction,
							amount: values.amount,
							due_on: pickedDay(values.due_on) || null,
							note: values.note.trim() || null,
							occurred_on: pickedDay(values.occurred_on),
							// Empty (accounts not loaded) means none moved; «none» is the same, said out loud.
							bank_account_id: bankValue(values.bank_account_id) ?? null,
						},
					});
					await Promise.all([
						queryClient.invalidateQueries({ queryKey: getPlanningListDebtsQueryKey(book.id) }),
						refreshMoney(queryClient, book.id),
					]);
					toast.success(t.planningForms.debtCreated);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<RadioGroupField
				name="direction"
				label={t.planningForms.direction}
				options={[
					{ value: "owed_to_me", label: t.planningForms.owedToMe },
					{ value: "i_owe", label: t.planningForms.iOwe },
				]}
			/>
			<TextField name="person" label={t.planningForms.person} isRequired />
			<TextField
				name="amount"
				label={t.planningForms.amount}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<DayField name="occurred_on" label={t.plan.date} isRequired />
			<BankField
				name="bank_account_id"
				bookId={book.id}
				label={t.banks.debtAccount}
				noneLabel={t.banks.debtNone}
			/>
			<DayField name="due_on" label={t.planningForms.dueOn} />
			<TextField name="note" label={t.planningForms.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

const moreSchema = z.object({
	amount: amountRule,
	occurred_on: z.string().min(1, { error: t.days.needDate }),
	note: z.string().max(300),
	bank_account_id: z.string(),
});
type MoreValues = z.input<typeof moreSchema>;

/** The debt grew: more was lent to them or borrowed from them, on a day, through an account if cash moved. */
export function IncreaseDebtForm({
	book,
	debt,
	onDone,
}: {
	book: BookResponse;
	debt: DebtResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const increase = usePlanningIncreaseDebt();
	const form = useForm<MoreValues>({
		resolver: zodResolver(moreSchema),
		defaultValues: { amount: "", occurred_on: todayPicker(), note: "", bank_account_id: "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = moreSchema.parse(raw);
				try {
					await increase.mutateAsync({
						bookId: book.id,
						debtId: debt.id,
						data: {
							amount: values.amount,
							occurred_on: pickedDay(values.occurred_on),
							note: values.note.trim() || null,
							bank_account_id: bankValue(values.bank_account_id) ?? null,
						},
					});
					await Promise.all([
						queryClient.invalidateQueries({ queryKey: getPlanningListDebtsQueryKey(book.id) }),
						queryClient.invalidateQueries({
							predicate: (query) => String(query.queryKey[0]).includes("/debts/"),
						}),
						refreshMoney(queryClient, book.id),
					]);
					toast.success(t.plan.moreDone);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<p className="text-sm text-muted">{t.plan.moreHint}</p>
			<TextField name="amount" label={t.plan.moreAmount} inputMode="decimal" dir="ltr" isRequired />
			<DayField name="occurred_on" label={t.plan.date} isRequired />
			<BankField
				name="bank_account_id"
				bookId={book.id}
				label={t.banks.debtAccount}
				noneLabel={t.banks.debtNone}
			/>
			<TextField name="note" label={t.planningForms.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

const settleSchema = z.object({
	amount: amountRule,
	record_transaction: z.boolean(),
	occurred_on: z.string().min(1, { error: t.days.needDate }),
	bank_account_id: z.string(),
});
type SettleValues = z.input<typeof settleSchema>;

/** Settling only marks the debt paid; booking the money moving as a transaction is a separate, opt-in choice. */
export function SettleForm({
	book,
	debt,
	onDone,
}: {
	book: BookResponse;
	debt: DebtResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const settle = usePlanningSettleDebt();
	const form = useForm<SettleValues>({
		resolver: zodResolver(settleSchema),
		defaultValues: {
			// Everything that is left, unless the person writes less: then it is a part payment.
			amount: String(Number(debt.remaining ?? debt.amount)),
			record_transaction: false,
			occurred_on: todayPicker(),
			bank_account_id: "",
		},
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = settleSchema.parse(raw);
				try {
					await settle.mutateAsync({
						bookId: book.id,
						debtId: debt.id,
						data: {
							record_transaction: values.record_transaction,
							amount: values.amount,
							occurred_on: pickedDay(values.occurred_on),
							// Cash that really moved goes through this account; «none» (or not loaded) moves none.
							bank_account_id: values.record_transaction
								? bankValue(values.bank_account_id)
								: (bankValue(values.bank_account_id) ?? null),
						},
					});
					await Promise.all([
						queryClient.invalidateQueries({ queryKey: getPlanningListDebtsQueryKey(book.id) }),
						refreshMoney(queryClient, book.id),
					]);
					toast.success(
						Number(values.amount) >= Number(debt.remaining ?? debt.amount)
							? t.planning.settledToast
							: t.plan.partDone,
					);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField
				name="amount"
				label={t.plan.partAmount}
				description={t.plan.partHint}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<DayField name="occurred_on" label={t.plan.date} isRequired />
			<BankField
				name="bank_account_id"
				bookId={book.id}
				label={t.banks.debtAccount}
				noneLabel={t.banks.debtNone}
			/>
			<SwitchField
				name="record_transaction"
				label={t.planningForms.recordTransaction}
				description={t.planningForms.recordTransactionHint}
			/>
			<SubmitButton>{t.planningForms.settleConfirm}</SubmitButton>
		</FormRoot>
	);
}

const loanSchema = z.object({
	title: z.string().trim().min(1, { error: t.planningForms.needLoanTitle }).max(120),
	installment_amount: amountRule,
	installment_count: z
		.string()
		.transform(toAscii)
		.refine((value) => /^\d{1,3}$/.test(value) && Number(value) >= 1 && Number(value) <= 600, {
			error: t.planningForms.badCount,
		}),
	starts_on: z.string().min(1, { error: t.days.needDate }),
});
type LoanValues = z.input<typeof loanSchema>;

export function LoanForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const create = usePlanningCreateLoan();
	const form = useForm<LoanValues>({
		resolver: zodResolver(loanSchema),
		defaultValues: {
			title: "",
			installment_amount: "",
			installment_count: "",
			starts_on: todayPicker(),
		},
	});
	// What the whole loan will have cost by the last instalment, as the two numbers are typed.
	const each = toAscii(useWatch({ control: form.control, name: "installment_amount" }) ?? "");
	const count = toAscii(useWatch({ control: form.control, name: "installment_count" }) ?? "");
	const total = Number(each) * Number(count);
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = loanSchema.parse(raw);
				try {
					await create.mutateAsync({
						bookId: book.id,
						data: {
							title: values.title,
							installment_amount: values.installment_amount,
							installment_count: Number(values.installment_count),
							starts_on: pickedDay(values.starts_on),
						},
					});
					await queryClient.invalidateQueries({ queryKey: getPlanningListLoansQueryKey(book.id) });
					toast.success(t.planningForms.loanCreated);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField name="title" label={t.planningForms.loanTitle} isRequired />
			<TextField
				name="installment_amount"
				label={t.planningForms.installmentAmount}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<TextField
				name="installment_count"
				label={t.planningForms.installmentCount}
				inputMode="numeric"
				dir="ltr"
				isRequired
			/>
			{Number.isFinite(total) && total > 0 ? (
				<p className="text-sm text-muted">
					{t.plan.totalPayable}:{" "}
					<b className="text-foreground">{formatMoney(String(total), book.currency)}</b>
				</p>
			) : null}
			<DayField name="starts_on" label={t.planningForms.startsOn} isRequired />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}
