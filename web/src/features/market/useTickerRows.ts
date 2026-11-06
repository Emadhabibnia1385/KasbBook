import { useMemo } from "react";
import { usePortfolioInstruments } from "@/api/generated/portfolio/portfolio";
import { currencyName } from "@/shared/format";
import { useQuotes } from "./useQuotes";

export type TickerRow = { code: string; name: string; value: string; exact: boolean; age: number };

const NOT_A_CURRENCY = (source: string) => source === "iran" || source === "world";

/**
 * The prices the strip and the card list, in toman: gold, coins and metals from the instrument feed, and
 * every currency or coin from the quote feed. The order is the one chosen, and a code nobody can price
 * yet is left out rather than shown empty.
 */
export function useTickerRows(codes: readonly string[], enabled = true) {
	const instruments = usePortfolioInstruments({
		query: { enabled, staleTime: 60_000, refetchInterval: 300_000 },
	});
	const things = useMemo(
		() =>
			new Map(
				(instruments.data ?? [])
					.filter((item) => NOT_A_CURRENCY(item.source))
					.map((item) => [item.code, item]),
			),
		[instruments.data],
	);
	// Until the instrument list arrives a code is asked of the quote feed only if it cannot be a gold or coin.
	const currencies = codes.filter(
		(code) => !things.has(code) && !/^(gold|coin_|mesghal|silver|X[A-Z]{2}$)/.test(code),
	);
	const quotes = useQuotes(currencies, "IRT", enabled);
	const rows = useMemo(() => {
		const out: TickerRow[] = [];
		for (const code of codes) {
			const thing = things.get(code);
			if (thing) {
				if (thing.price) {
					out.push({
						code,
						name: thing.name,
						value: String(thing.price),
						exact: Boolean(thing.exact),
						age: 0,
					});
				}
				continue;
			}
			const quote = quotes.data?.find((row) => row.code === code);
			if (quote) {
				out.push({
					code,
					name: currencyName(code),
					value: String(quote.value),
					exact: quote.exact,
					age: quote.age_seconds ?? 0,
				});
			}
		}
		return out;
	}, [codes, things, quotes.data]);
	return {
		rows,
		isLoading: quotes.isLoading || instruments.isLoading,
		isError: quotes.isError && rows.length === 0,
		refetch: () => {
			void quotes.refetch();
			void instruments.refetch();
		},
		updatedAt: quotes.dataUpdatedAt,
	};
}
