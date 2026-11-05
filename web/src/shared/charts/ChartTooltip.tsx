import type { ChartRow, FormatValue, Series } from "./types";

/** What the plot hands a tooltip: the row it drew, kept whole so the exact strings are still there. */
export type Datum = { row: ChartRow } & Record<string, unknown>;

type TooltipProps = {
	active?: boolean;
	payload?: readonly { payload?: unknown }[];
	series: readonly Series[];
	formatValue: FormatValue;
};

/** The hover card: the row's title, then each series by name with its exact value. */
export function ChartTooltip({ active, payload, series, formatValue }: TooltipProps) {
	const datum = payload?.[0]?.payload as Datum | undefined;
	if (!active || !datum) return null;
	const { row } = datum;
	const present = series.filter((item) => row.values[item.key] != null);
	if (present.length === 0) return null;
	return (
		<div
			dir="rtl"
			className="rounded-xl border border-border bg-overlay px-3 py-2 text-sm shadow-lg"
		>
			<p className="mb-1 font-semibold">{row.title ?? row.label}</p>
			<ul className="flex flex-col gap-0.5">
				{present.map((item) => (
					<li key={item.key} className="flex items-center justify-between gap-4">
						<span className="flex items-center gap-1.5">
							<span
								aria-hidden
								className="inline-block size-2.5 rounded-xs"
								style={{ background: item.color }}
							/>
							{item.name}
						</span>
						<span className="tabular-nums">{formatValue(row.values[item.key] as string)}</span>
					</li>
				))}
			</ul>
		</div>
	);
}
