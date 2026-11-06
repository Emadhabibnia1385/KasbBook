import { describe, expect, it } from "vitest";
import { monthEndOf, monthWindow } from "./calendar";
import { ceilDivide, isPositive, isZero, multiply, plain, sameAmount, sum } from "./decimal";

describe("decimal", () => {
	it("compares and sums without a float", () => {
		expect(sameAmount("70000000.0000", "70000000")).toBe(true);
		expect(sum(["0.1", "0.2", "-0.3"])).toBe("0.0000");
		expect(isZero("-0.0000")).toBe(true);
		expect(isPositive("0.0001")).toBe(true);
	});

	it("rounds a token settlement up, never short", () => {
		expect(ceilDivide("1000000", "0.0003")).toBe("3333333333.3334");
		expect(multiply("40", "600000")).toBe("24000000.0000");
	});

	it("gives a stored figure back as it would be typed", () => {
		expect(plain("50.0000")).toBe("50");
		expect(plain("1.2500")).toBe("1.25");
		expect(plain("100")).toBe("100");
	});
});

describe("calendar", () => {
	it("opens a Jalali month on the right Gregorian days", () => {
		expect(monthWindow("1405-08")).toEqual({ starts_on: "2026-10-23", ends_on: "2026-11-21" });
		expect(monthWindow("1405-01")).toEqual({ starts_on: "2026-03-21", ends_on: "2026-04-20" });
	});

	it("knows a leap Esfand", () => {
		expect(monthWindow("1403-12").ends_on).toBe("2025-03-20");
		expect(monthWindow("1403-12").starts_on).toBe("2025-02-19");
	});

	it("counts a Gregorian month by the usual days", () => {
		expect(monthWindow("2026-02", "gregorian")).toEqual({
			starts_on: "2026-02-01",
			ends_on: "2026-02-28",
		});
		expect(monthWindow("2028-02", "gregorian").ends_on).toBe("2028-02-29");
		expect(monthWindow("2026-12", "gregorian").ends_on).toBe("2026-12-31");
	});

	it("finds the end of the month a day falls in", () => {
		expect(monthEndOf("2026-11-05")).toBe("2026-11-21");
	});
});
