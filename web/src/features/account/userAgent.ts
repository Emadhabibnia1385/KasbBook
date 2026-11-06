// A browser's long user-agent string, boiled down to what a person recognises: «Chrome · macOS».
const BROWSERS: [RegExp, string][] = [
	[/Edg(?:e|A|iOS)?\//, "Edge"],
	[/OPR\/|Opera/, "Opera"],
	[/SamsungBrowser/, "Samsung Internet"],
	[/Firefox|FxiOS/, "Firefox"],
	[/Chrome|CriOS|Chromium/, "Chrome"],
	[/Safari/, "Safari"],
];
const SYSTEMS: [RegExp, string][] = [
	[/iPhone|iPad|iPod/, "iOS"],
	[/Android/, "Android"],
	[/Windows/, "Windows"],
	[/Mac OS X|Macintosh/, "macOS"],
	[/CrOS/, "ChromeOS"],
	[/Linux/, "Linux"],
];

export function describeAgent(agent: string | null | undefined, unknown: string): string {
	if (!agent) return unknown;
	const browser = BROWSERS.find(([pattern]) => pattern.test(agent))?.[1];
	const system = SYSTEMS.find(([pattern]) => pattern.test(agent))?.[1];
	if (!browser && !system) return unknown;
	return [browser ?? unknown, system].filter(Boolean).join(" · ");
}
