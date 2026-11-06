import { shiftIso } from "@/shared/jalaliDay";
import { pickedDay } from "@/shared/dates";

export type RangeKey =
	| "all"
	| "today"
	| "yesterday"
	| "d3"
	| "d7"
	| "d30"
	| "d90"
	| "year"
	| "custom";
export type FlowKey = "income" | "expense";
export type SortKey = "newest" | "oldest" | "amount_desc" | "amount_asc" | "category";

export type Filters = {
	q: string;
	range: RangeKey;
	/** Picker values of the custom range. */
	since: string;
	until: string;
	flows: FlowKey[];
	categories: string[];
	/** The money it was paid in: «only the TON ones». */
	currencies: string[];
	/** Not a filter: it orders what is shown, so «clear filters» leaves it alone. */
	sort: SortKey;
};

export const NO_FILTERS: Filters = {
	q: "",
	range: "all",
	since: "",
	until: "",
	flows: [],
	categories: [],
	currencies: [],
	sort: "newest",
};

// «۳ روز اخیر» counts today as one of the days, so «۷ روز اخیر» is today and the six before it.
const BACK: Partial<Record<RangeKey, number>> = { d3: 2, d7: 6, d30: 29, d90: 89, year: 364 };

export function todayIso(now = new Date()): string {
	const pad = (n: number) => String(n).padStart(2, "0");
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** The dates a range means, as the API takes them. Empty for «all». */
export function rangeDates(
	filters: Filters,
	today = todayIso(),
): { since?: string; until?: string } {
	switch (filters.range) {
		case "all":
			return {};
		case "today":
			return { since: today, until: today };
		case "yesterday": {
			const day = shiftIso(today, -1);
			return { since: day, until: day };
		}
		case "custom":
			return {
				since: pickedDay(filters.since) || undefined,
				until: pickedDay(filters.until) || undefined,
			} as {
				since?: string;
				until?: string;
			};
		default:
			return { since: shiftIso(today, -(BACK[filters.range] ?? 0)), until: today };
	}
}

/** How many separate things narrow the list, for the «فیلترها (۲)» label. */
export function activeCount(filters: Filters): number {
	return (
		(filters.q.trim().length >= 2 ? 1 : 0) +
		(filters.range !== "all" ? 1 : 0) +
		filters.flows.length +
		filters.categories.length +
		filters.currencies.length
	);
}

export const toggle = <T>(list: readonly T[], item: T): T[] =>
	list.includes(item) ? list.filter((entry) => entry !== item) : [...list, item];
