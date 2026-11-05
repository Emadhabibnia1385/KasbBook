// The date picker speaks `YYYY-MM-DDTHH:mm`; the API speaks `YYYY-MM-DD`. These two bridge them.

/** The day of a picker value: "2026-11-05T12:00" → "2026-11-05", "" stays "". */
export function pickedDay(value: string): string {
	return value.slice(0, 10);
}

/** Today as the picker takes it, by the clock on the person's own device. */
export function todayPicker(now = new Date()): string {
	const pad = (n: number) => String(n).padStart(2, "0");
	return toPicker(`${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`);
}

/** A day the API sent, as the picker takes it. Noon, so no time zone can move it to another day. */
export function toPicker(day: string | null | undefined): string {
	return day ? `${day.slice(0, 10)}T12:00` : "";
}
