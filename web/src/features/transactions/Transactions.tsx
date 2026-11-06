import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PlusIcon } from "@/shared/icons";
import { Amount } from "./Amount";
import { MoneyFields } from "./MoneyFields";
import { CategoryField, FlowSwitch } from "./FormControls";
import { AttachmentsField } from "./AttachmentsField";
import { CompactRows } from "./CompactRows";
import { FilterBar } from "./FilterBar";
import { type Filters, NO_FILTERS, rangeDates, todayIso } from "./filters";
import { TransactionDetail } from "./TransactionDetail";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	DataTable,
	EmptyState,
	FormRoot,
	Modal,
	useIsNarrow,
	PageHeader,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	booksAddAttachment,
	useBooksDeleteTransaction,
	useBooksEditTransaction,
	useBooksListTransactions,
	useBooksRecordTransaction,
} from "@/api/generated/books/books";
import type { BookResponse, TransactionResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { pickedDay, toPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { formatAmount, formatDay, formatMoney, toAscii } from "@/shared/format";
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
	// The money it was paid in; the book's own currency unless chosen otherwise. A rate is only
	// asked for, and checked, when it is another one.
	currency: z.string(),
	rate: z.string().transform(toAscii),
	// Today unless changed: most entries are made the day they happen.
	occurred_on: z.string().min(1, { error: t.days.needDate }),
});
type Values = z.input<typeof schema>;

const editSchema = z.object({
	flow: z.enum(["income", "expense"]),
	currency: z.string(),
	rate: z.string().transform(toAscii),
	amount: amountRule,
	category: z.string().trim().min(1, { error: t.transactions.needCategory }).max(80),
	description: z.string().max(300),
	occurred_on: z.string().min(1, { error: t.days.needDate }),
});
type EditValues = z.input<typeof editSchema>;

/** "1500000.0000" → "1500000": the amount as a person would type it back. */
/** "300000.0000" → "300000"; a rate keeps what places it has, so a small one is not rounded away. */
function plainRate(value: string): string {
	return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

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
			flow: row.flow === "income" ? "income" : "expense",
			currency: row.original_currency,
			rate: plainRate(row.conversion_rate),
			amount: plainAmount(row.original_amount),
			category: row.category,
			description: row.description ?? "",
			occurred_on: toPicker(row.occurred_on),
		},
	});
	const flow = useWatch({ control: form.control, name: "flow" });
	return (
		<FormRoot
			form={form}
			className="grid gap-x-8 gap-y-4 md:grid-cols-2"
			onSubmit={async (raw) => {
				const values = editSchema.parse(raw);
				const other = values.currency !== book.currency;
				if (other && !(/^\d+(\.\d+)?$/.test(values.rate) && Number(values.rate) > 0)) {
					form.setError("rate", { message: t.fx.needRate });
					return;
				}
				// Only what changed is sent: an unchanged amount would be re-checked against the wallet for nothing.
				const changes: Record<string, string | null> = {};
				if (values.flow !== row.flow) changes.flow = values.flow;
				if (values.currency !== row.original_currency) changes.currency = values.currency;
				// The rate is sent when it changed, and with any new currency: a new currency has none to inherit.
				if (
					other &&
					(values.currency !== row.original_currency ||
						values.rate !== plainRate(row.conversion_rate))
				)
					changes.conversion_rate = values.rate;
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
			<div className="flex flex-col gap-4">
				<FlowSwitch name="flow" />
				<MoneyFields
					book={book}
					initialCurrency={row.original_currency}
					initialRate={plainRate(row.conversion_rate)}
				/>
				<CategoryField
					name="category"
					bookId={book.id}
					flow={flow}
					label={t.transactions.category}
					isRequired
				/>
				<DayField name="occurred_on" label={t.transactions.date} isRequired />
			</div>
			<div className="flex flex-col gap-4">
				<TextField name="description" label={t.transactions.note} />
				<AttachmentsField bookId={book.id} transactionId={row.id} queue={[]} onQueue={() => {}} />
			</div>
			<div className="md:col-span-2">
				<SubmitButton>{t.common.save}</SubmitButton>
			</div>
		</FormRoot>
	);
}

function AddForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const record = useBooksRecordTransaction();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			flow: "expense",
			amount: "",
			category: "",
			description: "",
			currency: book.currency,
			rate: "",
			occurred_on: toPicker(todayIso()),
		},
	});
	const flow = useWatch({ control: form.control, name: "flow" });
	// Files chosen before the transaction exists wait here and are sent once it does.
	const [files, setFiles] = useState<File[]>([]);
	return (
		<FormRoot
			form={form}
			className="grid gap-x-8 gap-y-4 md:grid-cols-2"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				const other = values.currency !== book.currency;
				if (other && !(/^\d+(\.\d+)?$/.test(values.rate) && Number(values.rate) > 0)) {
					form.setError("rate", { message: t.fx.needRate });
					return;
				}
				try {
					// Scope follows the book's kind on the server; the panel records what the person typed.
					const made = await record.mutateAsync({
						bookId: book.id,
						data: {
							flow: values.flow,
							scope:
								book.type === "personal" ? "personal" : book.type === "business" ? "work" : "team",
							category: values.category,
							amount: values.amount,
							description: values.description || null,
							occurred_on: pickedDay(values.occurred_on),
							currency: other ? values.currency : null,
							conversion_rate: other ? values.rate : null,
						},
					});
					let unsent = 0;
					for (const file of files) {
						try {
							await booksAddAttachment(book.id, made.id, { file });
						} catch {
							unsent += 1;
						}
					}
					await refreshMoney(queryClient, book.id);
					await queryClient.invalidateQueries({
						queryKey: [`/api/v1/books/${book.id}/transactions`],
					});
					toast.success(t.transactions.saved);
					// The transaction is saved either way; a file that did not go is said plainly, and can be added by editing.
					if (unsent) toast.danger(t.attach.someUnsent);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<div className="flex flex-col gap-4">
				<FlowSwitch name="flow" />
				<MoneyFields book={book} initialCurrency={book.currency} initialRate="" />
				<DayField name="occurred_on" label={t.transactions.date} isRequired />
			</div>
			<div className="flex flex-col gap-4">
				<CategoryField
					name="category"
					bookId={book.id}
					flow={flow}
					label={t.transactions.category}
					isRequired
				/>
				<TextField name="description" label={t.transactions.note} />
				<AttachmentsField bookId={book.id} queue={files} onQueue={setFiles} />
			</div>
			<div className="md:col-span-2">
				<SubmitButton>{t.common.save}</SubmitButton>
			</div>
		</FormRoot>
	);
}

function List({ book }: { book: BookResponse }) {
	const [page, setPage] = useState(1);
	const [adding, setAdding] = useState(false);
	const [opened, setOpened] = useState<TransactionResponse | null>(null);
	const [editing, setEditing] = useState<TransactionResponse | null>(null);
	const [removing, setRemoving] = useState<TransactionResponse | null>(null);
	const [filters, setFilters] = useState<Filters>(NO_FILTERS);
	const queryClient = useQueryClient();
	const dates = rangeDates(filters);
	const text = filters.q.trim();
	const filtered = Boolean(
		dates.since ||
			dates.until ||
			filters.flows.length ||
			filters.categories.length ||
			filters.currencies.length ||
			text.length >= 2,
	);
	const query = useBooksListTransactions(book.id, {
		...dates,
		flow: filters.flows.length ? filters.flows : undefined,
		category: filters.categories.length ? filters.categories : undefined,
		q: text.length >= 2 ? text : undefined,
		currency: filters.currencies.length ? filters.currencies : undefined,
		sort: filters.sort,
		page,
		per_page: PER_PAGE,
	});
	const remove = useBooksDeleteTransaction();
	const narrow = useIsNarrow("md");
	const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PER_PAGE));
	const status = query.isError ? "error" : query.isLoading ? "loading" : "ready";
	const emptyTitle = filtered ? t.txFilter.noMatchTitle : t.transactions.emptyTitle;
	const empty = filtered ? t.txFilter.noMatch : t.transactions.empty;

	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.transactions} description={book.name} />
			<FilterBar
				book={book}
				leading={
					<Button className="hidden shrink-0 md:inline-flex" onPress={() => setAdding(true)}>
						<PlusIcon aria-hidden />
						{t.transactions.add}
					</Button>
				}
				value={filters}
				onChange={(next) => {
					setFilters(next);
					setPage(1);
				}}
			/>
			{query.data && filtered ? (
				<p
					className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted"
					aria-live="polite"
				>
					<span>
						{formatAmount(query.data.total)} {t.txFilter.matches}
					</span>
					{Number(query.data.total_income ?? 0) > 0 ? (
						<span>
							{t.txFilter.incomeSum}:{" "}
							<b className="text-success">
								{formatMoney(query.data.total_income ?? "0", book.currency)}
							</b>
						</span>
					) : null}
					{Number(query.data.total_expense ?? 0) > 0 ? (
						<span>
							{t.txFilter.expenseSum}:{" "}
							<b className="text-foreground">
								{formatMoney(query.data.total_expense ?? "0", book.currency)}
							</b>
						</span>
					) : null}
				</p>
			) : null}
			{narrow ? (
				<CompactRows
					book={book}
					rows={query.data?.items}
					status={status}
					onRetry={() => void query.refetch()}
					emptyTitle={emptyTitle}
					empty={empty}
					page={page}
					pageCount={pages}
					onPageChange={setPage}
					onOpen={setOpened}
				/>
			) : (
				<DataTable<TransactionResponse>
					ariaLabel={t.nav.transactions}
					status={status}
					onRetry={() => void query.refetch()}
					rows={query.data?.items}
					getRowId={(row) => row.id}
					emptyTitle={emptyTitle}
					empty={empty}
					columns={[
						{
							id: "category",
							header: t.transactions.category,
							isRowHeader: true,
							className: "w-36",
							cell: (row) => (
								<span className="flex items-center gap-2">
									<button
										type="button"
										className="truncate text-start font-medium hover:underline"
										onClick={() => setOpened(row)}
									>
										{row.category}
									</button>
									{(row.attachment_count ?? 0) > 0 ? (
										<span title={t.attach.clip} className="shrink-0 text-xs text-muted">
											<span aria-hidden>📎</span>
											<span className="sr-only">{t.attach.clip}</span>{" "}
											{formatAmount(row.attachment_count ?? 0)}
										</span>
									) : null}
								</span>
							),
						},
						{
							id: "amount",
							header: t.transactions.amount,
							align: "end",
							className: "w-36",
							cell: (row) => <Amount row={row} book={book} />,
						},
						{
							id: "date",
							header: t.transactions.date,
							className: "w-24 whitespace-nowrap",
							cell: (row) => formatDay(row.occurred_on),
						},
						{
							// One line of the note; the rest is a click away, so the table never grows sideways.
							id: "note",
							header: t.transactions.note,
							cell: (row) =>
								row.description ? (
									<button
										type="button"
										title={row.description}
										className="block w-full max-w-[11rem] truncate text-start text-muted hover:text-foreground xl:max-w-[22rem]"
										onClick={() => setOpened(row)}
									>
										{row.description}
									</button>
								) : (
									<span className="text-muted">—</span>
								),
						},
						{
							id: "actions",
							header: "",
							isActions: true,
							className: "w-32",
							cell: (row) => (
								<div className="flex justify-end gap-1">
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
			{/* A phone's thumb is at the bottom: the main action floats above the tab bar, at the reading start. */}
			<button
				type="button"
				aria-label={t.transactions.add}
				className="fixed bottom-[calc(var(--nasim-bottom-bar,4.5rem)+1rem)] start-4 z-20 flex h-14 items-center gap-2 rounded-full bg-accent px-5 text-sm font-semibold text-accent-foreground shadow-lg md:hidden"
				onClick={() => setAdding(true)}
			>
				<PlusIcon aria-hidden className="size-6" />
				{t.transactions.add}
			</button>
			<TransactionDetail
				book={book}
				row={opened}
				onClose={() => setOpened(null)}
				onEdit={setEditing}
				onRemove={setRemoving}
			/>
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.transactions.add} size="lg">
				<AddForm book={book} onDone={() => setAdding(false)} />
			</Modal>
			<Modal
				isOpen={editing !== null}
				onOpenChange={(open) => !open && setEditing(null)}
				title={t.txExtra.edit}
				size="lg"
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
