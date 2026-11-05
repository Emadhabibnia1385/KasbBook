import { useMarketRates } from "@/api/generated/market/market";
import { useNowSeconds } from "@/shared/clock";

const MINUTE = 60_000;

/** The market's prices, asked again every minute while a screen shows them. */
export function useRates(pairs?: string) {
	const query = useMarketRates(pairs ? { pairs } : undefined, {
		query: {
			refetchInterval: MINUTE,
			// A paused tab asks nothing; coming back, the next tick is at most a minute away.
			refetchIntervalInBackground: false,
			staleTime: MINUTE / 2,
			// A failed poll keeps showing the last good prices instead of blanking the card.
			retry: 1,
		},
	});
	const now = useNowSeconds();
	// Age as of this second: the server's age at fetch time plus however long ago that was received.
	const ageOf = (ageSeconds: number) =>
		ageSeconds + Math.max(0, now - Math.floor(query.dataUpdatedAt / 1000));
	return { ...query, ageOf };
}
