import { Collapsible } from "@nyxon/nasim";
import { usePortfolioInstruments } from "@/api/generated/portfolio/portfolio";
import { formatMoney } from "@/shared/format";
import { t } from "@/strings";

const GROUPS = ["gold", "coin", "metal", "currency", "crypto"] as const;

/** Today's price of gold, coins, metals, the main currencies and coins, in toman, with where each came from. */
export function PriceBoard() {
	const instruments =
		usePortfolioInstruments({
			query: { staleTime: 60_000, refetchInterval: 300_000 },
		}).data ?? [];
	if (instruments.length === 0) return null;
	return (
		<Collapsible title={t.market.allPrices} description={t.portfolio.pricesLead}>
			<div className="flex flex-col gap-4">
				{GROUPS.map((group) => {
					const items = instruments.filter(
						(item) => item.group === group && item.source !== "manual",
					);
					if (items.length === 0) return null;
					return (
						<section key={group} className="flex flex-col gap-1">
							<h3 className="text-sm font-semibold text-muted">{t.portfolio.groups[group]}</h3>
							<ul className="flex flex-col">
								{items.map((item) => (
									<li
										key={item.code}
										className="flex items-center justify-between gap-3 border-b border-separator py-2 text-sm last:border-b-0"
									>
										<span>
											{item.name} <span className="text-xs text-muted">/ {item.unit}</span>
										</span>
										<span className="flex flex-col items-end">
											<b>{item.price ? formatMoney(item.price, "IRT") : "—"}</b>
											{item.price ? (
												<span className="text-xs text-muted">
													{t.portfolio.sources[
														item.price_source as keyof typeof t.portfolio.sources
													] ?? item.price_source}
												</span>
											) : null}
										</span>
									</li>
								))}
							</ul>
						</section>
					);
				})}
			</div>
		</Collapsible>
	);
}
