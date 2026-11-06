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
import { calendarOf } from "@/shared/format";
import { pickedDay } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { kindOf, monthOptions, type PeriodKind, weekOptions, yearOptions } from "@/shared/periods";
import { t } from "@/strings";

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
	link.download = `kasbbook-${period.replaceAll(":", "-").replaceAll("..", "_to_")}.csv`;
	link.click();
	URL.revokeObjectURL(url);
}

const CUSTOM = "__custom";

export function Reports() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	const [kind, setKind] = useState<PeriodKind>("month");
	// Weeks, months and years are the book's own: a Gregorian book lists Gregorian ones, its week Monday to Sunday.
	const cal = calendarOf(book?.calendar);
	const weeks = weekOptions(7, cal);
	const months = monthOptions(12, cal);
	const years = yearOptions(4, cal);
	const [chosenWeek, setWeek] = useState("");
	const [chosenMonth, setMonth] = useState("");
	const [chosenYear, setYear] = useState("");
	const [from, setFrom] = useState("");
	const [to, setTo] = useState("");
	const pick = (options: { value: string }[], chosen: string) =>
		options.some((option) => option.value === chosen) ? chosen : (options[0]?.value ?? "");
	const week = pick(weeks, chosenWeek);
	const month = pick(months, chosenMonth);
	const year = pick(years, chosenYear);
	if (isLoading) return <PageSkeleton stats={4} />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <BookRequired />;
	const r = t.analytics.reports;
	const start = pickedDay(from);
	const end = pickedDay(to);
	const rangeProblem = start && end && end < start ? r.badRange : undefined;
	const range = start && end && !rangeProblem ? `${start}..${end}` : null;
	const period = kind === "week" ? week : kind === "month" ? month : kind === "year" ? year : range;
	const options = kind === "week" ? weeks : kind === "month" ? months : years;
	const value = kind === "week" ? week : kind === "month" ? month : year;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.reports}
				description={book.name}
				actions={
					period ? (
						<Button variant="secondary" onPress={() => void download(book, period)}>
							{t.reports.export}
						</Button>
					) : undefined
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
						{ value: "custom", label: r.custom },
					]}
				/>
				{kind === "custom" ? null : (
					<select
						aria-label={t.reports.period}
						value={value}
						onChange={(event) => {
							const next = event.target.value;
							// The last choice of every list opens the range of one's own.
							if (next === CUSTOM) return setKind("custom");
							if (kind === "week") setWeek(next);
							else if (kind === "month") setMonth(next);
							else setYear(next);
						}}
						className="h-10 max-w-full rounded-field border border-border bg-surface px-3 text-sm"
					>
						{options.map((item) => (
							<option key={item.value} value={item.value}>
								{item.label}
							</option>
						))}
						<option value={CUSTOM}>{r.customEllipsis}</option>
					</select>
				)}
			</div>
			{kind === "custom" ? (
				<div className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4">
					<div className="grid gap-4 md:grid-cols-2">
						<DayField label={r.from} value={from} onChange={setFrom} />
						<DayField label={r.until} value={to} onChange={setTo} errorMessage={rangeProblem} />
					</div>
					{range ? null : <p className="text-sm text-muted">{r.pickRange}</p>}
				</div>
			) : null}
			{period ? <Body book={book} period={period} /> : null}
		</div>
	);
}
