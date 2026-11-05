import { RatesCard } from "@/features/market/RatesCard";
import { Collapsible, useIsNarrow } from "@nyxon/nasim";
import { Link } from "@tanstack/react-router";
import {
	EmptyState,
	ErrorState,
	PageHeader,
	PageSkeleton,
	SectionCard,
	StaticTable,
} from "@nyxon/nasim";
import { useBooksListTransactions } from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import {
	CashflowPanel,
	CumulativePanel,
	ExpenseDonutPanel,
	ScopeDonutPanel,
	WeekdayPanel,
} from "@/features/analytics/charts";
import { KpiRow, OverviewRow } from "@/features/analytics/kpis";
import { BudgetGauges, TopCategories } from "@/features/analytics/tables";
import { useActiveBook } from "@/features/books/useActiveBook";
import { currentPeriod, formatDay, formatMoney } from "@/shared/format";
import { t } from "@/strings";

function Recent({ book }: { book: BookResponse }) {
	const { data } = useBooksListTransactions(book.id, { per_page: 6 });
	const items = data?.items ?? [];
	return (
		<SectionCard
			title={t.dashboard.recent}
			actions={
				<Link to="/transactions" className="text-sm text-accent">
					{t.dashboard.seeAll}
				</Link>
			}
		>
			{items.length === 0 ? (
				<p className="text-sm text-muted">{t.dashboard.noRecent}</p>
			) : (
				<StaticTable
					caption={t.dashboard.recent}
					columns={[t.dashboard.category, t.dashboard.amount, ""]}
					rows={items.map((tx) => ({
						id: tx.id,
						cells: [
							tx.category,
							<span key="a" className={tx.flow === "income" ? "text-success" : undefined}>
								{tx.flow === "income" ? "+" : "−"}
								{formatMoney(tx.converted_amount, book.currency)}
							</span>,
							formatDay(tx.occurred_on),
						],
					}))}
				/>
			)}
		</SectionCard>
	);
}

// On a phone the secondary charts fold under one heading, so the screen is the figures, the year's
// shape and the latest entries; a desktop shows everything as before.
function MoreCharts({ children }: { children: React.ReactNode }) {
	const narrow = useIsNarrow("md");
	if (!narrow) return <>{children}</>;
	return (
		<Collapsible title={t.dashboard.moreCharts}>
			<div className="flex flex-col gap-5 pt-3">{children}</div>
		</Collapsible>
	);
}

export function Dashboard() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton stats={4} />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book)
		return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	const period = currentPeriod();
	const a = t.analytics.dashboard;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.dashboard.title}
				description={book.name}
				actions={
					<Link to="/reports" className="text-sm text-accent">
						{a.details}
					</Link>
				}
			/>
			<KpiRow book={book} period={period} />
			<OverviewRow book={book} period={period} />
			<CashflowPanel book={book} />
			<div className="grid gap-5 lg:grid-cols-2">
				<CumulativePanel book={book} period={period} title={a.cumulativeTitle} />
				<ExpenseDonutPanel book={book} period={period} title={a.categoryDonutTitle} />
			</div>
			<MoreCharts>
				<BudgetGauges book={book} period={period} />
				<div className="grid gap-5 lg:grid-cols-2">
					<WeekdayPanel book={book} period={period} title={a.weekdayTitle} />
					<ScopeDonutPanel book={book} period={period} title={a.scopeTitle} />
				</div>
			</MoreCharts>
			<div className="grid gap-5 lg:grid-cols-2">
				<TopCategories book={book} period={period} flow="expense" title={a.topTitle} />
				<Recent book={book} />
				<RatesCard />
			</div>
		</div>
	);
}
