// The time zones the browser knows, each with its offset, so a person can find theirs by name or by clock.
export type ZoneOption = { value: string; label: string };

const offsetOf = (zone: string): string => {
	try {
		const parts = new Intl.DateTimeFormat("en", { timeZone: zone, timeZoneName: "shortOffset" })
			.formatToParts(new Date())
			.find((part) => part.type === "timeZoneName");
		return (parts?.value ?? "").replace("GMT", "UTC") || "UTC";
	} catch {
		return "";
	}
};

/** The zone this browser is in, or null when it will not say. */
export function browserZone(): string | null {
	try {
		return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
	} catch {
		return null;
	}
}

export function zoneOptions(current: string): ZoneOption[] {
	let names: string[] = [];
	try {
		names =
			(Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.(
				"timeZone",
			) ?? [];
	} catch {
		names = [];
	}
	// The zone already saved is always offered, even if this browser's list lacks it.
	const all = new Set([...names, current, "Asia/Tehran"]);
	return [...all]
		.sort((a, b) => a.localeCompare(b))
		.map((zone) => ({ value: zone, label: `${zone.replaceAll("_", " ")} (${offsetOf(zone)})` }));
}
