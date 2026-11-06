import { useSyncExternalStore } from "react";

// Whether the round quick-actions button is shown. A taste of this device, so it lives here and not on the
// server, like the header's parts; on unless switched off.
const KEY = "kasbbook.quick";
const listeners = new Set<() => void>();

function read(): boolean {
	try {
		return localStorage.getItem(KEY) !== "off";
	} catch {
		return true;
	}
}

export function setQuickEnabled(on: boolean) {
	try {
		localStorage.setItem(KEY, on ? "on" : "off");
	} catch {
		// the choice lasts until the page is closed
	}
	listeners.forEach((listener) => listener());
}

export function useQuickEnabled(): boolean {
	return useSyncExternalStore(
		(listener) => {
			listeners.add(listener);
			window.addEventListener("storage", listener);
			return () => {
				listeners.delete(listener);
				window.removeEventListener("storage", listener);
			};
		},
		read,
		() => true,
	);
}
