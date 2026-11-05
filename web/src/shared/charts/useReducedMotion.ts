import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(listener: () => void) {
	const media = window.matchMedia(QUERY);
	media.addEventListener("change", listener);
	return () => media.removeEventListener("change", listener);
}

/** True when the person asked their system for less motion: charts then draw without animating. */
export function useReducedMotion(): boolean {
	return useSyncExternalStore(
		subscribe,
		() => window.matchMedia(QUERY).matches,
		() => true,
	);
}
