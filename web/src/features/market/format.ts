import { formatAmount } from "@/shared/format";
import { t } from "@/strings";

export const DEFAULT_ZONE = "Asia/Tehran";

type Formatters = { date: Intl.DateTimeFormat; time: Intl.DateTimeFormat };
const cache = new Map<string, Formatters>();

function formattersFor(zone: string): Formatters {
	const hit = cache.get(zone);
	if (hit) return hit;
	const made: Formatters = {
		date: new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
			weekday: "long",
			year: "numeric",
			month: "long",
			day: "numeric",
			timeZone: zone,
		}),
		// h23: a Persian locale's default 12-hour clock would turn midnight into «۱۲:۰۰».
		time: new Intl.DateTimeFormat("fa-IR", {
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
			hourCycle: "h23",
			timeZone: zone,
		}),
	};
	cache.set(zone, made);
	return made;
}

/** An account can hold a zone this browser does not know; the clock then shows Tehran rather than nothing. */
function safeZone(zone: string | undefined): string {
	if (!zone) return DEFAULT_ZONE;
	try {
		new Intl.DateTimeFormat("en", { timeZone: zone });
		return zone;
	} catch {
		return DEFAULT_ZONE;
	}
}

const numeric = new Map<string, { jalali: Intl.DateTimeFormat; gregorian: Intl.DateTimeFormat }>();

const weekdays = new Map<string, Intl.DateTimeFormat>();

/** «جمعه»: the day of the week, in words, in the given zone. */
export function weekdayName(seconds: number, zone?: string): string {
	const key = safeZone(zone);
	let format = weekdays.get(key);
	if (!format) {
		format = new Intl.DateTimeFormat("fa-IR", { weekday: "long", timeZone: key });
		weekdays.set(key, format);
	}
	return format.format(new Date(seconds * 1000));
}

/** Both calendars as numbers with slashes: «۱۴۰۵/۰۸/۱۵» and «2026/11/06», in the given zone. */
export function numericDates(
	seconds: number,
	zone?: string,
): { jalali: string; gregorian: string } {
	const key = safeZone(zone);
	let formats = numeric.get(key);
	if (!formats) {
		const parts = { year: "numeric", month: "2-digit", day: "2-digit", timeZone: key } as const;
		formats = {
			jalali: new Intl.DateTimeFormat("fa-IR-u-ca-persian", parts),
			gregorian: new Intl.DateTimeFormat("en-CA-u-nu-latn", parts),
		};
		numeric.set(key, formats);
	}
	const at = new Date(seconds * 1000);
	// fa-IR writes «۱۴۰۵/۰۸/۱۵» already; en-CA writes «2026-11-06», and the slash is what is asked for.
	return {
		jalali: formats.jalali.format(at),
		gregorian: formats.gregorian.format(at).replaceAll("-", "/"),
	};
}

/** «جمعه ۱۵ آبان ۱۴۰۵» in the given zone. */
export function jalaliDate(seconds: number, zone?: string): string {
	return formattersFor(safeZone(zone)).date.format(new Date(seconds * 1000));
}

/** «۱۴:۰۵:۰۹», Persian digits, 24-hour. */
export function clockTime(seconds: number, zone?: string): string {
	return formattersFor(safeZone(zone)).time.format(new Date(seconds * 1000));
}

/** «همین حالا», «۱۲ ثانیه پیش», «۳ دقیقه پیش»: how long ago, in the unit a person would say. */
export function ageText(totalSeconds: number): string {
	const age = t.market.age;
	const seconds = Math.max(0, Math.floor(totalSeconds));
	if (seconds < 5) return age.now;
	if (seconds < 60) return `${formatAmount(seconds)} ${age.seconds}`;
	if (seconds < 3600) return `${formatAmount(Math.floor(seconds / 60))} ${age.minutes}`;
	if (seconds < 86_400) return `${formatAmount(Math.floor(seconds / 3600))} ${age.hours}`;
	return `${formatAmount(Math.floor(seconds / 86_400))} ${age.days}`;
}
