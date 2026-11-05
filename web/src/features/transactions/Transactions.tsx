import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	DataTable,
	EmptyState,
	FormRoot,
	Modal,
	PageHeader,
	RadioGroupField,
	StatusChip,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getBooksListTransactionsQueryKey,
	useBooksDeleteTransaction,
	useBooksListTransactions,
	useBooksRecordTransaction,
} from "@/api/generated/books/books";
import type { BookResponse, TransactionResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { formatDay, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";

const PER_PAGE = 20;

const schema = z.object({
	flow: z.enum(["income", "expense"]),
	amount: z
		.string()
		.transform(toAscii)
		.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, { error: t.transactions.badAmount }),
	category: z.string().trim().min(1, { error: t.transactions.needCategory }).max(80),
	description: z.string().max(300),
});
type Values = z.input<typeof schema>;

function AddForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const record = useBooksRecordTransaction();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { flow: "expense", amount: "", category: "", description: "" },
	});
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
							scope: book.type === "personal" ? "personal" : book.type === "business" ? "work" : "team",
							category: values.category,
							amount: values.amount,
							description: values.description || null,
						},
					});
					await queryClient.invalidateQueries({ queryKey: getBooksListTransactionsQueryKey(book.id) });
					await queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).includes("/reports/") });
					toast.success(t.transactions.saved);
					onDone();
				} catch (error) {
					toast.danger(error instanceof Error ? error.message : t.errors.unknown);
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
			<TextField name="amount" label={t.transactions.amount} inputMode="decimal" dir="ltr" isRequired />
			<TextField name="category" label={t.transactions.category} isRequired />
			<TextField name="description" label={t.transactions.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function List({ book }: { book: BookResponse }) {
	const [page, setPage] = useState(1);
	const [adding, setAdding] = useState(false);
	const [removing, setRemoving] = useState<TransactionResponse | null>(null);
	const queryClient = useQueryClient();
	const query = useBooksListTransactions(book.id, { page, per_page: PER_PAGE });
	const remove = useBooksDeleteTransaction();
	const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PER_PAGE));

	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.transactions}
				description={book.name}
				actions={<Button onPress={() => setAdding(true)}>{t.transactions.add}</Button>}
			/>
			<DataTable<TransactionResponse>
				ariaLabel={t.nav.transactions}
				cards="md"
				status={query.isError ? "error" : query.isLoading ? "loading" : "ready"}
				onRetry={() => void query.refetch()}
				rows={query.data?.items}
				getRowId={(row) => row.id}
				emptyTitle={t.transactions.emptyTitle}
				empty={t.transactions.empty}
				columns={[
					{ id: "category", header: t.transactions.category, isRowHeader: true, cell: (row) => row.category },
					{
						id: "amount",
						header: t.transactions.amount,
						align: "end",
						cell: (row) => (
							<span className={row.flow === "income" ? "text-success" : undefined}>
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
							<Button size="sm" variant="ghost" onPress={() => setRemoving(row)}>
								{t.common.delete}
							</Button>
						),
					},
				]}
				pagination={{ page, pageCount: pages, onPageChange: setPage }}
			/>
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.transactions.add} size="sm">
				<AddForm book={book} onDone={() => setAdding(false)} />
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
					await remove.mutateAsync({ bookId: book.id, transactionId: removing.id });
					await queryClient.invalidateQueries({ queryKey: getBooksListTransactionsQueryKey(book.id) });
					await queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).includes("/reports/") });
				}}
			/>
		</div>
	);
}

export function Transactions() {
	const { book, isLoading } = useActiveBook();
	if (isLoading) return null;
	if (!book) return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return <List book={book} />;
}
