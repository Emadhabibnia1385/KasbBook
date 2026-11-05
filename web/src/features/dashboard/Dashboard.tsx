import { Link } from "@tanstack/react-router";
import { BarTable, ColumnChart, EmptyState, ErrorState, PageHeader, PageSkeleton, SectionCard, StaticTable, StatCard } from "@nyxon/nasim";
import { useBooksListTransactions } from "@/api/generated/books/books";
import { useReportsByCategory, useReportsMonthly, useReportsSummary } from "@/api/generated/reports/reports";
import type { BookResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { currentPeriod, formatAmount, formatDay, formatMoney } from "@/shared/format";
import { t } from "@/strings";

function Figures({ book }: { book: BookResponse }) {
	const period = currentPeriod();
	const { data: summary } = useReportsSummary(book.id, { period });
	const money = (value: string | undefined) => (value === undefined ? "…" : formatMoney(value, book.currency));
	return (
		<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
			<StatCard label={t.dashboard.income} value={money(summary?.income)} />
			<StatCard label={t.dashboard.expense} value={money(summary?.expense)} />
			<StatCard label={t.dashboard.net} value={money(summary?.net)} />
			<StatCard
				label={t.dashboard.count}
				value={summary ? formatAmount(summary.transaction_count) : "…"}
				hint={t.dashboard.countUnit}
			/>
		</div>
	);
}

function Trend({ book }: { book: BookResponse }) {
	const { data } = useReportsMonthly(book.id, { months: 6 });
	const rows = data ?? [];
	const chart = (key: "income" | "expense", title: string, tone: "success" | "accent") => (
		<ColumnChart
			title={title}
			tone={tone}
			summary={`${t.dashboard.trendSummary}: ${title}`}
			empty={t.dashboard.trendEmpty}
			points={rows.map((row) => ({
				key: row.period,
				label: row.label,
				value: Number(row[key]),
				tooltip: `${row.label}: ${formatMoney(row[key], book.currency)}`,
			}))}
			table={{
				showLabel: t.dashboard.showTable,
				label: t.dashboard.tableLabel,
				columns: [t.dashboard.month, title],
				rows: rows.map((row) => ({ key: row.period, cells: [row.label, formatMoney(row[key], book.currency)] })),
			}}
		/>
	);
	return (
		<SectionCard title={t.dashboard.trendTitle}>
			<div className="grid gap-6 md:grid-cols-2">
				{chart("income", t.common.income, "success")}
				{chart("expense", t.common.expense, "accent")}
			</div>
		</SectionCard>
	);
}

function Categories({ book }: { book: BookResponse }) {
	const { data } = useReportsByCategory(book.id, { flow: "expense", period: currentPeriod() });
	const rows = data ?? [];
	return (
		<SectionCard title={t.dashboard.categoriesTitle}>
			<BarTable
				title={t.dashboard.categoriesTitle}
				hideTitle
				labelHeader={t.dashboard.category}
				valueHeaders={[t.dashboard.amount, t.dashboard.share]}
				empty={t.dashboard.noCategories}
				rows={rows.map((row) => ({
					key: row.category,
					label: row.category,
					value: Number(row.total),
					cells: [formatMoney(row.total, book.currency), `${formatAmount(row.share_percent)}٪`],
				}))}
			/>
		</SectionCard>
	);
}

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

export function Dashboard() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton stats={4} />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.dashboard.title} description={book.name} />
			<Figures book={book} />
			<Trend book={book} />
			<div className="grid gap-5 lg:grid-cols-2">
				<Categories book={book} />
				<Recent book={book} />
			</div>
		</div>
	);
}
