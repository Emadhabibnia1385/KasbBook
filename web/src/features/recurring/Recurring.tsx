import { BookRequired } from "@/features/books/BookRequired";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	DateTimeField,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	PageHeader,
	PageSkeleton,
	RadioGroupField,
	SelectField,
	StatusChip,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getRecurringListRulesQueryKey,
	useRecurringCreateRule,
	useRecurringDeleteRule,
	useRecurringListRules,
	useRecurringToggleRule,
} from "@/api/generated/recurring/recurring";
import type { BookResponse, RecurringResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { formatFullDate, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";

const PERIODS = [
	{ value: "monthly", label: t.recurring.periods.monthly },
	{ value: "weekly", label: t.recurring.periods.weekly },
	{ value: "daily", label: t.recurring.periods.daily },
];

const schema = z.object({
	flow: z.enum(["income", "expense"]),
	amount: z
		.string()
		.transform(toAscii)
		.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, {
			error: t.recurring.badAmount,
		}),
	category: z.string().trim().min(1, { error: t.recurring.needCategory }).max(80),
	period: z.enum(["daily", "weekly", "monthly"]),
	startsOn: z.string().min(10, { error: t.recurring.needDate }),
	description: z.string().max(300),
});
type Values = z.input<typeof schema>;

// The picker's value is a local `YYYY-MM-DDTHH:mm`; the rule only keeps the day.
function todayLocal(): string {
	const now = new Date();
	const pad = (n: number) => String(n).padStart(2, "0");
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T00:00`;
}

function AddForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const create = useRecurringCreateRule();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			flow: "expense",
			amount: "",
			category: "",
			period: "monthly",
			startsOn: todayLocal(),
			description: "",
		},
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					await create.mutateAsync({
						bookId: book.id,
						data: {
							flow: values.flow,
							category: values.category,
							amount: values.amount,
							period: values.period,
							starts_on: values.startsOn.slice(0, 10),
							description: values.description || null,
						},
					});
					await queryClient.invalidateQueries({ queryKey: getRecurringListRulesQueryKey(book.id) });
					toast.success(t.recurring.saved);
					onDone();
				} catch (error) {
					toast.danger(error instanceof Error ? error.message : t.errors.unknown);
				}
			}}
		>
			<RadioGroupField
				name="flow"
				label={t.recurring.kind}
				options={[
					{ value: "expense", label: t.common.expense },
					{ value: "income", label: t.common.income },
				]}
			/>
			<TextField
				name="amount"
				label={t.recurring.amount}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<TextField name="category" label={t.recurring.category} isRequired />
			<SelectField name="period" label={t.recurring.period} options={PERIODS} />
			<DateTimeField
				name="startsOn"
				label={t.recurring.startsOn}
				calendarLabel={t.recurring.calendar}
				timeLabel={t.recurring.time}
				clearLabel={t.recurring.clear}
				isRequired
			/>
			<TextField name="description" label={t.recurring.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function Rule({
	book,
	rule,
	onDelete,
}: {
	book: BookResponse;
	rule: RecurringResponse;
	onDelete: () => void;
}) {
	const queryClient = useQueryClient();
	const toggle = useRecurringToggleRule();
	return (
		<li className="flex flex-col gap-2 rounded-2xl border border-border bg-surface p-4">
			<div className="flex items-center justify-between gap-3">
				<span className="font-medium">{rule.category}</span>
				<StatusChip
					tone={rule.is_active ? "success" : "warning"}
					label={rule.is_active ? t.recurring.active : t.recurring.paused}
				/>
			</div>
			<p className={`text-lg font-semibold ${rule.flow === "income" ? "text-success" : ""}`}>
				{rule.flow === "income" ? "+" : "−"}
				{formatMoney(rule.amount, book.currency)}
			</p>
			<p className="text-sm text-muted">
				{t.recurring.periods[rule.period as keyof typeof t.recurring.periods] ?? rule.period} ·{" "}
				{t.recurring.next} {formatFullDate(rule.next_run_on)}
			</p>
			{rule.last_run_on ? (
				<p className="text-sm text-muted">
					{t.recurring.last} {formatFullDate(rule.last_run_on)}
				</p>
			) : null}
			{rule.description ? <p className="text-sm text-muted">{rule.description}</p> : null}
			<div className="flex gap-2">
				<Button
					size="sm"
					variant="secondary"
					isPending={toggle.isPending}
					onPress={async () => {
						try {
							await toggle.mutateAsync({ bookId: book.id, ruleId: rule.id });
							await queryClient.invalidateQueries({
								queryKey: getRecurringListRulesQueryKey(book.id),
							});
							toast.success(t.recurring.toggled);
						} catch (error) {
							toast.danger(error instanceof Error ? error.message : t.errors.unknown);
						}
					}}
				>
					{rule.is_active ? t.recurring.pause : t.recurring.resume}
				</Button>
				<Button size="sm" variant="ghost" onPress={onDelete}>
					{t.common.delete}
				</Button>
			</div>
		</li>
	);
}

function Content({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const [adding, setAdding] = useState(false);
	const [removing, setRemoving] = useState<RecurringResponse | null>(null);
	const { data = [], isLoading, isError, refetch } = useRecurringListRules(book.id);
	const remove = useRecurringDeleteRule();
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.recurring.title}
				description={book.name}
				actions={<Button onPress={() => setAdding(true)}>{t.recurring.add}</Button>}
			/>
			<p className="text-sm text-muted">{t.recurring.lead}</p>
			{isLoading ? (
				<PageSkeleton header={false} rows={3} />
			) : isError ? (
				<ErrorState onRetry={() => void refetch()} />
			) : data.length === 0 ? (
				<EmptyState title={t.recurring.emptyTitle} description={t.recurring.empty} />
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{data.map((rule) => (
						<Rule key={rule.id} book={book} rule={rule} onDelete={() => setRemoving(rule)} />
					))}
				</ul>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.recurring.add} size="sm">
				<AddForm book={book} onDone={() => setAdding(false)} />
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.recurring.deleteTitle}
				description={t.recurring.deleteBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					await remove.mutateAsync({ bookId: book.id, ruleId: removing.id });
					await queryClient.invalidateQueries({ queryKey: getRecurringListRulesQueryKey(book.id) });
					toast.success(t.recurring.deleted);
				}}
			/>
		</div>
	);
}

export function Recurring() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <BookRequired />;
	return <Content book={book} />;
}
