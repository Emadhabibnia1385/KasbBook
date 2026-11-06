import { useSyncExternalStore } from "react";

// What the bar at the top of the page shows. Each part can be switched off; a taste of this device, so it is
// kept here and not on the server, like the price strip's currencies.
const KEY = "kasbbook.header";

export type HeaderPrefs = {
	/** The ticking clock. */
	time: boolean;
	/** «جمعه». */
	weekday: boolean;
	/** «۱۴۰۵/۰۸/۱۵». */
	jalali: boolean;
	/** «2026/11/06». */
	gregorian: boolean;
	/** The strip of prices (which currencies is a separate choice). */
	prices: boolean;
};

export const DEFAULT_HEADER: HeaderPrefs = {
	time: true,
	weekday: true,
	jalali: true,
	gregorian: true,
	prices: true,
};

const listeners = new Set<() => void>();
let cached: HeaderPrefs | null = null;

function read(): HeaderPrefs {
	if (cached) return cached;
	try {
		const raw = localStorage.getItem(KEY);
		const parsed = raw ? (JSON.parse(raw) as Partial<HeaderPrefs>) : {};
		// A part the saved choice does not mention keeps its default, so adding one later does not hide it.
		cached = {
			...DEFAULT_HEADER,
			...Object.fromEntries(Object.entries(parsed).filter(([, v]) => typeof v === "boolean")),
		};
	} catch {
		cached = DEFAULT_HEADER;
	}
	return cached;
}

export function setHeaderPref(part: keyof HeaderPrefs, on: boolean) {
	cached = { ...read(), [part]: on };
	try {
		localStorage.setItem(KEY, JSON.stringify(cached));
	} catch {
		// the choice lasts until the page is closed
	}
	listeners.forEach((listener) => listener());
}

export function resetHeaderPrefs() {
	cached = DEFAULT_HEADER;
	try {
		localStorage.removeItem(KEY);
	} catch {
		// nothing to remove
	}
	listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void) => {
	listeners.add(listener);
	const onStorage = () => {
		cached = null;
		listener();
	};
	window.addEventListener("storage", onStorage);
	return () => {
		listeners.delete(listener);
		window.removeEventListener("storage", onStorage);
	};
};

export const useHeaderPrefs = (): HeaderPrefs =>
	useSyncExternalStore(subscribe, read, () => DEFAULT_HEADER);
