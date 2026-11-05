// Money here is a decimal string end to end. The few sums and comparisons a payroll screen needs are done
// on integers of 1/10000 (the scale the server stores), so no rial is ever rounded by a float.

const SCALE = 4;
const UNIT = 10n ** BigInt(SCALE);

/** "-12.5" → -125000n (units of 1/10000). Anything past four places is dropped, as the server does. */
export function toUnits(value: string): bigint {
	const text = value.trim();
	const negative = text.startsWith("-");
	const [whole = "0", fraction = ""] = text.replace(/^[-+]/, "").split(".");
	const units =
		BigInt(whole || "0") * UNIT + BigInt(fraction.slice(0, SCALE).padEnd(SCALE, "0") || "0");
	return negative ? -units : units;
}

export function fromUnits(units: bigint): string {
	const negative = units < 0n;
	const abs = negative ? -units : units;
	const whole = abs / UNIT;
	const fraction = (abs % UNIT).toString().padStart(SCALE, "0");
	return `${negative ? "-" : ""}${whole}.${fraction}`;
}

export const isZero = (value: string) => toUnits(value) === 0n;
export const isNegative = (value: string) => toUnits(value) < 0n;
export const isPositive = (value: string) => toUnits(value) > 0n;
export const sameAmount = (a: string, b: string) => toUnits(a) === toUnits(b);

export function sum(values: readonly string[]): string {
	return fromUnits(values.reduce((total, value) => total + toUnits(value), 0n));
}

/** amount × rate, to four places: what a payment in a token was worth in the payslip's own currency. */
export function multiply(amount: string, rate: string): string {
	return fromUnits((toUnits(amount) * toUnits(rate) + UNIT / 2n) / UNIT);
}

/** amount ÷ rate, rounded up to four places: a payslip settled in a token must not land a hair short. */
export function ceilDivide(amount: string, rate: string): string {
	const divisor = toUnits(rate);
	if (divisor <= 0n) return fromUnits(0n);
	return fromUnits((toUnits(amount) * UNIT + divisor - 1n) / divisor);
}

/** "50.0000" → "50", "1.2500" → "1.25": a stored figure as a person would type it back. */
export function plain(value: string): string {
	return value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
}

/** Never negative, as a number, for the length of a bar only. */
export const barLength = (value: string) => Math.max(0, Number(value));
