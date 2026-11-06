import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	DataTable,
	EmptyState,
	FormRoot,
	Modal,
	PageHeader,
	SubmitButton,
	TextField,
	toast,
	useIsNarrow,
} from "@nyxon/nasim";
import { useBooksDeleteTransaction, useBooksEditTransaction } from "@/api/generated/books/books";
import type { BookedTransactionResponse, BookResponse } from "@/api/generated/model";
import { useTransactionsListAllTransactions } from "@/api/generated/transactions/transactions";
import { useActiveBook } from "@/features/books/useActiveBook";
import { openQuick } from "@/features/quick/quickBus";
import { PendingRecurring } from "@/features/recurring/PendingRecurring";
import { RulesDialog } from "@/features/recurring/RulesDialog";
import { pickedDay, toPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { formatAmount, formatDay, formatMoney, toAscii } from "@/shared/format";
import { PlusIcon } from "@/shared/icons";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { Amount } from "./Amount";
import { AttachmentsField } from "./AttachmentsField";
import { CompactRows } from "./CompactRows";
import { FilterBar } from "./FilterBar";
import { type Filters, NO_FILTERS, rangeDates } from "./filters";
import { BookField, CategoryField, FlowSwitch } from "./FormControls";
import { MoneyFields } from "./MoneyFields";
import { amountRule } from "./rules";
import { TransactionDetail } from "./TransactionDetail";

const PER_PAGE = 20;

const editSchema = z.object({
	book_id: z.string().min(1),
	flow: z.enum(["income", "expense"]),
	currency: z.string(),
	rate: z.string().transform(toAscii),
	amount: amountRule,
	category: z.string().trim().min(1, { error: t.transactions.needCategory }).max(80),
	description: z.string().max(300),
	occurred_on: z.string().min(1, { error: t.days.needDate }),
});
type EditValues = z.input<typeof editSchema>;

/** "300000.0000" → "300000"; a rate keeps what places it has, so a small one is not rounded away. */
function plainRate(value: string): string {
	return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

function plainAmount(value: string): string {
	return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

function EditForm({
	books,
	row,
	onDone,
}: {
	/** Where this entry may go: the books with its own unit, itself included. */
	books: BookResponse[];
	row: BookedTransactionResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const edit = useBooksEditTransaction();
	const form = useForm<EditValues>({
		resolver: zodResolver(editSchema),
		defaultValues: {
			book_id: row.book_id,
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
	const targetId = useWatch({ control: form.control, name: "book_id" });
	// The book it is going to: its categories and currencies are the ones on offer.
	const book = books.find((b) => b.id === targetId) ?? {
		id: row.book_id,
		currency: row.book_currency,
	};
	// Another book has its own categories: the one picked for the last is not carried over.
	const seen = useRef(row.book_id);
	useEffect(() => {
		if (book.id === seen.current) return;
		seen.current = book.id;
		form.setValue("category", "");
	}, [book.id, form]);
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
				if (values.book_id !== row.book_id) changes.book_id = values.book_id;
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
					await edit.mutateAsync({ bookId: row.book_id, transactionId: row.id, data: changes });
					await Promise.all([
						refreshMoney(queryClient, row.book_id),
						changes.book_id ? refreshMoney(queryClient, changes.book_id) : null,
					]);
					toast.success(t.txExtra.editSaved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<div className="flex flex-col gap-4">
				<BookField name="book_id" books={books} label={t.scope.book} />
				<FlowSwitch name="flow" />
				<MoneyFields
					key={book.id}
					book={book}
					initialCurrency={row.original_currency}
					initialRate={plainRate(row.conversion_rate)}
				/>
				<CategoryField
					key={book.id}
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
				<AttachmentsField
					bookId={row.book_id}
					transactionId={row.id}
					queue={[]}
					onQueue={() => {}}
				/>
			</div>
			<div className="md:col-span-2">
				<SubmitButton>{t.common.save}</SubmitButton>
			</div>
		</FormRoot>
	);
}

function List({ books, book }: { books: BookResponse[]; book: BookResponse | undefined }) {
	const [page, setPage] = useState(1);
	const [opened, setOpened] = useState<BookedTransactionResponse | null>(null);
	const [editing, setEditing] = useState<BookedTransactionResponse | null>(null);
	const [removing, setRemoving] = useState<BookedTransactionResponse | null>(null);
	const [filters, setFilters] = useState<Filters>(NO_FILTERS);
	const queryClient = useQueryClient();
	const [rulesOpen, setRulesOpen] = useState(false);
	// One chosen book narrows the list to it; otherwise it is every book's.
	const scope = book ? [book] : books;
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
	const query = useTransactionsListAllTransactions({
		...dates,
		book_id: book ? [book.id] : undefined,
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
	const showBook = !book;
	// An entry can only move to a book with the same unit, so that is all the edit form offers.
	const sameUnit = (row: BookedTransactionResponse) =>
		books.filter((candidate) => candidate.currency === row.book_currency);

	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.transactions}
				description={book ? book.name : t.scope.allBooks}
				actions={
					<Button size="sm" variant="ghost" onPress={() => setRulesOpen(true)}>
						{t.repeat.rules}
					</Button>
				}
			/>
			<PendingRecurring book={book} />
			<FilterBar
				books={scope}
				leading={
					<Button
						className="hidden shrink-0 md:inline-flex"
						onPress={() => openQuick("transaction")}
					>
						<PlusIcon aria-hidden />
						{t.transactions.add}
					</Button>
				}
				below={
					<Button className="w-full" onPress={() => openQuick("transaction")}>
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
				<section
					aria-live="polite"
					aria-label={t.txFilter.summary}
					className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4"
				>
					<p className="text-sm font-medium">
						{formatAmount(query.data.total)} {t.txFilter.matches}
					</p>
					{query.data.totals.map((line) => (
						<dl
							key={line.currency}
							className="grid grid-cols-2 gap-3 border-t border-separator pt-3 first:border-t-0 first:pt-0"
						>
							<div className="flex min-w-0 flex-col gap-0.5">
								<dt className="text-xs text-muted">{t.txFilter.incomeSum}</dt>
								<dd className="font-semibold text-success">
									{formatMoney(line.income, line.currency)}
								</dd>
							</div>
							<div className="flex min-w-0 flex-col gap-0.5">
								<dt className="text-xs text-muted">{t.txFilter.expenseSum}</dt>
								<dd className="font-semibold">{formatMoney(line.expense, line.currency)}</dd>
							</div>
						</dl>
					))}
				</section>
			) : null}
			{narrow ? (
				<CompactRows
					showBook={showBook}
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
				<DataTable<BookedTransactionResponse>
					ariaLabel={t.nav.transactions}
					status={status}
					onRetry={() => void query.refetch()}
					rows={query.data?.items}
					getRowId={(row) => row.id}
					emptyTitle={emptyTitle}
					empty={empty}
					columns={[
						...(showBook
							? [
									{
										id: "book",
										header: t.scope.book,
										align: "center" as const,
										className: "w-28",
										cell: (row: BookedTransactionResponse) => (
											<bdi className="block truncate text-center text-sm font-medium">
												{row.book_name}
											</bdi>
										),
									},
								]
							: []),
						{
							id: "category",
							header: t.transactions.category,
							align: "center",
							isRowHeader: true,
							className: "w-36",
							cell: (row) => (
								<span className="flex min-w-0 flex-col items-center">
									<span className="flex items-center justify-center gap-2">
										<button
											type="button"
											className="truncate text-center font-medium hover:underline"
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
								</span>
							),
						},
						{
							id: "amount",
							header: t.transactions.amount,
							align: "center",
							className: "w-36",
							cell: (row) => (
								<Amount
									row={row}
									book={{ id: row.book_id, currency: row.book_currency }}
									align="center"
								/>
							),
						},
						{
							id: "date",
							header: t.transactions.date,
							align: "center",
							className: "w-24 whitespace-nowrap",
							cell: (row) => formatDay(row.occurred_on),
						},
						{
							// One line of the note; the rest is a click away, so the table never grows sideways.
							id: "note",
							header: t.transactions.note,
							align: "center",
							cell: (row) =>
								row.description ? (
									<button
										type="button"
										title={row.description}
										className="mx-auto block w-full max-w-[11rem] truncate text-center text-muted hover:text-foreground xl:max-w-[22rem]"
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
							align: "center",
							isActions: true,
							className: "w-32",
							cell: (row) => (
								<div className="flex justify-center gap-1">
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
			<RulesDialog books={scope} isOpen={rulesOpen} onOpenChange={setRulesOpen} />
			<TransactionDetail
				row={opened}
				onClose={() => setOpened(null)}
				onEdit={setEditing}
				onRemove={setRemoving}
			/>
			<Modal
				isOpen={editing !== null}
				onOpenChange={(open) => !open && setEditing(null)}
				title={t.txExtra.edit}
				size="lg"
			>
				{editing ? (
					<EditForm
						key={editing.id}
						books={sameUnit(editing)}
						row={editing}
						onDone={() => setEditing(null)}
					/>
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
						await remove.mutateAsync({ bookId: removing.book_id, transactionId: removing.id });
						await refreshMoney(queryClient, removing.book_id);
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
	const { books, book, isLoading } = useActiveBook();
	if (isLoading) return null;
	if (books.length === 0)
		return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return <List books={books} book={book} />;
}
