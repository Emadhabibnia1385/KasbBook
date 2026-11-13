const DEFAULT_PER_PAGE = 20;
// The API's own ceiling: asking for more would be refused rather than shown.
export const MAX_PER_PAGE = 10000;
const KEY = "kasbbook.transactionsPerPage";

/** The page size this person chose last time; a stored value that is not a sane number is ignored. */
export function savedPerPage(): number {
	try {
		const value = Number(localStorage.getItem(KEY));
		return Number.isInteger(value) && value >= 1 && value <= MAX_PER_PAGE
			? value
			: DEFAULT_PER_PAGE;
	} catch {
		return DEFAULT_PER_PAGE;
	}
}

export function rememberPerPage(value: number) {
	try {
		localStorage.setItem(KEY, String(value));
	} catch {
		// the next visit simply starts on the default
	}
}
