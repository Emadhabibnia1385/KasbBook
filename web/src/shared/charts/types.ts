export type Series = {
	key: string;
	/** What the legend, the tooltip and the table call it. */
	name: string;
	/** A token such as `var(--success)`. */
	color: string;
	/** A dashed line reads as «the other one» without relying on its colour. */
	dashed?: boolean;
	/** A line with a tinted area under it. */
	area?: boolean;
};

/** One position on the x axis. Values are the API's strings, so the table and tooltip stay exact. */
export type ChartRow = {
	key: string;
	/** Short, for the axis. */
	label: string;
	/** Longer, for the tooltip and the table; defaults to `label`. */
	title?: string;
	values: Record<string, string | null | undefined>;
};

/** Formats an exact value from the API for a person: a tooltip line or a table cell. */
export type FormatValue = (value: string) => string;
