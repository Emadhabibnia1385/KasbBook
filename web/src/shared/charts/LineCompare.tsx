import type { ReactNode } from "react";
import {
	Area,
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

type LineCompareProps = {
	title: string;
	hideTitle?: boolean;
	summary: string;
	rows: readonly ChartRow[];
	/** A series with `area` gets a tint under its line; one with `dashed` is the comparison. */
	series: readonly Series[];
	formatValue: FormatValue;
	rowHeader: string;
	height?: number;
	note?: ReactNode;
	emptyText?: string;
};

/** Lines over one axis, area-filled where it helps, dashed where a line is «the other period». */
export function LineCompare({
	title,
	hideTitle,
	summary,
	rows,
	series,
	formatValue,
	rowHeader,
	height = 260,
	note,
	emptyText,
}: LineCompareProps) {
	const reduced = useReducedMotion();
	const legend: LegendItem[] = series.map((item) => ({ ...item, kind: "line" as const }));
	return (
		<ChartFrame
			title={title}
			hideTitle={hideTitle}
			summary={summary}
			note={note}
			legend={<SeriesLegend items={legend} />}
			empty={!hasSignal(rows, series)}
			emptyText={emptyText}
			table={tableOf(rows, series, formatValue, rowHeader)}
		>
			<div style={{ height }}>
				<ResponsiveContainer width="100%" height="100%">
					<ComposedChart
						data={plotData(rows, series)}
						margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
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
							minTickGap={14}
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
							isAnimationActive={false}
						/>
						{series.map((item) =>
							item.area ? (
								<Area
									key={item.key}
									type="monotone"
									dataKey={item.key}
									stroke={item.color}
									strokeWidth={2.5}
									fill={item.color}
									fillOpacity={0.16}
									dot={false}
									activeDot={{ r: 4 }}
									isAnimationActive={!reduced}
								/>
							) : (
								<Line
									key={item.key}
									type="monotone"
									dataKey={item.key}
									stroke={item.color}
									strokeWidth={item.dashed ? 2 : 2.5}
									strokeDasharray={item.dashed ? "6 4" : undefined}
									dot={false}
									activeDot={{ r: 4 }}
									isAnimationActive={!reduced}
								/>
							),
						)}
					</ComposedChart>
				</ResponsiveContainer>
			</div>
		</ChartFrame>
	);
}
