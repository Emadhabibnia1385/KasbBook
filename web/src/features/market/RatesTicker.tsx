import { formatAmount } from "@/shared/format";
import { t } from "@/strings";
import { useHeaderPrefs } from "./headerPrefs";
import { useTickerCodes } from "./tickerPrefs";
import { useTickerRows } from "./useTickerRows";

// A strip of the prices a shop owner glances at, for the top bar of a wide screen: the currencies chosen
// in the settings (Tether, Tron and TON until then). Silent when there is nothing to show: a bar must not
// announce that a price service is down.
export function RatesTicker() {
	const codes = useTickerCodes();
	const show = useHeaderPrefs().prices;
	// Switched off: nothing is shown, and nothing is asked of the market for it.
	const { rows } = useTickerRows(codes, show);
	if (!show || !rows.length) return null;
	return (
		<ul
			aria-label={t.market.tickerLabel}
			className="flex min-w-0 items-center gap-4 overflow-hidden text-xs"
		>
			{rows.map((rate) => (
				<li key={rate.code} className="flex shrink-0 items-center gap-1">
					<span className="text-muted">{rate.name}</span>
					<span dir="ltr" className="font-semibold tabular-nums">
						{rate.exact ? "" : "≈ "}
						{formatAmount(rate.value, 0)}
					</span>
				</li>
			))}
		</ul>
	);
}
