import { useSyncExternalStore } from "react";

// Which currencies the price strip and the prices card list. A taste of this device, so it lives here and
// not on the server: nobody else sees the strip, and it should not need a request to change.
const KEY = "kasbbook.ticker";
export const DEFAULT_TICKER = ["USDT", "TRX", "TON"];
export const MAX_TICKER = 6;

const listeners = new Set<() => void>();
let cached: readonly string[] | null = null;

function read(): readonly string[] {
	if (cached) return cached;
	try {
		const raw = localStorage.getItem(KEY);
		const parsed = raw ? (JSON.parse(raw) as unknown) : null;
		if (
			Array.isArray(parsed) &&
			parsed.every((code) => typeof code === "string") &&
			parsed.length > 0
		) {
			cached = parsed.slice(0, MAX_TICKER);
			return cached;
		}
	} catch {
		// unreadable: the defaults serve
	}
	cached = DEFAULT_TICKER;
	return cached;
}

export function setTickerCodes(codes: readonly string[]) {
	const next = codes.length > 0 ? codes.slice(0, MAX_TICKER) : DEFAULT_TICKER;
	cached = next;
	try {
		localStorage.setItem(KEY, JSON.stringify(next));
	} catch {
		// the choice lasts until the page is closed
	}
	listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void) => {
	listeners.add(listener);
	window.addEventListener("storage", () => {
		cached = null;
		listener();
	});
	return () => listeners.delete(listener);
};

export function useTickerCodes(): readonly string[] {
	return useSyncExternalStore(subscribe, read, () => DEFAULT_TICKER);
}
