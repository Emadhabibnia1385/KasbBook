import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { closeQuick, openQuick, useQuick } from "./quickBus";
import { setQuickEnabled, useQuickEnabled } from "./quickPrefs";

afterEach(() => {
	localStorage.clear();
	act(() => closeQuick());
});

describe("quick actions button", () => {
	it("is on until it is switched off, and remembers the choice", () => {
		const { result } = renderHook(() => useQuickEnabled());
		expect(result.current).toBe(true);
		act(() => setQuickEnabled(false));
		expect(result.current).toBe(false);
		expect(localStorage.getItem("kasbbook.quick")).toBe("off");
		act(() => setQuickEnabled(true));
		expect(result.current).toBe(true);
	});

	it("opens one dialog at a time, from anywhere, and closes it", () => {
		const { result } = renderHook(() => useQuick());
		expect(result.current).toBeNull();
		act(() => openQuick("transaction"));
		expect(result.current).toBe("transaction");
		act(() => openQuick("category"));
		expect(result.current).toBe("category");
		act(() => closeQuick());
		expect(result.current).toBeNull();
	});
});
