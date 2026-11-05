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
