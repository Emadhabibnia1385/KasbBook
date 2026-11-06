import { describe, expect, it } from "vitest";
import { describeAgent } from "./userAgent";

const CHROME_MAC =
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";
const SAFARI_IPHONE =
	"Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const EDGE_WINDOWS =
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0";

describe("describeAgent", () => {
	it("names the browser and the system, not the whole string", () => {
		expect(describeAgent(CHROME_MAC, "؟")).toBe("Chrome · macOS");
		expect(describeAgent(SAFARI_IPHONE, "؟")).toBe("Safari · iOS");
		expect(describeAgent(EDGE_WINDOWS, "؟")).toBe("Edge · Windows");
	});
	it("says so when it cannot tell", () => {
		expect(describeAgent(null, "ناشناس")).toBe("ناشناس");
		expect(describeAgent("curl/8.0", "ناشناس")).toBe("ناشناس");
	});
});
