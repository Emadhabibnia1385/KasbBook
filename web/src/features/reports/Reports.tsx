import { BookRequired } from "@/features/books/BookRequired";
import { useState } from "react";
import { Button, ErrorState, FilterChips, PageHeader, PageSkeleton } from "@nyxon/nasim";
import { reportsExportCsv } from "@/api/generated/reports/reports";
import type { BookResponse } from "@/api/generated/model";
import {
	BridgePanel,
	CategoryMonthlyPanel,
	CumulativePanel,
	ExpenseDonutPanel,
	FlowPanel,
	ScopeDonutPanel,
	WeekdayPanel,
} from "@/features/analytics/charts";
import { CompareCards } from "@/features/analytics/kpis";
import { TopCategories } from "@/features/analytics/tables";
import { useActiveBook } from "@/features/books/useActiveBook";
import { kindOf, monthOptions, type PeriodKind, yearOptions } from "@/shared/periods";
import { t } from "@/strings";

const MONTHS = monthOptions(12);
const YEARS = yearOptions(4);

function Body({ book, period }: { book: BookResponse; period: string }) {
	const r = t.analytics.reports;
	const kind = kindOf(period);
	return (
		<div className="flex flex-col gap-5">
			<CompareCards book={book} period={period} />
			<FlowPanel book={book} period={period} kind={kind} />
			<CategoryMonthlyPanel book={book} />
			<div className="grid gap-5 lg:grid-cols-2">
				<CumulativePanel book={book} period={period} title={r.cumulativeTitle} />
				<BridgePanel book={book} period={period} />
			</div>
			<div className="grid gap-5 lg:grid-cols-2">
				<ExpenseDonutPanel book={book} period={period} title={r.categoryDonutTitle} />
				<ScopeDonutPanel book={book} period={period} title={r.scopeTitle} />
			</div>
			<WeekdayPanel book={book} period={period} title={r.weekdayTitle} />
			<div className="grid gap-5 lg:grid-cols-2">
				<TopCategories book={book} period={period} flow="expense" title={r.topExpense} limit={12} />
				<TopCategories book={book} period={period} flow="income" title={r.topIncome} limit={12} />
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
	const [kind, setKind] = useState<PeriodKind>("month");
	const [month, setMonth] = useState(MONTHS[0]?.value ?? "");
	const [year, setYear] = useState(YEARS[0]?.value ?? "");
	if (isLoading) return <PageSkeleton stats={4} />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <BookRequired />;
	const period = kind === "week" ? "week" : kind === "month" ? month : year;
	const options = kind === "month" ? MONTHS : YEARS;
	const r = t.analytics.reports;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.reports}
				description={book.name}
				actions={
					<Button variant="secondary" onPress={() => void download(book, period)}>
						{t.reports.export}
					</Button>
				}
			/>
			<div className="flex flex-wrap items-center gap-3">
				<FilterChips
					label={r.kind}
					value={kind}
					onChange={(next) => setKind(next as PeriodKind)}
					options={[
						{ value: "week", label: r.week },
						{ value: "month", label: r.month },
						{ value: "year", label: r.year },
					]}
				/>
				{kind === "week" ? null : (
					<select
						aria-label={t.reports.period}
						value={kind === "month" ? month : year}
						onChange={(event) =>
							kind === "month" ? setMonth(event.target.value) : setYear(event.target.value)
						}
						className="h-10 rounded-field border border-border bg-surface px-3 text-sm"
					>
						{options.map((item) => (
							<option key={item.value} value={item.value}>
								{item.label}
							</option>
						))}
					</select>
				)}
			</div>
			<Body book={book} period={period} />
		</div>
	);
}
