// Numbers, money and dates as a Persian reader expects them; screens never format by hand.
// Money arrives as a decimal string and stays a string until it is grouped, so no rial is lost to a float.

/** "1234.5000" → "1235", with half rounded away from zero, on the decimal string so no float is involved. */
function roundWhole(text: string): string {
	const negative = text.startsWith("-");
	const [whole = "0", fraction = ""] = text.replace(/^[-+]/, "").split(".");
	const up = (fraction[0] ?? "0") >= "5";
	const rounded = (BigInt(whole || "0") + (up ? 1n : 0n)).toString();
	return negative && rounded !== "0" ? `-${rounded}` : rounded;
}

const digits = new Intl.NumberFormat("fa-IR", { useGrouping: false });

/** "1234567.5000" → "۱٬۲۳۴٬۵۶۷" (up to `decimals` places, none if they are zeros). */
export function formatAmount(value: string | number, decimals = 2): string {
	const text = String(value).trim();
	const negative = text.startsWith("-");
	const [whole = "0", fraction = ""] = text.replace(/^[-+]/, "").split(".");
	const grouped = BigInt(whole || "0")
		.toString()
		.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
	const cents = fraction.slice(0, decimals).replace(/0+$/, "");
	const out = cents ? `${grouped}.${cents}` : grouped;
	const persian = out
		.replace(/\d/g, (d) => digits.format(Number(d)))
		.replaceAll(",", "٬")
		.replace(".", "٫");
	return negative && out !== "0" ? `\u200E−${persian}` : persian;
}

type CatalogEntry = { code: string; name: string; symbol: string; kind: string };

// The names the panel can use before the catalog has arrived; the catalog replaces them.
const NAMES: Record<string, CatalogEntry> = {
	IRT: { code: "IRT", name: "تومان", symbol: "تومان", kind: "fiat" },
	IRR: { code: "IRR", name: "ریال", symbol: "ریال", kind: "fiat" },
	USD: { code: "USD", name: "دلار آمریکا", symbol: "$", kind: "fiat" },
	EUR: { code: "EUR", name: "یورو", symbol: "€", kind: "fiat" },
	USDT: { code: "USDT", name: "تتر", symbol: "USDT", kind: "crypto" },
};
const CACHE_KEY = "kasbbook.currencies";

try {
	const cached = localStorage.getItem(CACHE_KEY);
	if (cached) for (const row of JSON.parse(cached) as CatalogEntry[]) NAMES[row.code] = row;
} catch {
	// no cache: the built-in names serve until the catalog is fetched
}

/** Remember the catalog, so a currency has its Persian name from the first paint of the next visit. */
export function registerCurrencies(rows: readonly CatalogEntry[]) {
	for (const row of rows) NAMES[row.code] = row;
	try {
		localStorage.setItem(CACHE_KEY, JSON.stringify(rows));
	} catch {
		// the names last for this visit only
	}
}

export function currencyName(code: string): string {
	return NAMES[code]?.name ?? code;
}

// Toman and rial have no cents in daily use: «۹٬۸۲۳٬۰۲۱٫۸۱ تومان» is noise, and it widens every card.
// Everything else follows the server's four stored places: two for a currency's cents, four for a coin.
function decimalsFor(code: string): number {
	if (code === "IRT" || code === "IRR") return 0;
	return NAMES[code]?.kind === "crypto" ? 4 : 2;
}

export function formatMoney(value: string | number, currency: string): string {
	const decimals = decimalsFor(currency);
	const text = String(value).trim();
	const shown = decimals === 0 ? roundWhole(text) : text;
	return `${formatAmount(shown, decimals)} ${currencyName(currency)}`;
}

/** A compact figure for a chart's axis or a tight card: ۱٫۲ میلیون. */
export function formatCompact(value: number): string {
	const abs = Math.abs(value);
	const unit =
		abs >= 1e9
			? [1e9, "میلیارد"]
			: abs >= 1e6
				? [1e6, "میلیون"]
				: abs >= 1e3
					? [1e3, "هزار"]
					: null;
	if (!unit) return formatAmount(Math.round(value));
	const scaled = Math.round((value / (unit[0] as number)) * 10) / 10;
	return `${formatAmount(scaled)} ${unit[1]}`;
}

const dayFormat = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { day: "numeric", month: "long" });
const fullFormat = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
	year: "numeric",
	month: "long",
	day: "numeric",
});

/** An ISO date (2026-11-05) in the Jalali calendar: ۱۴ آبان. */
export function formatDay(iso: string): string {
	return dayFormat.format(new Date(`${iso}T12:00:00`));
}

export function formatFullDate(iso: string): string {
	return fullFormat.format(new Date(`${iso}T12:00:00`));
}

/**
 * A moment in full, in the Jalali calendar and the person's own time zone: ۱۴۰۵/۰۸/۱۵ - ۱۴:۲۰:۳۵.
 * A server time without a zone is read as UTC, which is what the server writes.
 */
export function formatStamp(iso: string, zone?: string): string {
	const value = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "—";
	let parts: Intl.DateTimeFormatPart[];
	try {
		parts = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
			timeZone: zone,
			year: "numeric",
			month: "2-digit",
			day: "2-digit",
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
			hourCycle: "h23",
		}).formatToParts(date);
	} catch {
		return "—";
	}
	const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
	return `${get("year")}/${get("month")}/${get("day")} - ${get("hour")}:${get("minute")}:${get("second")}`;
}

/** Western digits as typed on a phone's Persian keyboard, back to ASCII for the API. */
export function toAscii(text: string): string {
	return text
		.replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
		.replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
}

const periodParts = new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", {
	year: "numeric",
	month: "numeric",
});

/** The current Jalali month in the form the reports API takes: 1405-08. */
export function currentPeriod(now = new Date()): string {
	const parts = periodParts.formatToParts(now);
	const pick = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
	return `${pick("year")}-${pick("month").padStart(2, "0")}`;
}

export const MONTHS = [
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

/** The last `count` Jalali months, newest first, as the API's period and a label to show. */
export function recentPeriods(count: number, now = new Date()): { value: string; label: string }[] {
	const [year = 0, month = 1] = currentPeriod(now).split("-").map(Number);
	return Array.from({ length: count }, (_, back) => {
		const index = year * 12 + (month - 1) - back;
		const y = Math.floor(index / 12);
		const m = (index % 12) + 1;
		return {
			value: `${y}-${String(m).padStart(2, "0")}`,
			label: `${MONTHS[m - 1]} ${formatAmount(y).replace(/[٬,]/g, "")}`,
		};
	});
}
