import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CompactRows } from "./CompactRows";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	Collapsible,
	DataTable,
	EmptyState,
	FormRoot,
	Modal,
	useIsNarrow,
	PageHeader,
	RadioGroupField,
	StatusChip,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	useBooksDeleteTransaction,
	useBooksEditTransaction,
	useBooksListTransactions,
	useBooksRecordTransaction,
} from "@/api/generated/books/books";
import type { BookResponse, TransactionResponse } from "@/api/generated/model";
import { CategoryChips } from "@/features/books/CategoryChips";
import { useActiveBook } from "@/features/books/useActiveBook";
import { pickedDay, toPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { currencyName, formatDay, formatMoney, toAscii } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const PER_PAGE = 20;

const amountRule = z
	.string()
	.transform(toAscii)
	.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, {
		error: t.transactions.badAmount,
	});

const schema = z.object({
	flow: z.enum(["income", "expense"]),
	amount: amountRule,
	category: z.string().trim().min(1, { error: t.transactions.needCategory }).max(80),
	description: z.string().max(300),
});
type Values = z.input<typeof schema>;

const editSchema = z.object({
	amount: amountRule,
	category: z.string().trim().min(1, { error: t.transactions.needCategory }).max(80),
	description: z.string().max(300),
	occurred_on: z.string().min(1, { error: t.days.needDate }),
});
type EditValues = z.input<typeof editSchema>;

/** "1500000.0000" → "1500000": the amount as a person would type it back. */
function plainAmount(value: string): string {
	return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

function EditForm({
	book,
	row,
	onDone,
}: {
	book: BookResponse;
	row: TransactionResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const edit = useBooksEditTransaction();
	const form = useForm<EditValues>({
		resolver: zodResolver(editSchema),
		defaultValues: {
			amount: plainAmount(row.original_amount),
			category: row.category,
			description: row.description ?? "",
			occurred_on: toPicker(row.occurred_on),
		},
	});
	const flow = row.flow === "income" ? "income" : "expense";
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = editSchema.parse(raw);
				// Only what changed is sent: an unchanged amount would be re-checked against the wallet for nothing.
				const changes: Record<string, string | null> = {};
				if (values.amount !== plainAmount(row.original_amount)) changes.amount = values.amount;
				if (values.category !== row.category) changes.category = values.category;
				if ((values.description || null) !== (row.description || null))
					changes.description = values.description || null;
				if (pickedDay(values.occurred_on) !== row.occurred_on)
					changes.occurred_on = pickedDay(values.occurred_on);
				if (Object.keys(changes).length === 0) {
					onDone();
					return;
				}
				try {
					await edit.mutateAsync({ bookId: book.id, transactionId: row.id, data: changes });
					await refreshMoney(queryClient, book.id);
					toast.success(t.txExtra.editSaved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField
				name="amount"
				label={t.transactions.amount}
				description={
					row.original_currency === book.currency
						? undefined
						: `${t.txExtra.foreignCurrency} ${currencyName(row.original_currency)}`
				}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<TextField name="category" label={t.transactions.category} isRequired />
			<CategoryChips
				bookId={book.id}
				flow={flow}
				onPick={(name) =>
					form.setValue("category", name, { shouldValidate: true, shouldDirty: true })
				}
			/>
			<DayField name="occurred_on" label={t.transactions.date} isRequired />
			<TextField name="description" label={t.transactions.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function AddForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const record = useBooksRecordTransaction();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { flow: "expense", amount: "", category: "", description: "" },
	});
	const flow = useWatch({ control: form.control, name: "flow" });
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					// Scope follows the book's kind on the server; the panel records what the person typed.
					await record.mutateAsync({
						bookId: book.id,
						data: {
							flow: values.flow,
							scope:
								book.type === "personal" ? "personal" : book.type === "business" ? "work" : "team",
							category: values.category,
							amount: values.amount,
							description: values.description || null,
						},
					});
					await refreshMoney(queryClient, book.id);
					toast.success(t.transactions.saved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<RadioGroupField
				name="flow"
				label={t.transactions.kind}
				options={[
					{ value: "expense", label: t.common.expense },
					{ value: "income", label: t.common.income },
				]}
			/>
			<TextField
				name="amount"
				label={t.transactions.amount}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<TextField name="category" label={t.transactions.category} isRequired />
			<CategoryChips
				bookId={book.id}
				flow={flow}
				onPick={(name) =>
					form.setValue("category", name, { shouldValidate: true, shouldDirty: true })
				}
			/>
			<TextField name="description" label={t.transactions.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

// On a phone the date range is folded away until wanted; it opens by itself while a filter is active.
function Filters({
	narrow,
	filtered,
	children,
}: {
	narrow: boolean;
	filtered: boolean;
	children: React.ReactNode;
}) {
	if (!narrow) return <>{children}</>;
	return (
		<Collapsible title={t.txExtra.filter} defaultOpen={filtered}>
			{children}
		</Collapsible>
	);
}

function List({ book }: { book: BookResponse }) {
	const [page, setPage] = useState(1);
	const [adding, setAdding] = useState(false);
	const [editing, setEditing] = useState<TransactionResponse | null>(null);
	const [removing, setRemoving] = useState<TransactionResponse | null>(null);
	const [since, setSince] = useState("");
	const [until, setUntil] = useState("");
	const queryClient = useQueryClient();
	const range = { since: pickedDay(since) || undefined, until: pickedDay(until) || undefined };
	const filtered = Boolean(range.since || range.until);
	const query = useBooksListTransactions(book.id, { ...range, page, per_page: PER_PAGE });
	const remove = useBooksDeleteTransaction();
	const narrow = useIsNarrow("md");
	const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PER_PAGE));

	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.transactions}
				description={book.name}
				actions={<Button onPress={() => setAdding(true)}>{t.transactions.add}</Button>}
			/>
			<Filters narrow={narrow} filtered={filtered}>
				<fieldset className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
					<legend className="sr-only">{t.txExtra.filter}</legend>
					<DayField
						label={t.txExtra.since}
						value={since}
						onChange={(value) => {
							setSince(value);
							setPage(1);
						}}
					/>
					<DayField
						label={t.txExtra.until}
						value={until}
						errorMessage={
							range.since && range.until && range.since > range.until
								? t.txExtra.badRange
								: undefined
						}
						onChange={(value) => {
							setUntil(value);
							setPage(1);
						}}
					/>
					{filtered ? (
						<Button
							variant="ghost"
							onPress={() => {
								setSince("");
								setUntil("");
								setPage(1);
							}}
						>
							{t.txExtra.clearFilter}
						</Button>
					) : null}
				</fieldset>
			</Filters>
			{narrow ? (
				<CompactRows
					book={book}
					rows={query.data?.items}
					status={query.isError ? "error" : query.isLoading ? "loading" : "ready"}
					onRetry={() => void query.refetch()}
					emptyTitle={filtered ? t.txExtra.filteredEmptyTitle : t.transactions.emptyTitle}
					empty={filtered ? t.txExtra.filteredEmpty : t.transactions.empty}
					page={page}
					pageCount={pages}
					onPageChange={setPage}
					onEdit={setEditing}
					onRemove={setRemoving}
				/>
			) : (
				<DataTable<TransactionResponse>
					ariaLabel={t.nav.transactions}
					cards="md"
					status={query.isError ? "error" : query.isLoading ? "loading" : "ready"}
					onRetry={() => void query.refetch()}
					rows={query.data?.items}
					getRowId={(row) => row.id}
					emptyTitle={filtered ? t.txExtra.filteredEmptyTitle : t.transactions.emptyTitle}
					empty={filtered ? t.txExtra.filteredEmpty : t.transactions.empty}
					columns={[
						{
							id: "category",
							header: t.transactions.category,
							isRowHeader: true,
							cell: (row) => row.category,
						},
						{
							id: "amount",
							header: t.transactions.amount,
							align: "end",
							cell: (row) => (
								<span dir="ltr" className={row.flow === "income" ? "text-success" : undefined}>
									{row.flow === "income" ? "+" : "−"}
									{formatMoney(row.converted_amount, book.currency)}
								</span>
							),
						},
						{
							id: "kind",
							header: t.transactions.kind,
							cell: (row) => (
								<StatusChip
									tone={row.flow === "income" ? "success" : "neutral"}
									label={row.flow === "income" ? t.common.income : t.common.expense}
								/>
							),
						},
						{ id: "date", header: t.transactions.date, cell: (row) => formatDay(row.occurred_on) },
						{ id: "note", header: t.transactions.note, cell: (row) => row.description ?? "—" },
						{
							id: "actions",
							header: "",
							isActions: true,
							cell: (row) => (
								<div className="flex gap-1">
									<Button size="sm" variant="ghost" onPress={() => setEditing(row)}>
										{t.common.edit}
									</Button>
									<Button size="sm" variant="ghost" onPress={() => setRemoving(row)}>
										{t.common.delete}
									</Button>
								</div>
							),
						},
					]}
					pagination={{ page, pageCount: pages, onPageChange: setPage }}
				/>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.transactions.add} size="sm">
				<AddForm book={book} onDone={() => setAdding(false)} />
			</Modal>
			<Modal
				isOpen={editing !== null}
				onOpenChange={(open) => !open && setEditing(null)}
				title={t.txExtra.edit}
				size="sm"
			>
				{editing ? (
					<EditForm key={editing.id} book={book} row={editing} onDone={() => setEditing(null)} />
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.transactions.deleteTitle}
				description={t.transactions.deleteBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, transactionId: removing.id });
						await refreshMoney(queryClient, book.id);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}

export function Transactions() {
	const { book, isLoading } = useActiveBook();
	if (isLoading) return null;
	if (!book)
		return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return <List book={book} />;
}
