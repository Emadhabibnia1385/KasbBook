// A day typed in the Jalali calendar, read back as the ISO day the API takes. The calendar itself is the
// browser's (Intl, via the payroll calendar's month windows), so the length of a month and the leap
// Esfand agree with every other date on screen and with the server's.
import { monthWindow } from "@/features/payroll/calendar";
import { toAscii } from "@/shared/format";

const DAY = 86_400_000;

export type DayParse =
	| { ok: true; year: number; month: number; day: number; iso: string }
	| {
			ok: false;
			/**
			 * `empty` nothing typed; `partial` a day still being typed; `format` not shaped like a date;
			 * `year`, `month`, `day` the shape is right and that part is not a real one.
			 */
			reason: "empty" | "partial" | "format" | "year" | "month" | "day";
			/** For `day`: how long the month is, so the message can say it. */
			daysInMonth?: number;
	  };

// Years a small business can plausibly mean; a typo such as 4015 is told apart from a real date.
const FIRST_YEAR = 1300;
const LAST_YEAR = 1499;

// Direction marks a copy-paste brings along, and every dash or dot or slash a person might separate with.
const INVISIBLE = /[\s​-‏‪-‮⁦-⁩]/g;
const SEPARATORS = /[-–—−‐./\\٫]/g;

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function toPersianDigits(text: string): string {
	return text.replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)] ?? digit);
}

/** Persian, Arabic or Latin digits and any separator, folded to «1405/8/15»-shaped ASCII. */
export function normalizeDayText(text: string): string {
	return toAscii(text).replace(INVISIBLE, "").replace(SEPARATORS, "/");
}

export function daysInJalaliMonth(year: number, month: number): number {
	const { starts_on, ends_on } = monthWindow(`${year}-${String(month).padStart(2, "0")}`);
	return (
		Math.round((Date.parse(`${ends_on}T12:00:00Z`) - Date.parse(`${starts_on}T12:00:00Z`)) / DAY) +
		1
	);
}

/** `iso` moved by whole days; days are counted in UTC noon so no clock change can skip or repeat one. */
export function shiftIso(iso: string, days: number): string {
	return new Date(Date.parse(`${iso}T12:00:00Z`) + days * DAY).toISOString().slice(0, 10);
}

/** Reads «۱۴۰۵/۰۸/۱۵», «1405-8-15» or «14050815»; says what is wrong when it is not a real Jalali day. */
export function parseJalaliDay(text: string): DayParse {
	const folded = normalizeDayText(text);
	if (folded === "") return { ok: false, reason: "empty" };

	const separated = /^(\d{4})\/(\d{1,2})\/(\d{1,2})$/.exec(folded);
	const packed = /^(\d{4})(\d{2})(\d{2})$/.exec(folded);
	const match = separated ?? packed;
	if (!match) {
		// Still on its way to a date (1405, 1405/0, 14050): not wrong yet.
		return /^\d{1,7}$/.test(folded) || /^\d{0,4}(\/\d{0,2}){1,2}$/.test(folded)
			? { ok: false, reason: "partial" }
			: { ok: false, reason: "format" };
	}
	const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])] as const;
	if (year < FIRST_YEAR || year > LAST_YEAR) return { ok: false, reason: "year" };
	if (month < 1 || month > 12) return { ok: false, reason: "month" };
	const length = daysInJalaliMonth(year, month);
	if (day < 1 || day > length) return { ok: false, reason: "day", daysInMonth: length };

	const first = monthWindow(`${year}-${String(month).padStart(2, "0")}`).starts_on;
	return { ok: true, year, month, day, iso: shiftIso(first, day - 1) };
}

const jalaliParts = new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", {
	timeZone: "UTC",
	year: "numeric",
	month: "numeric",
	day: "numeric",
});

/** The Jalali day an ISO day falls on, or null for something that is not an ISO day. */
export function jalaliOfIso(iso: string): { year: number; month: number; day: number } | null {
	if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
	const date = new Date(`${iso}T12:00:00Z`);
	if (Number.isNaN(date.getTime())) return null;
	const parts = jalaliParts.formatToParts(date);
	const pick = (type: string) => Number(parts.find((part) => part.type === type)?.value);
	return { year: pick("year"), month: pick("month"), day: pick("day") };
}

/** An ISO day as it is typed here: «۱۴۰۵/۰۸/۱۵». Empty for anything that is not a day. */
export function formatJalaliDay(iso: string): string {
	const parts = jalaliOfIso(iso);
	if (!parts) return "";
	const pad = (n: number) => String(n).padStart(2, "0");
	return toPersianDigits(`${parts.year}/${pad(parts.month)}/${pad(parts.day)}`);
}
