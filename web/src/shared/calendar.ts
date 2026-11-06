// The two calendars a day can be chosen in, as plain functions: a month's grid, a typed date read back,
// a day written out. Everything is keyed by the ISO day (2026-11-06), which is what the API takes and what
// both calendars convert to and from, so the field can switch between them without changing the value.
import { monthWindow } from "@/features/payroll/calendar";
import { toAscii } from "@/shared/format";
import {
	daysInJalaliMonth,
	jalaliOfIso,
	normalizeDayText,
	shiftIso,
	toPersianDigits,
} from "./jalaliDay";

export type CalendarKind = "jalali" | "gregorian";

export type MonthGrid = {
	year: number;
	month: number;
	/** Blank cells before the 1st, so day one lands under its weekday. */
	lead: number;
	days: { day: number; iso: string }[];
};

const pad = (n: number) => String(n).padStart(2, "0");
const weekday = (iso: string) => new Date(`${iso}T12:00:00Z`).getUTCDay(); // 0 = Sunday

/** The Jalali month's days; the week starts on Saturday. */
export function jalaliGrid(year: number, month: number): MonthGrid {
	const first = monthWindow(`${year}-${pad(month)}`).starts_on;
	return {
		year,
		month,
		lead: (weekday(first) + 1) % 7,
		days: Array.from({ length: daysInJalaliMonth(year, month) }, (_, i) => ({
			day: i + 1,
			iso: shiftIso(first, i),
		})),
	};
}

/** The Gregorian month's days; the week starts on Monday, as it does wherever this calendar is the one used. */
export function gregorianGrid(year: number, month: number): MonthGrid {
	const first = `${year}-${pad(month)}-01`;
	const length = new Date(Date.UTC(year, month, 0)).getUTCDate();
	return {
		year,
		month,
		lead: (weekday(first) + 6) % 7,
		days: Array.from({ length }, (_, i) => ({
			day: i + 1,
			iso: `${year}-${pad(month)}-${pad(i + 1)}`,
		})),
	};
}

export function gridFor(kind: CalendarKind, year: number, month: number): MonthGrid {
	return kind === "jalali" ? jalaliGrid(year, month) : gregorianGrid(year, month);
}

/** Which year and month of this calendar an ISO day falls in. */
export function monthOf(kind: CalendarKind, iso: string): { year: number; month: number } {
	if (kind === "jalali") {
		const parts = jalaliOfIso(iso);
		if (parts) return { year: parts.year, month: parts.month };
	}
	const [year, month] = iso.split("-").map(Number);
	return { year: year ?? 2026, month: month ?? 1 };
}

/** The month before or after, rolling the year. */
export function stepMonth(
	year: number,
	month: number,
	by: 1 | -1,
): { year: number; month: number } {
	const index = year * 12 + (month - 1) + by;
	return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

/** A typed Gregorian day: «2026/11/06», «2026-11-6», «20261106», in any digits. */
export function parseGregorianDay(
	text: string,
): { ok: true; iso: string } | { ok: false; empty: boolean; partial: boolean } {
	const folded = toAscii(normalizeDayText(text));
	if (folded === "") return { ok: false, empty: true, partial: false };
	const match =
		/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/.exec(folded) ?? /^(\d{4})(\d{2})(\d{2})$/.exec(folded);
	if (!match)
		return {
			ok: false,
			empty: false,
			partial: /^\d{1,7}$/.test(folded) || /^\d{0,4}(\/\d{0,2}){1,2}$/.test(folded),
		};
	const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])] as const;
	const date = new Date(Date.UTC(year, month - 1, day));
	// A date that rolls over (Feb 30 becoming Mar 2) is not that day.
	const real =
		year >= 1900 &&
		year <= 2200 &&
		date.getUTCFullYear() === year &&
		date.getUTCMonth() === month - 1 &&
		date.getUTCDate() === day;
	return real
		? { ok: true, iso: `${year}-${pad(month)}-${pad(day)}` }
		: { ok: false, empty: false, partial: false };
}

/** An ISO day as it is typed in a calendar: «۱۴۰۵/۰۸/۱۵» or «2026/11/06». Empty for anything else. */
export function writeDay(kind: CalendarKind, iso: string): string {
	if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "";
	if (kind === "jalali") {
		const parts = jalaliOfIso(iso);
		return parts ? toPersianDigits(`${parts.year}/${pad(parts.month)}/${pad(parts.day)}`) : "";
	}
	return iso.replaceAll("-", "/");
}

export const JALALI_MONTHS = [
	"فروردین",
	"اردیبهشت",
	"خرداد",
	"تیر",
	"مرداد",
	"شهریور",
	"مهر",
	"آبان",
	"آذر",
	"دی",
	"بهمن",
	"اسفند",
];
export const GREGORIAN_MONTHS = [
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
];
export const JALALI_WEEK = ["ش", "ی", "د", "س", "چ", "پ", "ج"];
export const GREGORIAN_WEEK = ["M", "T", "W", "T", "F", "S", "S"];
