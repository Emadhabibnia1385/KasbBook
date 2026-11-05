import { useState } from "react";
import { BarTable, Button, ColumnChart, EmptyState, ErrorState, PageHeader, PageSkeleton, SectionCard, StatCard } from "@nyxon/nasim";
import { reportsExportCsv } from "@/api/generated/reports/reports";
import { useReportsByCategory, useReportsDaily, useReportsSummary } from "@/api/generated/reports/reports";
import type { BookResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { formatAmount, formatDay, formatMoney, recentPeriods } from "@/shared/format";
import { t } from "@/strings";

const PERIODS = recentPeriods(12);

function categoryTable(book: BookResponse, title: string, rows: { category: string; total: string; share_percent: string }[]) {
	return (
		<BarTable
			title={title}
			labelHeader={t.dashboard.category}
			valueHeaders={[t.dashboard.amount, t.dashboard.share]}
			empty={t.reports.noData}
			rows={rows.map((row) => ({
				key: row.category,
				label: row.category,
				value: Number(row.total),
				cells: [formatMoney(row.total, book.currency), `${formatAmount(row.share_percent)}٪`],
			}))}
		/>
	);
}

function Body({ book, period }: { book: BookResponse; period: string }) {
	const summary = useReportsSummary(book.id, { period });
	const expense = useReportsByCategory(book.id, { flow: "expense", period });
	const income = useReportsByCategory(book.id, { flow: "income", period });
	const daily = useReportsDaily(book.id, { period });
	const money = (value?: string) => (value === undefined ? "…" : formatMoney(value, book.currency));
	const days = daily.data ?? [];
	const dayChart = (key: "income" | "expense", title: string, tone: "success" | "accent") => (
		<ColumnChart
			title={title}
			tone={tone}
			summary={`${t.reports.daily}: ${title}`}
			empty={t.reports.noData}
			points={days.map((day) => ({
				key: day.on,
				label: formatDay(day.on),
				value: Number(day[key]),
				tooltip: `${formatDay(day.on)}: ${formatMoney(day[key], book.currency)}`,
			}))}
			table={{
				showLabel: t.dashboard.showTable,
				label: `${t.reports.daily}: ${title}`,
				columns: [t.transactions.date, title],
				rows: days.map((day) => ({ key: day.on, cells: [formatDay(day.on), formatMoney(day[key], book.currency)] })),
			}}
		/>
	);
	return (
		<div className="flex flex-col gap-5">
			<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard label={t.common.income} value={money(summary.data?.income)} />
				<StatCard label={t.common.expense} value={money(summary.data?.expense)} />
				<StatCard label={t.common.net} value={money(summary.data?.net)} />
				<StatCard label={t.dashboard.count} value={summary.data ? formatAmount(summary.data.transaction_count) : "…"} hint={t.dashboard.countUnit} />
			</div>
			<SectionCard title={t.reports.daily}>
				<div className="grid gap-6 md:grid-cols-2">
					{dayChart("income", t.common.income, "success")}
					{dayChart("expense", t.common.expense, "accent")}
				</div>
			</SectionCard>
			<div className="grid gap-5 lg:grid-cols-2">
				<SectionCard title={t.reports.expenseByCategory}>{categoryTable(book, t.reports.expenseByCategory, expense.data ?? [])}</SectionCard>
				<SectionCard title={t.reports.incomeByCategory}>{categoryTable(book, t.reports.incomeByCategory, income.data ?? [])}</SectionCard>
			</div>
		</div>
	);
}

// Saves the period as a CSV through the same authenticated request, since a plain link would carry no token.
async function download(book: BookResponse, period: string) {
	const blob = (await reportsExportCsv(book.id, { period })) as unknown as Blob;
	const url = URL.createObjectURL(blob);
	const link = document.createElement("a");
	link.href = url;
	link.download = `kasbbook-${period}.csv`;
	link.click();
	URL.revokeObjectURL(url);
}

export function Reports() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	const [period, setPeriod] = useState(PERIODS[0]?.value ?? "");
	if (isLoading) return <PageSkeleton stats={4} />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.reports}
				description={book.name}
				actions={
					<>
						<select
							aria-label={t.reports.period}
							value={period}
							onChange={(event) => setPeriod(event.target.value)}
							className="h-10 rounded-field border border-border bg-surface px-3 text-sm"
						>
							{PERIODS.map((item) => (
								<option key={item.value} value={item.value}>
									{item.label}
								</option>
							))}
						</select>
						<Button variant="secondary" onPress={() => void download(book, period)}>
							{t.reports.export}
						</Button>
					</>
				}
			/>
			<Body book={book} period={period} />
		</div>
	);
}
