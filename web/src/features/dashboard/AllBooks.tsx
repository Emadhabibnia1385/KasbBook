import { DayPair } from "@/shared/DayPair";
import { Link } from "@tanstack/react-router";
import { useQueries } from "@tanstack/react-query";
import { SectionCard, StaticTable, StatCard } from "@nyxon/nasim";
import {
	analyticsCashflow,
	analyticsCompare,
	getAnalyticsCashflowQueryKey,
	getAnalyticsCompareQueryKey,
} from "@/api/generated/analytics/analytics";
import type { BookResponse } from "@/api/generated/model";
import { reportsByCategory, getReportsByCategoryQueryKey } from "@/api/generated/reports/reports";
import { useTransactionsListAllTransactions } from "@/api/generated/transactions/transactions";
import { Loaded } from "@/features/analytics/Loaded";
import { selectBook } from "@/features/books/useActiveBook";
import { useQuotes } from "@/features/market/useQuotes";
import { RatesCard, CountryRates } from "@/features/market/RatesCard";
import {
	categoryColor,
	color,
	DeltaChip,
	Donut,
	GroupedColumns,
	OTHER_COLOR,
	type Slice,
} from "@/shared/charts";
import {
	calendarOf,
	currencyName,
	currentPeriod,
	formatAmount,
	formatCompact,
	formatMoney,
} from "@/shared/format";
import { periodLabel } from "@/shared/periods";
import { t } from "@/strings";

// Books can keep different units. Their figures are brought into the most common one at today's approximate
// rate, and a book whose rate nobody can give is left out of the totals and named, rather than added as if
// its numbers were the same money.
function useUnits(books: BookResponse[]) {
	const counts = new Map<string, number>();
	for (const book of books) counts.set(book.currency, (counts.get(book.currency) ?? 0) + 1);
	const unit = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "IRT";
	const others = [...counts.keys()].filter((code) => code !== unit);
	const quotes = useQuotes(others, unit, others.length > 0);
	const worth = new Map((quotes.data ?? []).map((q) => [q.code, Number(q.value)]));
	const factor = (code: string): number | null => (code === unit ? 1 : (worth.get(code) ?? null));
	return { unit, factor, converted: others.length > 0 };
}

type Row = { book: BookResponse; rate: number | null };

// Each book's current month is by its own calendar, so a Jalali and a Gregorian book are each asked about theirs.
const periodFor = (book: BookResponse) => currentPeriod(calendarOf(book.calendar));

export function AllBooksDashboard({ books }: { books: BookResponse[] }) {
	const { unit, factor, converted } = useUnits(books);
	const sameCalendar = new Set(books.map((book) => calendarOf(book.calendar))).size <= 1;
	const rows: Row[] = books.map((book) => ({ book, rate: factor(book.currency) }));
	const skipped = rows.filter((row) => row.rate === null);
	const money = (value: number) => formatMoney(String(Math.round(value)), unit);
	const scale = (row: Row, value: string) => Number(value) * (row.rate ?? 0);

	const compares = useQueries({
		queries: books.map((book) => ({
			queryKey: getAnalyticsCompareQueryKey(book.id, { period: periodFor(book) }),
			queryFn: () => analyticsCompare(book.id, { period: periodFor(book) }),
		})),
	});
	const cashflows = useQueries({
		queries: books.map((book) => ({
			queryKey: getAnalyticsCashflowQueryKey(book.id, { months: 12 }),
			queryFn: () => analyticsCashflow(book.id, { months: 12 }),
		})),
	});
	const categories = useQueries({
		queries: books.map((book) => ({
			queryKey: getReportsByCategoryQueryKey(book.id, { flow: "expense", period: periodFor(book) }),
			queryFn: () => reportsByCategory(book.id, { flow: "expense", period: periodFor(book) }),
		})),
	});
	const recent = useTransactionsListAllTransactions({ per_page: 6, sort: "newest" });

	const ready = compares.every((q) => q.data !== undefined);
	let income = 0;
	let expense = 0;
	let previousIncome = 0;
	let previousExpense = 0;
	let count = 0;
	rows.forEach((row, index) => {
		const data = compares[index]?.data;
		if (!data || row.rate === null) return;
		income += scale(row, data.current.income);
		expense += scale(row, data.current.expense);
		previousIncome += scale(row, data.previous.income);
		previousExpense += scale(row, data.previous.expense);
		count += data.current.transaction_count;
	});
	const net = income - expense;
	const change = (now: number, before: number) => ({
		percent: before === 0 ? null : (((now - before) / before) * 100).toFixed(0),
		absolute: String(now - before),
	});
	const previousLabel = compares.find((q) => q.data)?.data?.previous_period;
	const here = (value: number) => (ready ? money(value) : "…");

	// Twelve months, every book's added into the same month.
	const months = new Map<
		string,
		{ label: string; cal: ReturnType<typeof calendarOf>; income: number; expense: number }
	>();
	rows.forEach((row, index) => {
		if (row.rate === null) return;
		for (const point of cashflows[index]?.data ?? []) {
			const month = months.get(point.period) ?? {
				label: point.label,
				cal: calendarOf(row.book.calendar),
				income: 0,
				expense: 0,
			};
			month.income += scale(row, point.income);
			month.expense += scale(row, point.expense);
			months.set(point.period, month);
		}
	});
	const monthRows = [...months.entries()]
		.sort(([a], [b]) => a.localeCompare(b))
		.map(([key, month]) => ({
			key,
			label: month.label,
			title: periodLabel(key, month.cal),
			values: {
				income: String(month.income),
				expense: String(month.expense),
				net: String(month.income - month.expense),
			},
		}));

	// Spending by category, the same name in two books being one slice.
	const spent = new Map<string, number>();
	rows.forEach((row, index) => {
		if (row.rate === null) return;
		for (const line of categories[index]?.data ?? [])
			spent.set(line.category, (spent.get(line.category) ?? 0) + scale(row, line.total));
	});
	const ordered = [...spent.entries()].sort((a, b) => b[1] - a[1]);
	const slices: Slice[] = ordered.slice(0, 6).map(([name, value], index) => ({
		key: name,
		label: name,
		value: String(value),
		color: categoryColor(index),
	}));
	const rest = ordered.slice(6).reduce((sum, [, value]) => sum + value, 0);
	if (rest > 0)
		slices.push({
			key: "other",
			label: t.analytics.chart.other,
			value: String(rest),
			color: OTHER_COLOR,
		});

	const a = t.analytics.dashboard;
	const s = t.analytics.series;
	const perBook = rows.map((row, index) => {
		const data = compares[index]?.data;
		return {
			key: row.book.id,
			label: row.book.name,
			title: row.book.name,
			values: {
				income: String(data && row.rate !== null ? scale(row, data.current.income) : 0),
				expense: String(data && row.rate !== null ? scale(row, data.current.expense) : 0),
			},
		};
	});

	return (
		<>
			{converted ? (
				<p className="text-xs text-muted">
					{t.scope.approx} {currencyName(unit)} {t.scope.approxTail}
				</p>
			) : null}
			{skipped.length > 0 ? (
				<p className="text-xs text-danger">
					{t.scope.notCounted} {skipped.map((row) => row.book.name).join("، ")}
				</p>
			) : null}
			<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard
					label={t.dashboard.income}
					value={<span className="text-lg sm:text-2xl">{here(income)}</span>}
					footer={
						ready ? <DeltaChip {...change(income, previousIncome)} goodWhen="up" /> : undefined
					}
				/>
				<StatCard
					label={t.dashboard.expense}
					value={<span className="text-lg sm:text-2xl">{here(expense)}</span>}
					footer={
						ready ? <DeltaChip {...change(expense, previousExpense)} goodWhen="down" /> : undefined
					}
				/>
				<StatCard
					label={t.dashboard.net}
					value={<span className="text-lg sm:text-2xl">{here(net)}</span>}
					footer={
						ready ? (
							<DeltaChip {...change(net, previousIncome - previousExpense)} goodWhen="up" />
						) : undefined
					}
				/>
				<StatCard
					label={t.dashboard.countUnit}
					value={<span className="text-lg sm:text-2xl">{ready ? formatAmount(count) : "…"}</span>}
					hint={
						previousLabel
							? sameCalendar
								? periodLabel(periodFor(books[0] as BookResponse), calendarOf(books[0]?.calendar))
								: t.scope.eachBooksMonth
							: undefined
					}
				/>
			</div>

			<SectionCard title={t.scope.byBook} description={t.scope.byBookHint}>
				<GroupedColumns
					title={t.scope.byBook}
					hideTitle
					summary={t.scope.byBookHint}
					rowHeader={t.scope.book}
					formatValue={(value) => money(Number(value))}
					rows={perBook}
					bars={[
						{ key: "income", name: s.income, color: color.income },
						{ key: "expense", name: s.expense, color: color.expense },
					]}
					lines={[]}
				/>
				<ul className="mt-3 flex flex-col">
					{rows.map((row, index) => {
						const data = compares[index]?.data;
						const bookNet = data && row.rate !== null ? scale(row, data.current.net) : null;
						return (
							<li key={row.book.id} className="border-b border-separator last:border-b-0">
								<button
									type="button"
									onClick={() => selectBook(row.book.id)}
									className="flex min-h-12 w-full items-center justify-between gap-3 text-start hover:text-accent"
								>
									<span className="truncate font-medium">{row.book.name}</span>
									<span
										dir="ltr"
										className={`text-sm tabular-nums ${bookNet !== null && bookNet < 0 ? "text-danger" : "text-muted"}`}
									>
										{bookNet === null ? "…" : `${t.scope.net}: ${money(bookNet)}`}
									</span>
								</button>
							</li>
						);
					})}
				</ul>
			</SectionCard>

			<SectionCard title={a.cashflowTitle}>
				<GroupedColumns
					title={a.cashflowTitle}
					hideTitle
					summary={a.cashflowSummary}
					rowHeader={t.analytics.chart.month}
					formatValue={(value) => money(Number(value))}
					rows={monthRows}
					bars={[
						{ key: "income", name: s.income, color: color.income },
						{ key: "expense", name: s.expense, color: color.expense },
					]}
					lines={[{ key: "net", name: s.net, color: color.net }]}
				/>
			</SectionCard>

			<div className="grid gap-5 lg:grid-cols-2">
				<SectionCard title={a.categoryDonutTitle}>
					<Donut
						title={a.categoryDonutTitle}
						hideTitle
						summary={`${a.categoryDonutTitle}: ${slices.map((slice) => slice.label).join("، ")}`}
						slices={slices}
						formatValue={(value) => money(Number(value))}
						center={{ label: t.common.expense, value: formatCompact(expense) }}
						emptyText={t.dashboard.noCategories}
					/>
				</SectionCard>
				<SectionCard
					title={t.scope.recent}
					actions={
						<Link to="/transactions" className="text-sm text-accent">
							{t.dashboard.seeAll}
						</Link>
					}
				>
					<Loaded query={recent}>
						{(page) =>
							page.items.length === 0 ? (
								<p className="text-sm text-muted">{t.dashboard.noRecent}</p>
							) : (
								<StaticTable
									caption={t.scope.recent}
									columns={[t.dashboard.category, t.dashboard.amount, ""]}
									rows={page.items.map((tx) => ({
										id: tx.id,
										cells: [
											<span key="c" className="flex flex-col">
												<span>{tx.category}</span>
												<span className="text-xs text-muted">{tx.book_name}</span>
											</span>,
											<span key="a" className={tx.flow === "income" ? "text-success" : undefined}>
												{tx.flow === "income" ? "+" : "−"}
												{formatMoney(tx.converted_amount, tx.book_currency)}
											</span>,
											<DayPair key="d" iso={tx.occurred_on} bookId={tx.book_id} />,
										],
									}))}
								/>
							)
						}
					</Loaded>
				</SectionCard>
				<RatesCard />
				<CountryRates />
			</div>
		</>
	);
}
