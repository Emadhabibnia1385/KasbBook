// The periods the analytics API takes (1405-08, 1405, week) and the words a person reads for them.
import {
	type CalendarName,
	currentPeriod,
	formatAmount,
	monthNames,
	recentPeriods,
	yearText,
} from "@/shared/format";
import { t } from "@/strings";

export type PeriodKind = "week" | "month" | "year" | "custom";

const plain = (year: number | string, cal: CalendarName = "jalali") => yearText(year, cal);
const num = (n: number, cal: CalendarName) => (cal === "gregorian" ? String(n) : formatAmount(n));

const ORDINALS = ["اول", "دوم", "سوم", "چهارم", "پنجم", "ششم"];

const dayParts: Record<CalendarName, Intl.DateTimeFormat> = {
	jalali: new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", {
		year: "numeric",
		month: "numeric",
		day: "numeric",
	}),
	gregorian: new Intl.DateTimeFormat("en-u-ca-gregory-nu-latn", {
		year: "numeric",
		month: "numeric",
		day: "numeric",
	}),
};

/** An ISO day as the year, month and day of the given calendar. */
export function partsOfDay(
	iso: string,
	cal: CalendarName,
): { year: number; month: number; day: number } {
	const parts = dayParts[cal].formatToParts(new Date(`${iso}T12:00:00`));
	const pick = (type: string) => Number(parts.find((part) => part.type === type)?.value);
	return { year: pick("year"), month: pick("month"), day: pick("day") };
}

const pad = (n: number) => String(n).padStart(2, "0");
const isoOf = (date: Date) =>
	`${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

/** The first and last day of the week `back` weeks ago: Saturday to Friday, or Monday to Sunday. */
export function weekBounds(
	back: number,
	cal: CalendarName,
	now = new Date(),
): { from: string; to: string } {
	const weekday = now.getDay(); // 0 is Sunday
	const since = cal === "jalali" ? (weekday + 1) % 7 : (weekday + 6) % 7;
	const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - since - 7 * back);
	const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
	return { from: isoOf(start), to: isoOf(end) };
}

const dayFormats: Record<CalendarName, Intl.DateTimeFormat> = {
	jalali: new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
		day: "numeric",
		month: "long",
		year: "numeric",
	}),
	gregorian: new Intl.DateTimeFormat("en-US-u-ca-gregory-nu-latn", {
		day: "numeric",
		month: "long",
		year: "numeric",
	}),
};

/** A day written out in the book's calendar: «۱۵ آبان ۱۴۰۵» or «November 6, 2026». */
export function formatDayIn(iso: string, cal: CalendarName = "jalali"): string {
	return dayFormats[cal].format(new Date(`${iso}T12:00:00`));
}

/** «هفتهٔ اول نوامبر»: which week of its month a week is, counted from the day it starts on. */
export function weekName(back: number, cal: CalendarName, now = new Date()): string {
	const { from } = weekBounds(back, cal, now);
	const { month, day } = partsOfDay(from, cal);
	const ordinal = ORDINALS[Math.min(5, Math.floor((day - 1) / 7))] ?? "";
	return `${t.analytics.reports.weekWord} ${ordinal} ${monthNames(cal)[month - 1] ?? ""}`;
}

/** «۲ تا ۸ نوامبر»: the days a week covers, naming the month only once when it is the same. */
function weekSpan(back: number, cal: CalendarName, now = new Date()): string {
	const { from, to } = weekBounds(back, cal, now);
	const a = partsOfDay(from, cal);
	const b = partsOfDay(to, cal);
	const names = monthNames(cal);
	const end = `${num(b.day, cal)} ${names[b.month - 1] ?? ""}`;
	return a.month === b.month
		? `${num(a.day, cal)} ${t.analytics.reports.to} ${end}`
		: `${num(a.day, cal)} ${names[a.month - 1] ?? ""} ${t.analytics.reports.to} ${end}`;
}

/** The weeks to choose from, this one first: each named for its place in its month, with its days. */
export function weekOptions(count = 7, cal: CalendarName = "jalali", now = new Date()) {
	return Array.from({ length: count }, (_, back) => ({
		value: `w:${back}`,
		label: `${back === 0 ? `${t.analytics.reports.thisWeek}: ` : ""}${weekName(back, cal, now)} (${weekSpan(back, cal, now)})`,
	}));
}

/** The two ends of a custom range, from the documented form `2026-10-01..2026-10-31`. */
export function rangeOf(spec: string): { from: string; to: string } | null {
	const [from = "", to = ""] = spec.split("..");
	return /^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to) ? { from, to } : null;
}

/** «آبان ۱۴۰۵», «سال ۱۴۰۵», «هفتهٔ اول مهر» — from either the documented form or the API's own (`w:1`). */
export function periodLabel(spec: string, cal: CalendarName = "jalali"): string {
	const range = rangeOf(spec);
	if (range) {
		return `${formatDayIn(range.from, cal)} ${t.analytics.reports.to} ${formatDayIn(range.to, cal)}`;
	}
	if (spec === "week" || spec === "w:0") return t.analytics.reports.thisWeek;
	const weeksBack = /^w:(\d+)$/.exec(spec)?.[1];
	if (weeksBack) {
		return Number(weeksBack) === 1
			? t.analytics.reports.lastWeek
			: weekName(Number(weeksBack), cal);
	}
	const [year = "", month] = spec.split("-");
	if (month === undefined) return `${t.analytics.reports.yearWord} ${plain(year, cal)}`;
	return `${monthNames(cal)[Number(month) - 1] ?? month} ${plain(year, cal)}`;
}

/** What a period is, for the charts that show days in a week or month and months in a year. */
export function kindOf(spec: string): PeriodKind {
	const range = rangeOf(spec);
	if (range) {
		const days =
			(new Date(`${range.to}T12:00:00`).getTime() - new Date(`${range.from}T12:00:00`).getTime()) /
				86_400_000 +
			1;
		// A long stretch reads as months, like a year; a short one as days.
		return days > 62 ? "year" : "month";
	}
	return spec === "week" || spec.startsWith("w:") ? "week" : spec.includes("-") ? "month" : "year";
}

export function monthOptions(count = 12, cal: CalendarName = "jalali") {
	return recentPeriods(count, cal);
}

export function yearOptions(count = 4, cal: CalendarName = "jalali") {
	const year = Number(currentPeriod(cal).split("-")[0]);
	return Array.from({ length: count }, (_, back) => ({
		value: String(year - back),
		label: `${t.analytics.reports.yearWord} ${plain(year - back, cal)}`,
	}));
}

const partsOf: Record<CalendarName, Intl.DateTimeFormat> = {
	jalali: new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", { year: "numeric", month: "numeric" }),
	gregorian: new Intl.DateTimeFormat("en-u-ca-gregory-nu-latn", {
		year: "numeric",
		month: "numeric",
	}),
};

/** The month of the book's calendar an ISO day falls in, as the API's period and the month's name. */
export function monthOfDay(
	iso: string,
	cal: CalendarName = "jalali",
): { period: string; label: string } {
	const parts = partsOf[cal].formatToParts(new Date(`${iso}T12:00:00`));
	const pick = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
	const month = Number(pick("month"));
	return {
		period: `${pick("year")}-${String(month).padStart(2, "0")}`,
		label: monthNames(cal)[month - 1] ?? "",
	};
}
