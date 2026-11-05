import type { ChartTable } from "./ChartFrame";
import type { Datum } from "./ChartTooltip";
import { color } from "./palette";
import { isolate, toNumber } from "./text";
import type { ChartRow, FormatValue, Series } from "./types";

/** Rows as the plot reads them: numbers for the picture, the row itself for the tooltip. */
export function plotData(rows: readonly ChartRow[], series: readonly Series[]): Datum[] {
	return rows.map((row) => {
		const datum: Datum = { row, label: row.label };
		for (const item of series) datum[item.key] = toNumber(row.values[item.key]);
		return datum;
	});
}

/** Whether there is anything to draw: a chart of nothing but zeros is a flat line and says nothing. */
export function hasSignal(rows: readonly ChartRow[], series: readonly Series[]): boolean {
	return rows.some((row) => series.some((item) => (toNumber(row.values[item.key]) ?? 0) !== 0));
}

/** The same figures as text, with the API's exact strings, for the disclosure beneath the chart. */
export function tableOf(
	rows: readonly ChartRow[],
	series: readonly Series[],
	formatValue: FormatValue,
	header: string,
): ChartTable {
	return {
		header,
		columns: series.map((item) => item.name),
		rows: rows.map((row) => ({
			key: row.key,
			cells: [
				row.title ?? row.label,
				...series.map((item) =>
					row.values[item.key] == null ? "—" : formatValue(row.values[item.key] as string),
				),
			],
		})),
	};
}

export const axisTick = { fill: color.axis, fontSize: 11 } as const;

export function tickLabel(value: unknown): string {
	return isolate(String(value));
}
