// An SVG label is laid out left to right, so a Persian one with digits ("۱۴ آبان", "۱٫۲ میلیون") would
// read in the wrong order. An isolate keeps the string in its own direction whatever surrounds it.
export function isolate(text: string): string {
	return `⁧${text}⁩`;
}

export function toNumber(value: string | null | undefined): number | null {
	if (value === null || value === undefined || value === "") return null;
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : null;
}
