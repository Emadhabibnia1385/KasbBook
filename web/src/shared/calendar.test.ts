import { describe, expect, it } from "vitest";
import {
	gregorianGrid,
	jalaliGrid,
	monthOf,
	parseGregorianDay,
	stepMonth,
	writeDay,
} from "./calendar";

describe("grids", () => {
	it("lays a Jalali month under the right weekdays, week starting Saturday", () => {
		// 1 Farvardin 1405 is Saturday 21 March 2026: no blank cells before it.
		const month = jalaliGrid(1405, 1);
		expect(month.lead).toBe(0);
		expect(month.days).toHaveLength(31);
		expect(month.days[0]?.iso).toBe("2026-03-21");
		expect(month.days.at(-1)?.iso).toBe("2026-04-20");
		// 1405 is not leap (1404 is), so Esfand has 29 days.
		expect(jalaliGrid(1405, 12).days).toHaveLength(29);
		expect(jalaliGrid(1403, 12).days).toHaveLength(30);
	});

	it("lays a Gregorian month with the week starting Monday", () => {
		const november = gregorianGrid(2026, 11); // 1 Nov 2026 is a Sunday
		expect(november.lead).toBe(6);
		expect(november.days).toHaveLength(30);
		expect(gregorianGrid(2024, 2).days).toHaveLength(29);
	});

	it("finds a day's month in either calendar and steps across years", () => {
		expect(monthOf("jalali", "2026-11-06")).toEqual({ year: 1405, month: 8 });
		expect(monthOf("gregorian", "2026-11-06")).toEqual({ year: 2026, month: 11 });
		expect(stepMonth(1405, 12, 1)).toEqual({ year: 1406, month: 1 });
		expect(stepMonth(2026, 1, -1)).toEqual({ year: 2025, month: 12 });
	});
});

describe("typing and writing days", () => {
	it("reads Gregorian days in any digits and separators, and refuses ones that do not exist", () => {
		for (const text of ["2026/11/06", "2026-11-6", "20261106", "۲۰۲۶/۱۱/۰۶"]) {
			expect(parseGregorianDay(text), text).toEqual({ ok: true, iso: "2026-11-06" });
		}
		expect(parseGregorianDay("2026/02/30")).toMatchObject({ ok: false, partial: false });
		expect(parseGregorianDay("2026/13/01")).toMatchObject({ ok: false });
		expect(parseGregorianDay("2026/1")).toMatchObject({ ok: false, partial: true });
		expect(parseGregorianDay("")).toMatchObject({ ok: false, empty: true });
	});

	it("writes the same day in both calendars", () => {
		expect(writeDay("jalali", "2026-11-06")).toBe("۱۴۰۵/۰۸/۱۵");
		expect(writeDay("gregorian", "2026-11-06")).toBe("2026/11/06");
		expect(writeDay("jalali", "nonsense")).toBe("");
	});
});
