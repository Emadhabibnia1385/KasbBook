// Jalali months as the API wants them: a Gregorian ISO window. The panel never carries its own calendar
// tables; it asks Intl which Gregorian day a Jalali day is, so it can not drift from the one on screen.

const DAY = 86_400_000;
const persian = new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", {
	timeZone: "UTC",
	year: "numeric",
	month: "numeric",
	day: "numeric",
});

const parseIso = (iso: string) => new Date(`${iso}T12:00:00Z`);
const toIso = (date: Date) => date.toISOString().slice(0, 10);

function jalaliOf(date: Date): { year: number; month: number; day: number } {
	const parts = persian.formatToParts(date);
	const pick = (type: string) => Number(parts.find((part) => part.type === type)?.value);
	return { year: pick("year"), month: pick("month"), day: pick("day") };
}

/** The Gregorian day on which Jalali month `month` of `year` begins. */
function monthStart(year: number, month: number): Date {
	const target = year * 12 + month;
	// Nowruz falls on 20–21 March; each month is 29–31 days, so this lands within a month of the answer.
	let guess = new Date(Date.UTC(year + 621, 2, 21, 12) + Math.round((month - 1) * 30.5) * DAY);
	for (let step = 0; step < 24; step += 1) {
		const now = jalaliOf(guess);
		const index = now.year * 12 + now.month;
		if (index === target) return new Date(guess.getTime() - (now.day - 1) * DAY);
		// Back to the last day of the previous month, or forward into the next one.
		guess = new Date(guess.getTime() + (index > target ? -now.day : 32 - now.day) * DAY);
	}
	return guess;
}

/** First and last day of a month given as "1405-08", counted by the Jalali calendar or, when asked, the Gregorian one. */
export function monthWindow(
	period: string,
	cal: "jalali" | "gregorian" = "jalali",
): { starts_on: string; ends_on: string } {
	const [year = 0, month = 1] = period.split("-").map(Number);
	if (cal === "gregorian") {
		const pad = (n: number) => String(n).padStart(2, "0");
		return {
			starts_on: `${year}-${pad(month)}-01`,
			// Day zero of the next month is the last day of this one.
			ends_on: toIso(new Date(Date.UTC(year, month, 0, 12))),
		};
	}
	const next = month === 12 ? monthStart(year + 1, 1) : monthStart(year, month + 1);
	return {
		starts_on: toIso(monthStart(year, month)),
		ends_on: toIso(new Date(next.getTime() - DAY)),
	};
}

/** The last day of the Jalali month an ISO date falls in. */
export function monthEndOf(iso: string): string {
	const { year, month } = jalaliOf(parseIso(iso));
	return monthWindow(`${year}-${String(month).padStart(2, "0")}`).ends_on;
}

/** Today in the device's own calendar day, as YYYY-MM-DD. */
export function todayIso(now = new Date()): string {
	const pad = (n: number) => String(n).padStart(2, "0");
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** An ISO date as the Gregorian local value Nasim's date field holds, and back. */
export const toFieldValue = (iso: string) => `${iso}T00:00`;
export const fromFieldValue = (value: string) => value.slice(0, 10);
