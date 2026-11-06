import { describe, expect, it } from "vitest";
import { kindOf, periodLabel, rangeOf, weekBounds, weekName, weekOptions } from "./periods";

// Friday 6 November 2026.
const NOW = new Date(2026, 10, 6, 12);

describe("weeks", () => {
	it("run Monday to Sunday on a Gregorian book", () => {
		expect(weekBounds(0, "gregorian", NOW)).toEqual({ from: "2026-11-02", to: "2026-11-08" });
		expect(weekBounds(1, "gregorian", NOW)).toEqual({ from: "2026-10-26", to: "2026-11-01" });
	});

	it("run Saturday to Friday on a Jalali book", () => {
		expect(weekBounds(0, "jalali", NOW)).toEqual({ from: "2026-10-31", to: "2026-11-06" });
	});

	it("are named for their place in their month", () => {
		expect(weekName(0, "gregorian", NOW)).toBe("هفتهٔ اول نوامبر");
		expect(weekName(1, "gregorian", NOW)).toBe("هفتهٔ چهارم اکتبر");
		expect(weekName(0, "jalali", NOW)).toBe("هفتهٔ دوم آبان");
	});

	it("are listed newest first, the current one marked", () => {
		const options = weekOptions(7, "gregorian", NOW);
		expect(options).toHaveLength(7);
		expect(options[0]?.value).toBe("w:0");
		expect(options[0]?.label).toContain("این هفته");
		expect(options[6]?.value).toBe("w:6");
	});
});

describe("custom ranges", () => {
	it("are read from the documented form", () => {
		expect(rangeOf("2026-10-01..2026-10-31")).toEqual({ from: "2026-10-01", to: "2026-10-31" });
		expect(rangeOf("1405-08")).toBeNull();
	});

	it("are labelled in the book's calendar", () => {
		expect(periodLabel("2026-10-01..2026-10-31", "gregorian")).toContain("اکتبر ۲۰۲۶");
		expect(periodLabel("2026-10-01..2026-10-31", "jalali")).toContain("مهر ۱۴۰۵");
	});

	it("read as days when short and as months when long", () => {
		expect(kindOf("2026-10-01..2026-10-20")).toBe("month");
		expect(kindOf("2026-01-01..2026-12-31")).toBe("year");
		expect(kindOf("w:2")).toBe("week");
	});
});
