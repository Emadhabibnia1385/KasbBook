import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The store keeps its choice in module memory, so each test starts from a fresh copy of it.
async function fresh() {
	vi.resetModules();
	return import("./headerPrefs");
}

describe("header preferences", () => {
	beforeEach(() => localStorage.clear());

	it("shows everything until told otherwise", async () => {
		const { useHeaderPrefs, DEFAULT_HEADER } = await fresh();
		expect(renderHook(() => useHeaderPrefs()).result.current).toEqual(DEFAULT_HEADER);
	});

	it("switches one part off, remembers it, and tells every screen showing it", async () => {
		const { useHeaderPrefs, setHeaderPref } = await fresh();
		const { result } = renderHook(() => useHeaderPrefs());
		act(() => setHeaderPref("gregorian", false));
		expect(result.current.gregorian).toBe(false);
		expect(result.current.jalali).toBe(true);
		expect(JSON.parse(localStorage.getItem("kasbbook.header") ?? "{}").gregorian).toBe(false);
	});

	it("keeps the default for a part a saved choice never mentioned, and ignores junk", async () => {
		localStorage.setItem(
			"kasbbook.header",
			JSON.stringify({ time: false, weekday: "no", extra: true }),
		);
		const { useHeaderPrefs } = await fresh();
		const prefs = renderHook(() => useHeaderPrefs()).result.current;
		expect(prefs.time).toBe(false);
		expect(prefs.weekday).toBe(true);
		expect(prefs.prices).toBe(true);
	});

	it("survives an unreadable saved choice and can be reset", async () => {
		localStorage.setItem("kasbbook.header", "{nope");
		const { useHeaderPrefs, setHeaderPref, resetHeaderPrefs } = await fresh();
		const { result } = renderHook(() => useHeaderPrefs());
		expect(result.current.time).toBe(true);
		act(() => setHeaderPref("time", false));
		act(() => resetHeaderPrefs());
		expect(result.current.time).toBe(true);
		expect(localStorage.getItem("kasbbook.header")).toBeNull();
	});
});
