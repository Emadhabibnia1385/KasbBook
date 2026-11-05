import { keepPreviousData } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
	DataTable,
	EmptyState,
	ErrorState,
	PageHeader,
	PageSkeleton,
	SearchBox,
	StatusChip,
} from "@nyxon/nasim";
import { useReportsSearch } from "@/api/generated/reports/reports";
import type { BookResponse, TransactionResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { formatAmount, formatDay, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";

const PER_PAGE = 20;
// The service matches nothing under two characters, so asking sooner would only spend a request.
const MIN_LENGTH = 2;

// The box is typed into freely; the request waits for a pause.
function useDebounced(value: string, delay = 300): string {
	const [settled, setSettled] = useState(value);
	useEffect(() => {
		const timer = setTimeout(() => setSettled(value), delay);
		return () => clearTimeout(timer);
	}, [value, delay]);
	return settled;
}

function Results({ book }: { book: BookResponse }) {
	const [text, setText] = useState("");
	const [page, setPage] = useState(1);
	const q = toAscii(useDebounced(text)).trim();
	const ready = q.length >= MIN_LENGTH;
	const query = useReportsSearch(
		book.id,
		{ q, page, per_page: PER_PAGE },
		{ query: { enabled: ready, placeholderData: keepPreviousData } },
	);
	const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PER_PAGE));

	return (
		<div className="flex flex-col gap-4">
			<PageHeader title={t.search.title} description={book.name} />
			<SearchBox
				label={t.search.label}
				placeholder={t.search.placeholder}
				value={text}
				onChange={(value) => {
					setText(value);
					setPage(1);
				}}
			/>
			{!ready ? (
				<p className="text-sm text-muted">{t.search.hint}</p>
			) : query.isError ? (
				<ErrorState onRetry={() => void query.refetch()} />
			) : query.isLoading ? (
				<PageSkeleton header={false} rows={4} />
			) : (
				<>
					{query.data && query.data.total > 0 ? (
						<p className="text-sm text-muted">
							{formatAmount(query.data.total)} {t.search.found} · {t.search.totalAmount}:{" "}
							{formatMoney(query.data.total_amount, book.currency)}
						</p>
					) : null}
					<DataTable<TransactionResponse>
						ariaLabel={t.search.title}
						cards="md"
						status="ready"
						rows={query.data?.items}
						getRowId={(row) => row.id}
						emptyTitle={t.search.none}
						empty={t.search.noneBody}
						columns={[
							{
								id: "category",
								header: t.search.category,
								isRowHeader: true,
								cell: (row) => row.category,
							},
							{
								id: "amount",
								header: t.search.amount,
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
								header: t.search.kind,
								cell: (row) => (
									<StatusChip
										tone={row.flow === "income" ? "success" : "neutral"}
										label={row.flow === "income" ? t.common.income : t.common.expense}
									/>
								),
							},
							{ id: "date", header: t.search.date, cell: (row) => formatDay(row.occurred_on) },
							{ id: "note", header: t.search.note, cell: (row) => row.description ?? "—" },
						]}
						pagination={{ page, pageCount: pages, onPageChange: setPage }}
					/>
				</>
			)}
		</div>
	);
}

export function Search() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book)
		return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return <Results book={book} />;
}
