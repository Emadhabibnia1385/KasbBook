import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Recharts measures its container with ResizeObserver, which jsdom does not have.
class ResizeObserverStub {
	observe() {}
	unobserve() {}
	disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverStub);

/** `matchMedia` for the one query the charts ask; a test sets `reduced` before rendering. */
export const media = { reduced: false };

window.matchMedia = (query: string) =>
	({
		matches: query.includes("prefers-reduced-motion") ? media.reduced : false,
		media: query,
		onchange: null,
		addEventListener: () => {},
		removeEventListener: () => {},
		addListener: () => {},
		removeListener: () => {},
		dispatchEvent: () => false,
	}) as MediaQueryList;

afterEach(() => {
	cleanup();
	media.reduced = false;
});
