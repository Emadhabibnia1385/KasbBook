import { describe, expect, it } from "vitest";
import { formatOtherCalendar } from "./format";

describe("formatOtherCalendar", () => {
	it("writes a Jalali book's day as a Gregorian date", () => {
		expect(formatOtherCalendar("2026-11-05", "jalali")).toBe("2026/11/05");
	});

	it("writes a Gregorian book's day as a Jalali date", () => {
		expect(formatOtherCalendar("2026-11-05", "gregorian")).toBe("۱۴۰۵/۰۸/۱۴");
	});
});
