import type { ReactNode } from "react";
import { Pie, PieChart, ResponsiveContainer } from "recharts";
import { formatAmount } from "@/shared/format";
import { t } from "@/strings";
import { ChartFrame } from "./ChartFrame";
import { color } from "./palette";
import { toNumber } from "./text";
import type { FormatValue } from "./types";
import { useReducedMotion } from "./useReducedMotion";

export type Slice = { key: string; label: string; value: string; color: string };

type DonutProps = {
	title: string;
	hideTitle?: boolean;
	summary: string;
	slices: readonly Slice[];
	formatValue: FormatValue;
	/** Printed in the hole: what the ring adds up to. */
	center?: { label: string; value: string };
	emptyText?: string;
	note?: ReactNode;
};

/** A ring of shares. The list beside it is the legend: every slice by name, its share and its exact amount. */
export function Donut({
	title,
	hideTitle,
	summary,
	slices,
	formatValue,
	center,
	emptyText,
	note,
}: DonutProps) {
	const reduced = useReducedMotion();
	const drawn = slices.map((slice) => ({
		...slice,
		number: Math.max(0, toNumber(slice.value) ?? 0),
	}));
	const total = drawn.reduce((sum, slice) => sum + slice.number, 0);
	const share = (number: number) =>
		total > 0 ? formatAmount(((number / total) * 100).toFixed(1)) : formatAmount(0);
	return (
		<ChartFrame
			title={title}
			hideTitle={hideTitle}
			summary={summary}
			note={note}
			empty={total <= 0}
			emptyText={emptyText}
			legendPosition="bottom"
			legend={
				<ul aria-label={t.analytics.chart.legend} className="flex flex-col gap-1.5 text-sm">
					{drawn.map((slice) => (
						<li key={slice.key} className="flex items-center gap-2">
							<span
								aria-hidden
								className="inline-block size-2.5 shrink-0 rounded-xs"
								style={{ background: slice.color }}
							/>
							<span className="min-w-0 flex-1">
								<span className="block truncate">{slice.label}</span>
								{/* The amount has its own column from sm up; below that it goes under the name. */}
								<span className="block text-xs text-muted tabular-nums sm:hidden">
									{formatValue(slice.value)}
								</span>
							</span>
							<span className="tabular-nums text-muted">{share(slice.number)}٪</span>
							<span className="hidden w-36 text-end tabular-nums sm:inline">
								{formatValue(slice.value)}
							</span>
						</li>
					))}
				</ul>
			}
			table={{
				header: t.analytics.top.category,
				columns: [t.analytics.chart.amount, t.analytics.chart.share],
				rows: drawn.map((slice) => ({
					key: slice.key,
					cells: [slice.label, formatValue(slice.value), `${share(slice.number)}٪`],
				})),
			}}
		>
			<div className="relative mx-auto h-44 w-44">
				<ResponsiveContainer width="100%" height="100%">
					<PieChart accessibilityLayer={false}>
						<Pie
							data={drawn.map((slice) => ({
								name: slice.label,
								value: slice.number,
								fill: slice.color,
							}))}
							dataKey="value"
							nameKey="name"
							innerRadius="64%"
							outerRadius="100%"
							paddingAngle={drawn.length > 1 ? 2 : 0}
							stroke={color.surface}
							strokeWidth={2}
							startAngle={90}
							endAngle={-270}
							isAnimationActive={!reduced}
						/>
					</PieChart>
				</ResponsiveContainer>
				{center ? (
					<div
						dir="rtl"
						className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-6 text-center"
					>
						<span className="text-xs text-muted">{center.label}</span>
						<span className="text-sm font-bold tabular-nums">{center.value}</span>
					</div>
				) : null}
			</div>
		</ChartFrame>
	);
}
