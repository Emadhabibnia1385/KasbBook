import { useIsNarrow } from "@nyxon/nasim";
import {
	Bar,
	CartesianGrid,
	ComposedChart,
	Rectangle,
	ReferenceLine,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { formatCompact } from "@/shared/format";
import { t } from "@/strings";
import { ChartFrame, SeriesLegend } from "./ChartFrame";
import { ChartTooltip, type Datum } from "./ChartTooltip";
import { color } from "./palette";
import { axisTick, tableOf, tickLabel } from "./plot";
import { isolate, toNumber } from "./text";
import type { ChartRow, FormatValue, Series } from "./types";
import { useReducedMotion } from "./useReducedMotion";

export type BridgeStep = {
	key: string;
	label: string;
	/** Signed, as the API's string: income positive, an expense negative. A `total` is the running sum so far. */
	amount: string;
	kind: "income" | "expense" | "total";
};

type BridgeProps = {
	title: string;
	hideTitle?: boolean;
	summary: string;
	steps: readonly BridgeStep[];
	formatValue: FormatValue;
	emptyText?: string;
};

const FILL = { income: color.income, expense: color.expense, total: color.net } as const;

/** A net bridge: income, then each cost taking a step down, then what is left. Each bar floats where the running total was. */
export function Bridge({ title, hideTitle, summary, steps, formatValue, emptyText }: BridgeProps) {
	const narrow = useIsNarrow("sm");
	const reduced = useReducedMotion();
	const amounts = steps.map((step) => toNumber(step.amount) ?? 0);
	// What the running total stood at before each step; a `total` bar always stands on zero.
	const before = amounts.map((_, index) =>
		amounts
			.slice(0, index)
			.reduce((sum, amount, at) => (steps[at]?.kind === "total" ? sum : sum + amount), 0),
	);
	const data: (Datum & { range: [number, number]; kind: BridgeStep["kind"] })[] = steps.map(
		(step, index) => {
			const amount = amounts[index] ?? 0;
			const start = step.kind === "total" ? 0 : (before[index] ?? 0);
			const end = step.kind === "total" ? amount : start + amount;
			const row: ChartRow = { key: step.key, label: step.label, values: { amount: step.amount } };
			return {
				row,
				label: step.label,
				kind: step.kind,
				range: [Math.min(start, end), Math.max(start, end)],
			};
		},
	);
	const rows = data.map((datum) => datum.row);
	const series: Series[] = [{ key: "amount", name: t.analytics.chart.amount, color: color.axis }];
	const kinds = (["income", "expense", "total"] as const).filter((kind) =>
		steps.some((step) => step.kind === kind),
	);
	const KIND_NAMES = {
		income: t.analytics.series.income,
		expense: t.analytics.series.expense,
		total: t.analytics.reports.bridgeTotal,
	};
	return (
		<ChartFrame
			title={title}
			hideTitle={hideTitle}
			summary={summary}
			legend={
				<SeriesLegend
					items={kinds.map((kind) => ({
						key: kind,
						name: KIND_NAMES[kind],
						color: FILL[kind],
						kind: "box" as const,
					}))}
				/>
			}
			empty={steps.every((step) => (toNumber(step.amount) ?? 0) === 0)}
			emptyText={emptyText}
			table={tableOf(rows, series, formatValue, t.analytics.top.category)}
		>
			<div style={{ height: narrow ? 180 : 260 }}>
				<ResponsiveContainer width="100%" height="100%">
					<ComposedChart
						data={data}
						margin={{ top: 8, right: 4, bottom: 0, left: 0 }}
						accessibilityLayer={false}
					>
						<CartesianGrid vertical={false} stroke={color.grid} />
						<XAxis
							dataKey="label"
							tickFormatter={tickLabel}
							tick={axisTick}
							tickLine={false}
							axisLine={false}
							interval={0}
						/>
						<YAxis
							width="auto"
							tickFormatter={(value: number) => isolate(formatCompact(value))}
							tick={axisTick}
							tickLine={false}
							axisLine={false}
							tickCount={5}
						/>
						<ReferenceLine y={0} stroke="var(--border)" />
						<Tooltip
							content={<ChartTooltip series={series} formatValue={formatValue} />}
							cursor={{ fill: "var(--surface-tertiary)", fillOpacity: 0.5 }}
							isAnimationActive={false}
						/>
						<Bar
							dataKey="range"
							maxBarSize={36}
							isAnimationActive={!reduced}
							shape={(props: unknown) => {
								const { payload, ...rest } = props as {
									payload: { kind: BridgeStep["kind"] };
								} & Record<string, unknown>;
								return <Rectangle {...rest} fill={FILL[payload.kind]} radius={4} />;
							}}
						/>
					</ComposedChart>
				</ResponsiveContainer>
			</div>
		</ChartFrame>
	);
}
