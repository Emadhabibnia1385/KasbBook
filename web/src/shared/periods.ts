// The periods the analytics API takes (1405-08, 1405, week) and the words a person reads for them.
import { currentPeriod, formatAmount, MONTHS, recentPeriods } from "@/shared/format";
import { t } from "@/strings";

export type PeriodKind = "week" | "month" | "year";

const plain = (year: number | string) => formatAmount(year).replace(/[٬,]/g, "");

/** «آبان ۱۴۰۵», «سال ۱۴۰۵», «این هفته» — from either the documented form or the API's own (`w:1`). */
export function periodLabel(spec: string): string {
	if (spec === "week" || spec === "w:0") return t.analytics.reports.thisWeek;
	const weeksBack = /^w:(\d+)$/.exec(spec)?.[1];
	if (weeksBack) {
		return Number(weeksBack) === 1
			? t.analytics.reports.lastWeek
			: `${formatAmount(weeksBack)} ${t.analytics.reports.weeksAgo}`;
	}
	const [year = "", month] = spec.split("-");
	if (month === undefined) return `${t.analytics.reports.yearWord} ${plain(year)}`;
	return `${MONTHS[Number(month) - 1] ?? month} ${plain(year)}`;
}

export function kindOf(spec: string): PeriodKind {
	return spec === "week" ? "week" : spec.includes("-") ? "month" : "year";
}

export function monthOptions(count = 12) {
	return recentPeriods(count);
}

export function yearOptions(count = 4) {
	const year = Number(currentPeriod().split("-")[0]);
	return Array.from({ length: count }, (_, back) => ({
		value: String(year - back),
		label: `${t.analytics.reports.yearWord} ${plain(year - back)}`,
	}));
}

const partsOf = new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", {
	year: "numeric",
	month: "numeric",
});

/** The Jalali month an ISO day falls in, as the API's period and the month's name. */
export function monthOfDay(iso: string): { period: string; label: string } {
	const parts = partsOf.formatToParts(new Date(`${iso}T12:00:00`));
	const pick = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
	const month = Number(pick("month"));
	return {
		period: `${pick("year")}-${String(month).padStart(2, "0")}`,
		label: MONTHS[month - 1] ?? "",
	};
}
