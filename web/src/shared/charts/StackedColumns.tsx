import type { ReactNode } from "react";
import {
	Bar,
	CartesianGrid,
	ComposedChart,
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

type StackedProps = {
	title: string;
	hideTitle?: boolean;
	/** What a screen reader hears for the picture. */
	summary: string;
	rows: readonly ChartRow[];
	/** Stacked bottom to top in this order; the legend lists them in the same order. */
	parts: readonly Series[];
	/** The row value that holds each position's total, shown as the table's last column. */
	total?: { key: string; name: string };
	formatValue: FormatValue;
	/** Header of the table's first column. */
	rowHeader: string;
	height?: number;
	note?: ReactNode;
	emptyText?: string;
};

/**
 * One column per position (a month) cut into the parts that make it up (its categories). Parts are
 * told apart by the legend and the table, not by colour alone, and a part that is zero is simply not drawn.
 */
export function StackedColumns({
	title,
	hideTitle,
	summary,
	rows,
	parts,
	total,
	formatValue,
	rowHeader,
	height = 280,
	note,
	emptyText,
}: StackedProps) {
	const reduced = useReducedMotion();
	const legend: LegendItem[] = parts.map((item) => ({ ...item, kind: "box" as const }));
	const tabled: Series[] = total
		? [...parts, { key: total.key, name: total.name, color: color.axis }]
		: [...parts];
	return (
		<ChartFrame
			title={title}
			hideTitle={hideTitle}
			summary={summary}
			note={note}
			legend={<SeriesLegend items={legend} />}
			empty={!hasSignal(rows, parts)}
			emptyText={emptyText}
			table={tableOf(rows, tabled, formatValue, rowHeader)}
		>
			<div style={{ height }}>
				<ResponsiveContainer width="100%" height="100%">
					<ComposedChart
						data={plotData(rows, parts)}
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
							content={<ChartTooltip series={parts} formatValue={formatValue} skipZero />}
							cursor={{ fill: "var(--surface-tertiary)", fillOpacity: 0.5 }}
							isAnimationActive={false}
						/>
						{parts.map((item) => (
							<Bar
								key={item.key}
								dataKey={item.key}
								stackId="stack"
								fill={item.color}
								// A hairline of the card's own colour keeps neighbouring parts apart without a hue.
								stroke={color.surface}
								strokeWidth={1}
								maxBarSize={36}
								isAnimationActive={!reduced}
							/>
						))}
					</ComposedChart>
				</ResponsiveContainer>
			</div>
		</ChartFrame>
	);
}
