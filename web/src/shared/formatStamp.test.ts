import { describe, expect, it } from "vitest";
import { formatStamp } from "./format";

describe("formatStamp", () => {
	it("writes the whole moment in the Jalali calendar and the given zone", () => {
		expect(formatStamp("2026-11-06T10:50:35Z", "Asia/Tehran")).toBe("۱۴۰۵/۰۸/۱۵ - ۱۴:۲۰:۳۵");
	});
	it("reads a time with no zone as UTC", () => {
		expect(formatStamp("2026-11-06T10:50:35", "Asia/Tehran")).toBe("۱۴۰۵/۰۸/۱۵ - ۱۴:۲۰:۳۵");
	});
	it("does not break on nonsense", () => {
		expect(formatStamp("not a date", "Asia/Tehran")).toBe("—");
	});
});
