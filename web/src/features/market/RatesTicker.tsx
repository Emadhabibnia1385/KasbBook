import { formatAmount } from "@/shared/format";
import { t } from "@/strings";
import { useRates } from "./useRates";

// A strip of the prices a shop owner glances at, for the top bar of a wide screen. Silent when there is
// nothing to show: a bar must not announce that a price service is down.
export function RatesTicker() {
	const { data } = useRates("USDT/IRT,BTC/IRT,TON/IRT");
	if (!data?.length) return null;
	return (
		<ul
			aria-label={t.market.tickerLabel}
			className="flex min-w-0 items-center gap-4 overflow-hidden text-xs"
		>
			{data.map((rate) => (
				<li key={rate.pair} className="flex shrink-0 items-center gap-1">
					<span className="text-muted">{t.market.assets[rate.base] ?? rate.base}</span>
					<span
						dir="ltr"
						className={`font-semibold tabular-nums ${rate.stale ? "text-muted" : ""}`}
					>
						{formatAmount(rate.value, 0)}
					</span>
				</li>
			))}
		</ul>
	);
}
