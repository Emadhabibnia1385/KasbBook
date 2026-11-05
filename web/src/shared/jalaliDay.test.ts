import { describe, expect, it } from "vitest";
import { formatJalaliDay, jalaliOfIso, parseJalaliDay, shiftIso } from "./jalaliDay";

describe("parseJalaliDay", () => {
	it("reads a real day in any digits and separators", () => {
		for (const text of ["1405/08/15", "۱۴۰۵/۰۸/۱۵", "1405-8-15", "14050815", "۱۴۰۵.۸.۱۵"]) {
			const parsed = parseJalaliDay(text);
			expect(parsed.ok, text).toBe(true);
			if (parsed.ok) expect(jalaliOfIso(parsed.iso)).toEqual({ year: 1405, month: 8, day: 15 });
		}
	});

	it("knows the length of every month, including the leap Esfand", () => {
		expect(parseJalaliDay("1403/12/30").ok).toBe(true);
		const flat = parseJalaliDay("1404/12/30");
		expect(flat).toMatchObject({ ok: false, reason: "day", daysInMonth: 29 });
		expect(parseJalaliDay("1405/06/31").ok).toBe(true);
		expect(parseJalaliDay("1405/07/31")).toMatchObject({
			ok: false,
			reason: "day",
			daysInMonth: 30,
		});
	});

	it("says which part is wrong", () => {
		expect(parseJalaliDay("1405/13/01")).toMatchObject({ ok: false, reason: "month" });
		expect(parseJalaliDay("4015/01/01")).toMatchObject({ ok: false, reason: "year" });
		expect(parseJalaliDay("hello")).toMatchObject({ ok: false, reason: "format" });
		expect(parseJalaliDay("")).toMatchObject({ ok: false, reason: "empty" });
	});

	it("does not call a day still being typed wrong", () => {
		for (const text of ["1405", "1405/0", "1405/08/", "14050"]) {
			expect(parseJalaliDay(text), text).toMatchObject({ ok: false, reason: "partial" });
		}
	});

	it("round-trips through the ISO day the API takes", () => {
		const parsed = parseJalaliDay("1405/01/01");
		expect(parsed.ok && parsed.iso).toBe("2026-03-21");
		expect(formatJalaliDay("2026-03-21")).toBe("۱۴۰۵/۰۱/۰۱");
		expect(formatJalaliDay("not a day")).toBe("");
	});
});

describe("shiftIso", () => {
	it("moves by whole days across a month end", () => {
		expect(shiftIso("2026-03-31", 1)).toBe("2026-04-01");
		expect(shiftIso("2026-03-01", -1)).toBe("2026-02-28");
	});
});
