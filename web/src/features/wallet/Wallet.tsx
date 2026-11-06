import { BookRequired } from "@/features/books/BookRequired";
import { EmptyState, ErrorState, PageHeader, PageSkeleton, SectionCard } from "@nyxon/nasim";
import { useBooksListCurrencies, useBooksWallet } from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { formatMoney } from "@/shared/format";
import { t } from "@/strings";
import { Conversions } from "./Conversions";

function Balances({ book }: { book: BookResponse }) {
	const { data = [], isLoading, isError, refetch } = useBooksWallet(book.id);
	if (isLoading) return <PageSkeleton header={false} rows={2} />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!data.length) return <EmptyState title={t.wallet.noBalances} />;
	return (
		<ul className="grid gap-3 sm:grid-cols-2">
			{data.map((row) => (
				<li
					key={row.code}
					className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-surface p-4"
				>
					<span className="flex flex-col">
						<span className="font-medium">{row.name}</span>
						{row.is_base ? <span className="text-xs text-muted">{t.wallet.base}</span> : null}
					</span>
					<span className="text-lg font-semibold">{formatMoney(row.amount, row.code)}</span>
				</li>
			))}
		</ul>
	);
}

function Content({ book }: { book: BookResponse }) {
	const currencies = useBooksListCurrencies(book.id);
	const options = currencies.data ?? [];
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.wallet.title} description={book.name} />
			<SectionCard title={t.wallet.balances} description={t.wallet.balancesHint}>
				<Balances book={book} />
			</SectionCard>
			<SectionCard title={t.wallet.conversions}>
				<Conversions book={book} options={options} />
			</SectionCard>
			<p className="text-sm text-muted">{t.wallet.unitsMoved}</p>
		</div>
	);
}

export function Wallet() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <BookRequired />;
	return <Content book={book} />;
}
