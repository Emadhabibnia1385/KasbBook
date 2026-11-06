import { currencyName, formatAmount } from "@/shared/format";
import { t } from "@/strings";
import { useHeaderPrefs } from "./headerPrefs";
import { useTickerCodes } from "./tickerPrefs";
import { useQuotes } from "./useQuotes";

// A strip of the prices a shop owner glances at, for the top bar of a wide screen: the currencies chosen
// in the settings (Tether, Tron and TON until then). Silent when there is nothing to show: a bar must not
// announce that a price service is down.
export function RatesTicker() {
	const codes = useTickerCodes();
	const show = useHeaderPrefs().prices;
	// Switched off: nothing is shown, and nothing is asked of the market for it.
	const { data } = useQuotes(codes, "IRT", show);
	if (!show || !data?.length) return null;
	return (
		<ul
			aria-label={t.market.tickerLabel}
			className="flex min-w-0 items-center gap-4 overflow-hidden text-xs"
		>
			{data.map((rate) => (
				<li key={rate.code} className="flex shrink-0 items-center gap-1">
					<span className="text-muted">{currencyName(rate.code)}</span>
					<span dir="ltr" className="font-semibold tabular-nums">
						{rate.exact ? "" : "≈ "}
						{formatAmount(rate.value, 0)}
					</span>
				</li>
			))}
		</ul>
	);
}
