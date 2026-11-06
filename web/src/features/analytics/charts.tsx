import { FilterChips, SectionCard } from "@nyxon/nasim";
import { useState } from "react";
import {
	useAnalyticsCashflow,
	useAnalyticsCategoryMonthly,
	useAnalyticsCompare,
	useAnalyticsCumulative,
	useAnalyticsScopeSplit,
	useAnalyticsTopCategories,
	useAnalyticsWeekday,
} from "@/api/generated/analytics/analytics";
import type { BookResponse } from "@/api/generated/model";
import { useReportsByCategory } from "@/api/generated/reports/reports";
import {
	Bridge,
	type BridgeStep,
	categoryColor,
	color,
	Donut,
	GroupedColumns,
	LineCompare,
	OTHER_COLOR,
	type Slice,
	StackedColumns,
	WeekdayBars,
} from "@/shared/charts";
import { addMoney, negateMoney, subtractMoney } from "@/shared/decimal";
import { calendarOf, formatAmount, formatCompact, formatDay, formatMoney } from "@/shared/format";
import { monthOfDay, type PeriodKind, periodLabel } from "@/shared/periods";
import { t } from "@/strings";
import { Loaded } from "./Loaded";

const money = (book: BookResponse) => (value: string) => formatMoney(value, book.currency);

/** Twelve months of income and expense side by side, with the net as a line across them. */
export function CashflowPanel({ book }: { book: BookResponse }) {
	const cal = calendarOf(book.calendar);
	const query = useAnalyticsCashflow(book.id, { months: 12 });
	const s = t.analytics.series;
	return (
		<SectionCard title={t.analytics.dashboard.cashflowTitle}>
			<Loaded query={query}>
				{(points) => (
					<GroupedColumns
						title={t.analytics.dashboard.cashflowTitle}
						hideTitle
						summary={t.analytics.dashboard.cashflowSummary}
						rowHeader={t.analytics.chart.month}
						formatValue={money(book)}
						rows={points.map((point) => ({
							key: point.period,
							label: point.label,
							title: periodLabel(point.period, cal),
							values: { income: point.income, expense: point.expense, net: point.net },
						}))}
						bars={[
							{ key: "income", name: s.income, color: color.income },
							{ key: "expense", name: s.expense, color: color.expense },
						]}
						lines={[{ key: "net", name: s.net, color: color.net }]}
					/>
				)}
			</Loaded>
		</SectionCard>
	);
}

/** Net so far, day by day, with the previous period's line under it so «ahead or behind» reads at a glance. */
export function CumulativePanel({
	book,
	period,
	title,
}: {
	book: BookResponse;
	period: string;
	title: string;
}) {
	const cal = calendarOf(book.calendar);
	const query = useAnalyticsCumulative(book.id, { period });
	return (
		<SectionCard title={title}>
			<Loaded query={query}>
				{(data) => {
					const now = periodLabel(data.period, cal);
					const before = periodLabel(data.previous_period, cal);
					const latest = (key: "net" | "previous_net") =>
						[...data.days].reverse().find((day) => day[key] != null)?.[key];
					const lastNow = latest("net");
					const lastBefore = latest("previous_net");
					const summary = [
						title,
						lastNow != null ? `${now}: ${formatMoney(lastNow, book.currency)}` : null,
						lastBefore != null ? `${before}: ${formatMoney(lastBefore, book.currency)}` : null,
					]
						.filter(Boolean)
						.join("، ");
					return (
						<LineCompare
							title={title}
							hideTitle
							summary={summary}
							rowHeader={t.analytics.chart.day}
							formatValue={money(book)}
							rows={data.days.map((day) => ({
								key: String(day.day_index),
								label: dayNumber(day.day_index, cal),
								title: `${t.analytics.chart.day} ${dayNumber(day.day_index, cal)}`,
								values: { net: day.net, previous_net: day.previous_net },
							}))}
							series={[
								{ key: "net", name: now, color: color.net, area: true },
								{ key: "previous_net", name: before, color: color.previous, dashed: true },
							]}
						/>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}

/**
 * Income and expense for each day of a week or month, or each month of a year. Read off the cumulative
 * series (the difference between neighbours) so every day appears, quiet ones too, and the page asks once.
 */
export function FlowPanel({
	book,
	period,
	kind,
}: {
	book: BookResponse;
	period: string;
	kind: PeriodKind;
}) {
	const cal = calendarOf(book.calendar);
	const query = useAnalyticsCumulative(book.id, { period });
	const title = kind === "year" ? t.analytics.reports.monthlyTitle : t.analytics.reports.dailyTitle;
	const s = t.analytics.series;
	return (
		<SectionCard title={title}>
			<Loaded query={query}>
				{(data) => {
					const buckets = new Map<
						string,
						{ label: string; title: string; income: string; expense: string }
					>();
					let seenIncome = "0.0000";
					let seenExpense = "0.0000";
					for (const day of data.days) {
						// Days that have not happened yet carry nothing and are not drawn.
						if (day.on == null || day.income == null || day.expense == null) continue;
						const income = subtractMoney(day.income, seenIncome);
						const expense = subtractMoney(day.expense, seenExpense);
						seenIncome = day.income;
						seenExpense = day.expense;
						const month = monthOfDay(day.on, cal);
						const key = kind === "year" ? month.period : day.on;
						const label =
							kind === "year"
								? month.label
								: kind === "month"
									? dayNumber(day.day_index, cal)
									: formatDay(day.on, cal);
						const bucket = buckets.get(key) ?? {
							label,
							title: kind === "year" ? periodLabel(month.period, cal) : formatDay(day.on, cal),
							income: "0.0000",
							expense: "0.0000",
						};
						bucket.income = addMoney(bucket.income, income);
						bucket.expense = addMoney(bucket.expense, expense);
						buckets.set(key, bucket);
					}
					return (
						<GroupedColumns
							title={title}
							hideTitle
							summary={`${t.analytics.reports.dailySummary}: ${periodLabel(data.period, cal)}`}
							rowHeader={kind === "year" ? t.analytics.chart.month : t.transactions.date}
							formatValue={money(book)}
							rows={[...buckets.entries()].map(([key, bucket]) => ({
								key,
								label: bucket.label,
								title: bucket.title,
								values: { income: bucket.income, expense: bucket.expense },
							}))}
							bars={[
								{ key: "income", name: s.income, color: color.income },
								{ key: "expense", name: s.expense, color: color.expense },
							]}
						/>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}

/** The biggest six categories and «سایر» for everything after them. */
export function ExpenseDonutPanel({
	book,
	period,
	title,
}: {
	book: BookResponse;
	period: string;
	title: string;
}) {
	const query = useReportsByCategory(book.id, { flow: "expense", period });
	return (
		<SectionCard title={title}>
			<Loaded query={query}>
				{(lines) => {
					const top = lines.slice(0, 6);
					const rest = lines.slice(6);
					const slices: Slice[] = top.map((line, index) => ({
						key: line.category,
						label: line.category,
						value: line.total,
						color: categoryColor(index),
					}));
					if (rest.length > 0) {
						slices.push({
							key: "other",
							label: t.analytics.chart.other,
							value: addMoney(...rest.map((line) => line.total)),
							color: categoryColor(6),
						});
					}
					const total = addMoney("0", ...lines.map((line) => line.total));
					return (
						<Donut
							title={title}
							hideTitle
							summary={`${title}: ${slices.map((slice) => slice.label).join("، ")}`}
							slices={slices}
							formatValue={money(book)}
							center={{ label: t.common.expense, value: formatCompact(Number(total)) }}
							emptyText={t.dashboard.noCategories}
						/>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}

/** Spending split by whose money it was: work, personal, team. */
export function ScopeDonutPanel({
	book,
	period,
	title,
}: {
	book: BookResponse;
	period: string;
	title: string;
}) {
	const query = useAnalyticsScopeSplit(book.id, { period });
	const names: Record<string, string> = t.analytics.scope;
	return (
		<SectionCard title={title}>
			<Loaded query={query}>
				{(rows) => {
					const slices: Slice[] = rows
						.filter((row) => Number(row.expense) > 0)
						.map((row, index) => ({
							key: row.scope,
							label: names[row.scope] ?? row.scope,
							value: row.expense,
							color: categoryColor(index),
						}));
					const total = addMoney("0", ...slices.map((slice) => slice.value));
					return (
						<Donut
							title={title}
							hideTitle
							summary={`${title}: ${slices.map((slice) => slice.label).join("، ")}`}
							slices={slices}
							formatValue={money(book)}
							center={{ label: t.common.expense, value: formatCompact(Number(total)) }}
							emptyText={t.dashboard.noCategories}
						/>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}

// A day's number in the digits of the book's calendar.
const dayNumber = (n: number, cal: ReturnType<typeof calendarOf>) =>
	cal === "gregorian" ? String(n) : formatAmount(n);

/** Which days of the week the money moves on. Saturday first, as the week runs here. */
export function WeekdayPanel({
	book,
	period,
	title,
}: {
	book: BookResponse;
	period: string;
	title: string;
}) {
	const query = useAnalyticsWeekday(book.id, { period });
	const s = t.analytics.series;
	return (
		<SectionCard title={title}>
			<Loaded query={query}>
				{(days) => {
					const busiest = days.reduce(
						(best, day) => (Number(day.expense) > Number(best.expense) ? day : best),
						days[0],
					);
					const note =
						busiest && Number(busiest.expense) > 0
							? `${t.analytics.weekday.busiest}: ${busiest.label}`
							: t.analytics.weekday.none;
					return (
						<WeekdayBars
							title={title}
							hideTitle
							summary={`${title}. ${note}`}
							note={note}
							rowHeader={t.analytics.chart.day}
							formatValue={money(book)}
							rows={days.map((day) => ({
								key: String(day.index),
								label: day.label,
								values: { income: day.income, expense: day.expense },
							}))}
							bars={[
								{ key: "income", name: s.income, color: color.income },
								{ key: "expense", name: s.expense, color: color.expense },
							]}
						/>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}

/** From income to what is left: each of the biggest costs takes a step down. */
export function BridgePanel({ book, period }: { book: BookResponse; period: string }) {
	const compare = useAnalyticsCompare(book.id, { period });
	const top = useAnalyticsTopCategories(book.id, { period, flow: "expense", limit: 5 });
	const title = t.analytics.reports.bridgeTitle;
	return (
		<SectionCard title={title}>
			<Loaded query={compare}>
				{(figures) => (
					<Loaded query={top}>
						{(categories) => {
							const named = categories.map((category) => category.current);
							const rest = subtractMoney(figures.current.expense, addMoney("0", ...named));
							const steps: BridgeStep[] = [
								{
									key: "income",
									label: t.analytics.series.income,
									amount: figures.current.income,
									kind: "income",
								},
								...categories.map((category) => ({
									key: category.category,
									label: category.category,
									amount: negateMoney(category.current),
									kind: "expense" as const,
								})),
								...(Number(rest) > 0
									? [
											{
												key: "other",
												label: t.analytics.chart.other,
												amount: negateMoney(rest),
												kind: "expense" as const,
											},
										]
									: []),
								{
									key: "net",
									label: t.analytics.reports.bridgeTotal,
									amount: figures.current.net,
									kind: "total",
								},
							];
							return (
								<Bridge
									title={title}
									hideTitle
									summary={t.analytics.reports.bridgeSummary}
									steps={steps}
									formatValue={money(book)}
								/>
							);
						}}
					</Loaded>
				)}
			</Loaded>
		</SectionCard>
	);
}

/** Each month cut into the categories that made it up: which cost grew, and which one only looked big. */
export function CategoryMonthlyPanel({ book }: { book: BookResponse }) {
	const [flow, setFlow] = useState<"expense" | "income">("expense");
	const cal = calendarOf(book.calendar);
	const query = useAnalyticsCategoryMonthly(book.id, { months: 6, flow, top: 5 });
	const a = t.analytics.dashboard;
	return (
		<SectionCard title={a.categoryMonthlyTitle}>
			<div className="mb-3">
				<FilterChips
					label={a.categoryMonthlyFlow}
					value={flow}
					onChange={(value) => setFlow(value as typeof flow)}
					options={[
						{ value: "expense", label: t.common.expense },
						{ value: "income", label: t.common.income },
					]}
				/>
			</div>
			<Loaded query={query}>
				{(data) => {
					// One part per category name, in the order they first appear, with «سایر» always last and grey.
					const names: { name: string; other: boolean }[] = [];
					for (const month of data.months)
						for (const segment of month.segments)
							if (!names.some((known) => known.name === segment.category))
								names.push({ name: segment.category, other: Boolean(segment.is_other) });
					names.sort((left, right) => Number(left.other) - Number(right.other));
					return (
						<StackedColumns
							title={a.categoryMonthlyTitle}
							hideTitle
							summary={a.categoryMonthlySummary}
							rowHeader={t.analytics.chart.month}
							formatValue={money(book)}
							total={{ key: "total", name: a.categoryMonthlyTotal }}
							parts={names.map((entry, index) => ({
								key: entry.name,
								name: entry.name,
								color: entry.other ? OTHER_COLOR : categoryColor(index),
							}))}
							rows={data.months.map((month) => ({
								key: month.period,
								label: month.label,
								title: periodLabel(month.period, cal),
								values: {
									...Object.fromEntries(
										month.segments.map((segment) => [segment.category, segment.amount]),
									),
									total: month.total,
								},
							}))}
						/>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}
