// Adding and subtracting amounts that arrive as strings, without ever turning them into floats.
// Four decimal places is the API's scale (Numeric(28, 4)), so a figure is a whole number of ten-thousandths.

const SCALE = 10_000n;

function toUnits(value: string): bigint {
	const text = value.trim();
	const [whole = "0", fraction = ""] = text.replace(/^[-+]/, "").split(".");
	const units = BigInt(whole || "0") * SCALE + BigInt(fraction.padEnd(4, "0").slice(0, 4) || "0");
	return text.startsWith("-") ? -units : units;
}

function fromUnits(units: bigint): string {
	const abs = units < 0n ? -units : units;
	return `${units < 0n ? "-" : ""}${abs / SCALE}.${(abs % SCALE).toString().padStart(4, "0")}`;
}

export function addMoney(...values: string[]): string {
	return fromUnits(values.reduce((sum, value) => sum + toUnits(value), 0n));
}

export function subtractMoney(from: string, take: string): string {
	return fromUnits(toUnits(from) - toUnits(take));
}

export function negateMoney(value: string): string {
	return fromUnits(-toUnits(value));
}

/**
 * `amount × rate` rounded half up to four places, on the decimal strings so no float is involved.
 * The rate may carry up to ten places (a price per unit); an unreadable input gives "".
 */
export function multiplyMoney(amount: string, rate: string): string {
	const parse = (text: string): [bigint, number] | null => {
		const clean = text.trim();
		if (!/^\d+(\.\d+)?$/.test(clean)) return null;
		const [whole = "0", fraction = ""] = clean.split(".");
		const places = Math.min(fraction.length, 10);
		return [BigInt(whole + fraction.slice(0, places)), places];
	};
	const a = parse(amount);
	const r = parse(rate);
	if (!a || !r) return "";
	const product = a[0] * r[0];
	const shift = a[1] + r[1] - 4; // down to ten-thousandths
	let units = product;
	if (shift > 0) {
		const divisor = 10n ** BigInt(shift);
		units = (product + divisor / 2n) / divisor;
	} else if (shift < 0) {
		units = product * 10n ** BigInt(-shift);
	}
	return fromUnits(units);
}
