import { useMarketQuotes } from "@/api/generated/market/market";

const MINUTE = 60_000;

/** What one unit of each code is worth in `base`, refreshed every minute while a screen shows it. */
export function useQuotes(codes: readonly string[], base: string, enabled = true) {
	return useMarketQuotes(
		{ base, codes: codes.join(",") },
		{
			query: {
				enabled: enabled && codes.length > 0,
				refetchInterval: MINUTE,
				staleTime: MINUTE / 2,
				retry: 1,
			},
		},
	);
}

/** A figure that is not a price the market publishes must be shown as an estimate, in words. */
export const sourceName = (source: string): string =>
	source
		.split("+")
		.map(
			(part) => ({ swapwallet: "سواپ‌ولت", "exchangerate-api": "exchangerate-api" })[part] ?? part,
		)
		.join(" + ");
