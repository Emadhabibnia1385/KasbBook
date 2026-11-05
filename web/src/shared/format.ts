// Numbers, money and dates as a Persian reader expects them; screens never format by hand.
// Money arrives as a decimal string and stays a string until it is grouped, so no rial is lost to a float.

const digits = new Intl.NumberFormat("fa-IR", { useGrouping: false });

/** "1234567.5000" → "۱٬۲۳۴٬۵۶۷" (up to two decimals, none if they are zeros). */
export function formatAmount(value: string | number): string {
	const text = String(value).trim();
	const negative = text.startsWith("-");
	const [whole = "0", fraction = ""] = text.replace(/^[-+]/, "").split(".");
	const grouped = BigInt(whole || "0")
		.toString()
		.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
	const cents = fraction.slice(0, 2).replace(/0+$/, "");
	const out = cents ? `${grouped}.${cents}` : grouped;
	const persian = out
		.replace(/\d/g, (d) => digits.format(Number(d)))
		.replaceAll(",", "٬")
		.replace(".", "٫");
	return negative && out !== "0" ? `\u200E−${persian}` : persian;
}

const CURRENCY_NAMES: Record<string, string> = { IRT: "تومان", IRR: "ریال", USD: "دلار", EUR: "یورو", USDT: "تتر" };

export function currencyName(code: string): string {
	return CURRENCY_NAMES[code] ?? code;
}

export function formatMoney(value: string | number, currency: string): string {
	return `${formatAmount(value)} ${currencyName(currency)}`;
}

/** A compact figure for a chart's axis or a tight card: ۱٫۲ میلیون. */
export function formatCompact(value: number): string {
	const abs = Math.abs(value);
	const unit = abs >= 1e9 ? [1e9, "میلیارد"] : abs >= 1e6 ? [1e6, "میلیون"] : abs >= 1e3 ? [1e3, "هزار"] : null;
	if (!unit) return formatAmount(Math.round(value));
	const scaled = Math.round((value / (unit[0] as number)) * 10) / 10;
	return `${formatAmount(scaled)} ${unit[1]}`;
}

const dayFormat = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { day: "numeric", month: "long" });
const fullFormat = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "long", day: "numeric" });

/** An ISO date (2026-11-05) in the Jalali calendar: ۱۴ آبان. */
export function formatDay(iso: string): string {
	return dayFormat.format(new Date(`${iso}T12:00:00`));
}

export function formatFullDate(iso: string): string {
	return fullFormat.format(new Date(`${iso}T12:00:00`));
}

/** Western digits as typed on a phone's Persian keyboard, back to ASCII for the API. */
export function toAscii(text: string): string {
	return text
		.replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
		.replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
}

const periodParts = new Intl.DateTimeFormat("en-u-ca-persian-nu-latn", { year: "numeric", month: "numeric" });

/** The current Jalali month in the form the reports API takes: 1405-08. */
export function currentPeriod(now = new Date()): string {
	const parts = periodParts.formatToParts(now);
	const pick = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
	return `${pick("year")}-${pick("month").padStart(2, "0")}`;
}
