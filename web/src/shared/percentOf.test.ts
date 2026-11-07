import { describe, expect, it } from "vitest";
import { percentOf } from "./decimal";

describe("percentOf", () => {
	it("takes a share of a balance without a float", () => {
		expect(percentOf("1000", 50)).toBe("500");
		expect(percentOf("1000.5000", 25)).toBe("250.125");
		expect(percentOf("1000", 100)).toBe("1000");
	});

	it("rounds down, never asking for more than there is", () => {
		expect(percentOf("0.0003", 50)).toBe("0.0001");
		expect(percentOf("1000.0001", 75)).toBe("750");
	});

	it("gives nothing for what is not a plain amount", () => {
		expect(percentOf("", 50)).toBe("");
		expect(percentOf("-5", 50)).toBe("");
	});
});
