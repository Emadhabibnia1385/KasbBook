import type { ReactNode } from "react";
import {
	Bar,
	CartesianGrid,
	ComposedChart,
	Line,
	ReferenceLine,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { formatCompact } from "@/shared/format";
import { ChartFrame, type LegendItem, SeriesLegend } from "./ChartFrame";
import { ChartTooltip } from "./ChartTooltip";
import { color } from "./palette";
import { axisTick, hasSignal, plotData, tableOf, tickLabel } from "./plot";
import { isolate } from "./text";
import type { ChartRow, FormatValue, Series } from "./types";
import { useReducedMotion } from "./useReducedMotion";

type ColumnsProps = {
	title: string;
	hideTitle?: boolean;
	/** What a screen reader hears for the picture. */
	summary: string;
	rows: readonly ChartRow[];
	/** Drawn side by side at every position. */
	bars: readonly Series[];
	/** Drawn over the columns (a net line); optional. */
	lines?: readonly Series[];
	formatValue: FormatValue;
	/** Header of the table's first column. */
	rowHeader: string;
	height?: number;
	note?: ReactNode;
	emptyText?: string;
};

/** Columns grouped by position (income beside expense for each month), with optional lines across them. */
export function GroupedColumns({
	title,
	hideTitle,
	summary,
	rows,
	bars,
	lines = [],
	formatValue,
	rowHeader,
	height = 260,
	note,
	emptyText,
}: ColumnsProps) {
	const reduced = useReducedMotion();
	const all = [...bars, ...lines];
	const legend: LegendItem[] = [
		...bars.map((item) => ({ ...item, kind: "box" as const })),
		...lines.map((item) => ({ ...item, kind: "line" as const })),
	];
	return (
		<ChartFrame
			title={title}
			hideTitle={hideTitle}
			summary={summary}
			note={note}
			legend={<SeriesLegend items={legend} />}
			empty={!hasSignal(rows, all)}
			emptyText={emptyText}
			table={tableOf(rows, all, formatValue, rowHeader)}
		>
			<div style={{ height }}>
				<ResponsiveContainer width="100%" height="100%">
					<ComposedChart
						data={plotData(rows, all)}
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
							interval="equidistantPreserveStart"
							minTickGap={6}
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
							content={<ChartTooltip series={all} formatValue={formatValue} />}
							cursor={{ fill: "var(--surface-tertiary)", fillOpacity: 0.5 }}
							isAnimationActive={false}
						/>
						{bars.map((item) => (
							<Bar
								key={item.key}
								dataKey={item.key}
								fill={item.color}
								radius={[4, 4, 0, 0]}
								maxBarSize={26}
								isAnimationActive={!reduced}
							/>
						))}
						{lines.map((item) => (
							<Line
								key={item.key}
								type="monotone"
								dataKey={item.key}
								stroke={item.color}
								strokeWidth={2.5}
								strokeDasharray={item.dashed ? "6 4" : undefined}
								dot={{ r: 3, fill: color.surface, stroke: item.color, strokeWidth: 2 }}
								isAnimationActive={!reduced}
							/>
						))}
					</ComposedChart>
				</ResponsiveContainer>
			</div>
		</ChartFrame>
	);
}

/** Income and expense for each day of the week: the same columns, seven of them, shorter. */
export function WeekdayBars(props: Omit<ColumnsProps, "height">) {
	return <GroupedColumns {...props} height={220} />;
}
