import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	PageHeader,
	PageSkeleton,
	RadioGroupField,
	SectionCard,
	SelectField,
	StatusChip,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import { getBooksListBooksQueryKey, useBooksSetCostPolicy } from "@/api/generated/books/books";
import type { BookResponse, FundResponse, TreasuryRuleResponse } from "@/api/generated/model";
import {
	usePayrollAddRule,
	usePayrollCloseRule,
	usePayrollCreateFund,
	usePayrollDeleteFund,
	usePayrollDeleteRule,
	usePayrollToggleFund,
	usePayrollToggleRule,
	usePayrollListFunds,
	usePayrollListRules,
} from "@/api/generated/payroll/payroll";
import { formatAmount, formatFullDate, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";
import { todayIso } from "./calendar";
import { isPositive, sum, toUnits } from "./decimal";
import { PayrollPage } from "./PayrollPage";
import { fundKindLabel, refreshPayroll, reportError, ruleBasisLabel } from "./shared";
import { Figure, ItemCard } from "./ui";

const DECIMAL = /^\d+(\.\d{1,4})?$/;

// ---------------------------------------------------------------- cost policy
const POLICIES = [
	{
		value: "before_split",
		label: t.payroll.costPolicy.before_split,
		description: t.payroll.costPolicy.beforeSplitBody,
	},
	{
		value: "from_treasury",
		label: t.payroll.costPolicy.from_treasury,
		description: t.payroll.costPolicy.fromTreasuryBody,
	},
];
const policySchema = z.object({
	cost_policy: z
		.string({ error: t.payroll.costPolicy.needPolicy })
		.min(1, { error: t.payroll.costPolicy.needPolicy }),
});
type PolicyValues = z.input<typeof policySchema>;

function PolicyForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const set = useBooksSetCostPolicy();
	const form = useForm<PolicyValues>({
		resolver: zodResolver(policySchema),
		defaultValues: { cost_policy: book.cost_policy },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					await set.mutateAsync({ bookId: book.id, data: { cost_policy: values.cost_policy } });
					await queryClient.invalidateQueries({ queryKey: getBooksListBooksQueryKey() });
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.costPolicy.saved);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<RadioGroupField name="cost_policy" label={t.payroll.costPolicy.title} options={POLICIES} />
			<p className="text-sm text-muted text-pretty">{t.payroll.costPolicy.note}</p>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

// ---------------------------------------------------------------------- funds
const FUND_KINDS = (["main", "emergency", "tax", "development", "equipment", "bonus"] as const).map(
	(value) => ({ value, label: t.payroll.fundKind[value] }),
);
const fundSchema = z.object({
	name: z.string().trim().min(1, { error: t.payroll.funds.needName }).max(80),
	kind: z.string({ error: t.payroll.funds.needKind }).min(1, { error: t.payroll.funds.needKind }),
});
type FundValues = z.input<typeof fundSchema>;

function FundForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const create = usePayrollCreateFund();
	const form = useForm<FundValues>({
		resolver: zodResolver(fundSchema),
		defaultValues: { name: "", kind: "main" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					await create.mutateAsync({
						bookId: book.id,
						data: { name: values.name, kind: values.kind },
					});
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.funds.created);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<TextField name="name" label={t.payroll.funds.name} isRequired />
			<SelectField name="kind" label={t.payroll.funds.kind} options={FUND_KINDS} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

// ---------------------------------------------------------------------- rules
const RULE_BASES = (["gross_percent", "net_percent", "fixed"] as const).map((value) => ({
	value,
	label: t.payroll.ruleBasis[value],
}));
const ruleSchema = z
	.object({
		basis: z
			.string({ error: t.payroll.rules.needBasis })
			.min(1, { error: t.payroll.rules.needBasis }),
		value: z.string().transform(toAscii),
		category: z.string().trim().max(80),
	})
	.superRefine((values, context) => {
		// A percentage is a plain number, never «۱۰م»: ten million percent is not a rule.
		const fixed = values.basis === "fixed";
		const valid =
			DECIMAL.test(values.value) &&
			isPositive(values.value) &&
			(fixed || toUnits(values.value) <= 100n * 10_000n);
		if (!valid)
			context.addIssue({
				code: "custom",
				path: ["value"],
				message: fixed ? t.payroll.rules.badFixed : t.payroll.rules.badPercent,
			});
	});
type RuleValues = z.input<typeof ruleSchema>;

function RuleForm({
	book,
	fund,
	onDone,
}: {
	book: BookResponse;
	fund: FundResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const add = usePayrollAddRule();
	const form = useForm<RuleValues>({
		resolver: zodResolver(ruleSchema),
		defaultValues: { basis: "gross_percent", value: "", category: "" },
	});
	const fixed = useWatch({ control: form.control, name: "basis" }) === "fixed";
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = ruleSchema.parse(raw);
				try {
					await add.mutateAsync({
						bookId: book.id,
						fundId: fund.id,
						data: { basis: values.basis, value: values.value, category: values.category || null },
					});
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.rules.created);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<SelectField name="basis" label={t.payroll.rules.basis} options={RULE_BASES} />
			<TextField
				name="value"
				label={t.payroll.rules.value}
				description={fixed ? t.payroll.rules.hintFixed : t.payroll.rules.hintPercent}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<TextField
				name="category"
				label={t.payroll.rules.category}
				description={t.payroll.rules.categoryHint}
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function Rules({ book, fund }: { book: BookResponse; fund: FundResponse }) {
	const queryClient = useQueryClient();
	const query = usePayrollListRules(book.id, fund.id);
	const close = usePayrollCloseRule();
	const remove = usePayrollDeleteRule();
	const toggle = usePayrollToggleRule();
	const [adding, setAdding] = useState(false);
	const [stopping, setStopping] = useState<TreasuryRuleResponse | null>(null);
	const [removing, setRemoving] = useState<TreasuryRuleResponse | null>(null);
	const valueText = (rule: TreasuryRuleResponse) =>
		rule.basis === "fixed"
			? formatMoney(rule.value, book.currency)
			: `${formatAmount(rule.value)}٪`;

	return (
		<div className="flex flex-col gap-3 border-t border-border pt-3">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<h3 className="text-sm font-semibold">{t.payroll.funds.rules}</h3>
				<Button size="sm" variant="secondary" onPress={() => setAdding(true)}>
					{t.payroll.rules.add}
				</Button>
			</div>
			{query.isLoading ? (
				<PageSkeleton header={false} rows={1} />
			) : query.isError ? (
				<ErrorState onRetry={() => void query.refetch()} />
			) : query.data?.length ? (
				<ul className="flex flex-col gap-2">
					{query.data.map((rule) => (
						<li key={rule.id} className="flex flex-col gap-2 rounded-xl border border-border p-3">
							<div className="flex flex-wrap items-center justify-between gap-2">
								<span className="font-medium">
									<Figure>{valueText(rule)}</Figure> · {ruleBasisLabel(rule.basis)}
								</span>
								<StatusChip
									tone={rule.is_active ? "success" : "neutral"}
									label={rule.is_active ? t.payroll.rules.on : t.payroll.rules.off}
								/>
							</div>
							<p className="text-sm text-muted">
								{t.payroll.rules.from} {formatFullDate(rule.effective_from)}
								{rule.effective_to
									? ` · ${t.payroll.rules.until} ${formatFullDate(rule.effective_to)}`
									: ""}
								{rule.category ? ` · ${rule.category}` : ""}
							</p>
							<div className="flex flex-wrap gap-2">
								{rule.effective_to ? null : (
									<Button size="sm" variant="secondary" onPress={() => setStopping(rule)}>
										{t.payroll.rules.stop}
									</Button>
								)}
								<Button
									size="sm"
									variant="secondary"
									isPending={toggle.isPending && toggle.variables?.ruleId === rule.id}
									onPress={async () => {
										try {
											const now = await toggle.mutateAsync({
												bookId: book.id,
												fundId: fund.id,
												ruleId: rule.id,
											});
											await refreshPayroll(queryClient, book.id);
											toast.success(now.is_active ? t.switches.ruleOn : t.switches.ruleOff);
										} catch (error) {
											reportError(error);
										}
									}}
								>
									{rule.is_active ? t.switches.ruleTurnOff : t.switches.ruleTurnOn}
								</Button>
								<Button size="sm" variant="ghost" onPress={() => setRemoving(rule)}>
									{t.payroll.rules.delete}
								</Button>
							</div>
						</li>
					))}
				</ul>
			) : (
				<p className="text-sm text-muted">{t.payroll.rules.empty}</p>
			)}

			<Modal
				isOpen={adding}
				onOpenChange={setAdding}
				title={`${t.payroll.rules.add}: ${fund.name}`}
				size="sm"
			>
				<RuleForm book={book} fund={fund} onDone={() => setAdding(false)} />
			</Modal>
			<ConfirmDialog
				isOpen={stopping !== null}
				onOpenChange={(open) => !open && setStopping(null)}
				title={t.payroll.rules.stopTitle}
				description={
					stopping
						? `${valueText(stopping)} · ${ruleBasisLabel(stopping.basis)}. ${t.payroll.rules.stopBody}`
						: undefined
				}
				confirmLabel={t.payroll.rules.stop}
				onConfirm={async () => {
					if (!stopping) return;
					try {
						await close.mutateAsync({
							bookId: book.id,
							fundId: fund.id,
							ruleId: stopping.id,
							data: { effective_to: todayIso() },
						});
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.rules.stopped);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.payroll.rules.deleteTitle}
				description={
					removing
						? `${valueText(removing)} · ${ruleBasisLabel(removing.basis)}. ${t.payroll.rules.deleteBody}`
						: undefined
				}
				confirmLabel={t.payroll.rules.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, fundId: fund.id, ruleId: removing.id });
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.rules.deleted);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}

function FundCard({
	book,
	fund,
	onDelete,
}: {
	book: BookResponse;
	fund: FundResponse;
	onDelete: () => void;
}) {
	const [open, setOpen] = useState(false);
	const queryClient = useQueryClient();
	const toggle = usePayrollToggleFund();
	return (
		<ItemCard
			title={fund.name}
			aside={
				<span className="flex flex-wrap items-center gap-2">
					<StatusChip tone="info" label={fundKindLabel(fund.kind)} />
					<StatusChip
						tone={fund.is_active ? "success" : "neutral"}
						label={fund.is_active ? t.payroll.funds.active : t.payroll.funds.inactive}
					/>
				</span>
			}
			actions={
				<>
					<Button
						size="sm"
						variant="secondary"
						onPress={() => setOpen((value) => !value)}
						aria-expanded={open}
					>
						{open ? t.payroll.funds.hideRules : t.payroll.funds.showRules}
					</Button>
					<Button
						size="sm"
						variant="secondary"
						isPending={toggle.isPending}
						onPress={async () => {
							try {
								const now = await toggle.mutateAsync({ bookId: book.id, fundId: fund.id });
								await refreshPayroll(queryClient, book.id);
								toast.success(now.is_active ? t.switches.fundOn : t.switches.fundOff);
							} catch (error) {
								reportError(error);
							}
						}}
					>
						{fund.is_active ? t.switches.fundTurnOff : t.switches.fundTurnOn}
					</Button>
					<Button size="sm" variant="ghost" onPress={onDelete}>
						{t.payroll.funds.delete}
					</Button>
				</>
			}
		>
			<p className="text-sm text-muted">
				{t.payroll.funds.balance}: <Figure>{formatMoney(fund.balance, book.currency)}</Figure>
			</p>
			<p className="text-xs text-muted">
				{t.switches.fundHint} {t.switches.lockedNote}
			</p>
			{open ? <Rules book={book} fund={fund} /> : null}
		</ItemCard>
	);
}

function Treasury({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const funds = usePayrollListFunds(book.id);
	const remove = usePayrollDeleteFund();
	const [creating, setCreating] = useState(false);
	const [changingPolicy, setChangingPolicy] = useState(false);
	const [removing, setRemoving] = useState<FundResponse | null>(null);
	const policyLabel =
		(t.payroll.costPolicy as Record<string, string>)[book.cost_policy] ?? book.cost_policy;

	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.team}
				description={book.name}
				actions={<Button onPress={() => setCreating(true)}>{t.payroll.funds.add}</Button>}
			/>

			<SectionCard
				title={t.payroll.costPolicy.title}
				actions={
					<Button size="sm" variant="secondary" onPress={() => setChangingPolicy(true)}>
						{t.payroll.costPolicy.change}
					</Button>
				}
			>
				<p className="text-sm">
					{t.payroll.costPolicy.current}: <strong>{policyLabel}</strong>
				</p>
			</SectionCard>

			<SectionCard title={t.payroll.funds.title} description={t.payroll.funds.lead}>
				{funds.isLoading ? (
					<PageSkeleton header={false} rows={2} />
				) : funds.isError ? (
					<ErrorState onRetry={() => void funds.refetch()} />
				) : funds.data?.length ? (
					<div className="flex flex-col gap-4">
						<ul className="grid gap-3 md:grid-cols-2">
							{funds.data.map((fund) => (
								<FundCard
									key={fund.id}
									book={book}
									fund={fund}
									onDelete={() => setRemoving(fund)}
								/>
							))}
						</ul>
						<p className="text-sm text-muted">
							{t.payroll.funds.total}:{" "}
							<Figure>
								{formatMoney(sum(funds.data.map((fund) => fund.balance)), book.currency)}
							</Figure>
						</p>
					</div>
				) : (
					<EmptyState title={t.payroll.funds.emptyTitle} description={t.payroll.funds.empty} />
				)}
			</SectionCard>

			<Modal isOpen={creating} onOpenChange={setCreating} title={t.payroll.funds.add} size="sm">
				<FundForm book={book} onDone={() => setCreating(false)} />
			</Modal>
			<Modal
				isOpen={changingPolicy}
				onOpenChange={setChangingPolicy}
				title={t.payroll.costPolicy.change}
				size="sm"
			>
				<PolicyForm book={book} onDone={() => setChangingPolicy(false)} />
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.payroll.funds.deleteTitle}
				description={removing ? `${removing.name}. ${t.payroll.funds.deleteBody}` : undefined}
				confirmLabel={t.payroll.funds.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, fundId: removing.id });
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.funds.deleted);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}

export function Funds() {
	return <PayrollPage>{(book) => <Treasury book={book} />}</PayrollPage>;
}
