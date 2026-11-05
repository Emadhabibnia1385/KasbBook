import { type ReactNode, useId } from "react";
import { t } from "@/strings";
import type { Series } from "./types";

export type ChartTable = {
	/** Header of the first column (the day, the month, the category). */
	header: string;
	columns: readonly string[];
	rows: readonly { key: string; cells: readonly ReactNode[] }[];
};

type FrameProps = {
	title: string;
	/** The title is only for screen readers: the card around the chart already shows it as a heading. */
	hideTitle?: boolean;
	/** What a screen reader hears for the picture, and the table's name. */
	summary: string;
	/** A line under the title, for the figure the chart is about. */
	note?: ReactNode;
	legend?: ReactNode;
	/** Above the picture (a series legend) or below it (a list that is the legend and more). */
	legendPosition?: "top" | "bottom";
	/** No picture when there is nothing to draw; the words say why. */
	empty?: boolean;
	emptyText?: string;
	table?: ChartTable;
	children: ReactNode;
};

/**
 * What every chart shares: a named figure, a legend in words, the picture and, behind a disclosure,
 * the same figures as a table. The picture is only ever a picture; the numbers are text.
 */
export function ChartFrame({
	title,
	hideTitle,
	summary,
	note,
	legend,
	legendPosition = "top",
	empty,
	emptyText,
	table,
	children,
}: FrameProps) {
	const captionId = useId();
	return (
		<figure className="flex min-w-0 flex-col gap-3" aria-labelledby={captionId}>
			<figcaption
				id={captionId}
				className={hideTitle ? "sr-only" : "text-sm font-semibold text-foreground"}
			>
				{title}
			</figcaption>
			{note ? <div className="text-sm text-muted">{note}</div> : null}
			{empty ? (
				<p className="rounded-md border border-dashed border-field-border p-4 text-center text-sm text-muted">
					{emptyText ?? t.analytics.chart.noData}
				</p>
			) : (
				<>
					{legendPosition === "top" ? legend : null}
					{/* A picture of numbers whose text is the table below: «img» with a label, not a widget. */}
					{/* oxlint-disable-next-line jsx-a11y/prefer-tag-over-role */}
					<div dir="ltr" role="img" aria-label={summary} className="min-w-0">
						{children}
					</div>
					{legendPosition === "bottom" ? legend : null}
				</>
			)}
			{table && table.rows.length > 0 ? <TableDisclosure label={summary} table={table} /> : null}
		</figure>
	);
}

function TableDisclosure({ label, table }: { label: string; table: ChartTable }) {
	return (
		<details className="rounded-md border border-border text-sm">
			<summary className="min-h-11 cursor-pointer px-3 py-2.5 font-medium">
				{t.analytics.chart.showTable}
			</summary>
			{/* A named region that takes focus, so a keyboard user can scroll a table wider than the screen. */}
			{/* oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex, jsx-a11y/prefer-tag-over-role */}
			<div className="max-h-80 overflow-auto" tabIndex={0} role="region" aria-label={label}>
				<table className="w-full text-sm">
					<caption className="sr-only">{label}</caption>
					<thead>
						<tr className="border-b border-border text-muted">
							<th scope="col" className="px-3 py-2 text-start font-medium">
								{table.header}
							</th>
							{table.columns.map((column) => (
								<th key={column} scope="col" className="px-3 py-2 text-end font-medium">
									{column}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{table.rows.map((row) => (
							<tr key={row.key} className="border-b border-border last:border-0">
								{row.cells.map((cell, index) =>
									index === 0 ? (
										<th key={index} scope="row" className="px-3 py-1.5 text-start font-normal">
											{cell}
										</th>
									) : (
										<td key={index} className="whitespace-nowrap px-3 py-1.5 text-end tabular-nums">
											{cell}
										</td>
									),
								)}
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</details>
	);
}

export type LegendItem = Pick<Series, "name" | "color" | "dashed"> & {
	key: string;
	kind?: "box" | "line";
};

/** The series by name, each with its mark: a box for columns, a line (dashed or not) for lines. */
export function SeriesLegend({ items }: { items: readonly LegendItem[] }) {
	return (
		<ul
			aria-label={t.analytics.chart.legend}
			className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-foreground"
		>
			{items.map((item) => (
				<li key={item.key} className="flex items-center gap-1.5">
					{item.kind === "line" ? (
						<span
							aria-hidden
							className="inline-block w-4 border-t-[3px]"
							style={{ borderColor: item.color, borderStyle: item.dashed ? "dashed" : "solid" }}
						/>
					) : (
						<span
							aria-hidden
							className="inline-block size-2.5 rounded-xs"
							style={{ background: item.color }}
						/>
					)}
					{item.name}
				</li>
			))}
		</ul>
	);
}
