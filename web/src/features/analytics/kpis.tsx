import { StatCard, useIsNarrow } from "@nyxon/nasim";
import type { ReactNode } from "react";
import {
	useAnalyticsCashflow,
	useAnalyticsCompare,
	useAnalyticsOverviewKpis,
} from "@/api/generated/analytics/analytics";
import type { BookResponse } from "@/api/generated/model";
import { color, DeltaChip, Sparkline } from "@/shared/charts";
import { formatAmount, formatMoney } from "@/shared/format";
import { periodLabel } from "@/shared/periods";
import { t } from "@/strings";

// A phone's two-column grid is about 160px a card: a seven-digit amount at the tile's usual size does not fit.
function Figure({ children }: { children: ReactNode }) {
	return <span className="text-lg sm:text-2xl">{children}</span>;
}

type ChangeCardProps = {
	label: string;
	value: string;
	/** The earlier period's figure, as text, so the chip's percentage always has its two ends in view. */
	previous?: string;
	chip?: ReactNode;
	spark?: ReactNode;
	hint?: string;
};

function ChangeCard({ label, value, previous, chip, spark, hint }: ChangeCardProps) {
	// A phone shows the figure and its change; the earlier figure, the year of shape and the
	// explanation are what make four cards a screen tall, and they are one tap away in the report.
	const compact = useIsNarrow("sm");
	if (compact) {
		return <StatCard label={label} value={<Figure>{value}</Figure>} footer={chip ?? undefined} />;
	}
	return (
		<StatCard
			label={label}
			value={<Figure>{value}</Figure>}
			hint={hint}
			footer={
				<div className="flex flex-col gap-2">
					{chip || previous ? (
						<div className="flex flex-wrap items-center gap-x-2 gap-y-1">
							{chip}
							{previous ? <span className="text-xs text-muted">{previous}</span> : null}
						</div>
					) : null}
					{spark}
				</div>
			}
		/>
	);
}

/** Income, expense, net and savings rate for the period, each against the one before; with a year of shape behind them. */
export function KpiRow({ book, period }: { book: BookResponse; period: string }) {
	const compare = useAnalyticsCompare(book.id, { period }).data;
	const cashflow = useAnalyticsCashflow(book.id, { months: 12 }).data ?? [];
	const money = (value?: string) => (value === undefined ? "…" : formatMoney(value, book.currency));
	const before = compare ? periodLabel(compare.previous_period) : "";
	const previous = (value?: string) =>
		value === undefined ? undefined : `${before}: ${money(value)}`;
	const spark = (key: "income" | "expense" | "net", tone: string, label: string) => (
		<Sparkline
			values={cashflow.map((point) => Number(point[key]))}
			color={tone}
			label={`${t.analytics.kpi.sparkline}: ${label}`}
		/>
	);
	const rate = useAnalyticsOverviewKpis(book.id, { period }).data?.savings_rate_percent;
	return (
		<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
			<ChangeCard
				label={t.dashboard.income}
				value={money(compare?.current.income)}
				previous={previous(compare?.previous.income)}
				chip={
					compare ? (
						<DeltaChip
							percent={compare.income.percent}
							absolute={compare.income.absolute}
							goodWhen="up"
						/>
					) : null
				}
				spark={spark("income", color.income, t.common.income)}
			/>
			<ChangeCard
				label={t.dashboard.expense}
				value={money(compare?.current.expense)}
				previous={previous(compare?.previous.expense)}
				chip={
					compare ? (
						<DeltaChip
							percent={compare.expense.percent}
							absolute={compare.expense.absolute}
							goodWhen="down"
						/>
					) : null
				}
				spark={spark("expense", color.expense, t.common.expense)}
			/>
			<ChangeCard
				label={t.dashboard.net}
				value={money(compare?.current.net)}
				previous={previous(compare?.previous.net)}
				chip={
					compare ? (
						<DeltaChip
							percent={compare.net.percent}
							absolute={compare.net.absolute}
							goodWhen="up"
						/>
					) : null
				}
				spark={spark("net", color.net, t.common.net)}
				hint={
					compare
						? `${formatAmount(compare.current.transaction_count)} ${t.dashboard.countUnit}`
						: undefined
				}
			/>
			<ChangeCard
				label={t.analytics.kpi.savingsRate}
				value={rate == null ? "—" : `${formatAmount(rate)}٪`}
				hint={rate == null ? t.analytics.kpi.noSavingsRate : t.analytics.kpi.savingsRateHint}
				spark={
					<Sparkline
						values={cashflow.map((point) =>
							point.savings_rate_percent == null ? null : Number(point.savings_rate_percent),
						)}
						color={color.net}
						label={`${t.analytics.kpi.sparkline}: ${t.analytics.kpi.savingsRate}`}
					/>
				}
			/>
		</div>
	);
}

/** Where the book stands: the balance, the pace of spending, how long it lasts and the single biggest cost. */
export function OverviewRow({ book, period }: { book: BookResponse; period: string }) {
	const { data } = useAnalyticsOverviewKpis(book.id, { period });
	const k = t.analytics.kpi;
	const biggest = data?.biggest_expense;
	const compact = useIsNarrow("sm");
	const hint = (text?: string) => (compact ? undefined : text);
	return (
		<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
			<StatCard
				label={k.balance}
				value={
					<Figure>
						{data ? formatMoney(data.total_balance ?? data.base_balance, data.currency) : "…"}
					</Figure>
				}
				hint={hint(data?.holds_other_currencies ? k.otherCurrencies : k.balanceHint)}
			/>
			<StatCard
				label={k.avgDaily}
				value={
					<Figure>
						{data
							? formatMoney(String(Math.round(Number(data.average_daily_expense))), data.currency)
							: "…"}
					</Figure>
				}
				hint={hint(k.avgDailyHint)}
			/>
			<StatCard
				label={k.runway}
				value={
					data
						? data.runway_days == null
							? "—"
							: `${formatAmount(data.runway_days)} ${k.runwayUnit}`
						: "…"
				}
				hint={hint(data?.runway_days == null && data ? k.noRunway : k.runwayHint)}
			/>
			<StatCard
				label={k.biggest}
				value={
					<Figure>
						{data ? (biggest ? formatMoney(biggest.amount, data.currency) : "—") : "…"}
					</Figure>
				}
				hint={biggest ? biggest.category : data ? hint(k.noBiggest) : undefined}
			/>
		</div>
	);
}

/** The same four figures as the dashboard row, but as a report of one period against the one before it. */
export function CompareCards({ book, period }: { book: BookResponse; period: string }) {
	const { data } = useAnalyticsCompare(book.id, { period });
	const money = (value?: string) => (value === undefined ? "…" : formatMoney(value, book.currency));
	const before = data ? periodLabel(data.previous_period) : "";
	const previous = (value?: string) =>
		value === undefined ? undefined : `${before}: ${money(value)}`;
	return (
		<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
			<ChangeCard
				label={t.common.income}
				value={money(data?.current.income)}
				previous={previous(data?.previous.income)}
				chip={
					data ? (
						<DeltaChip
							percent={data.income.percent}
							absolute={data.income.absolute}
							goodWhen="up"
						/>
					) : null
				}
			/>
			<ChangeCard
				label={t.common.expense}
				value={money(data?.current.expense)}
				previous={previous(data?.previous.expense)}
				chip={
					data ? (
						<DeltaChip
							percent={data.expense.percent}
							absolute={data.expense.absolute}
							goodWhen="down"
						/>
					) : null
				}
			/>
			<ChangeCard
				label={t.common.net}
				value={money(data?.current.net)}
				previous={previous(data?.previous.net)}
				chip={
					data ? (
						<DeltaChip percent={data.net.percent} absolute={data.net.absolute} goodWhen="up" />
					) : null
				}
			/>
			<ChangeCard
				label={t.analytics.reports.count}
				value={data ? formatAmount(data.current.transaction_count) : "…"}
				previous={data ? `${before}: ${formatAmount(data.previous.transaction_count)}` : undefined}
			/>
		</div>
	);
}
