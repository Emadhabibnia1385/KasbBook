import {
	EmptyState,
	ErrorState,
	Notice,
	PageSkeleton,
	SectionCard,
	StatusChip,
} from "@nyxon/nasim";
import type { MarketRateResponse } from "@/api/generated/model";
import { formatAmount } from "@/shared/format";
import { t } from "@/strings";
import { ageText } from "./format";
import { useRates } from "./useRates";

const asset = (code: string) =>
	t.market.assets[code] ? `${t.market.assets[code]} (${code})` : code;
const quoteName = (code: string) => (code === "IRT" ? t.money.toman : code);

// Toman prices are whole numbers in daily use; a USDT-quoted price (BTC) needs its places.
const priceText = (rate: MarketRateResponse) =>
	`${formatAmount(rate.value, rate.quote === "IRT" ? 0 : 4)} ${quoteName(rate.quote)}`;

/** Live prices with their source and age; the age counts up by itself between refreshes. */
export function RatesCard() {
	const rates = useRates();
	const rows = rates.data ?? [];
	const first = rows[0];
	return (
		<SectionCard
			title={t.market.title}
			description={t.market.lead}
			actions={first?.stale ? <StatusChip tone="warning" label={t.market.staleShort} /> : undefined}
		>
			{rates.isLoading ? (
				<PageSkeleton header={false} rows={3} label={t.market.loading} />
			) : rates.isError && rows.length === 0 ? (
				<ErrorState message={t.market.unavailable} onRetry={() => void rates.refetch()} />
			) : rows.length === 0 ? (
				<EmptyState title={t.market.empty} />
			) : (
				<div className="flex flex-col gap-3">
					{first?.stale ? (
						<Notice tone="warning" title={t.market.staleTitle}>
							{t.market.staleBody}
						</Notice>
					) : null}
					{rates.isError ? <Notice tone="warning">{t.market.refreshFailed}</Notice> : null}
					<ul className="flex flex-col">
						{rows.map((rate) => (
							<li
								key={rate.pair}
								className="flex items-center justify-between gap-3 border-b border-separator py-2 last:border-b-0"
							>
								<span className="font-medium">{asset(rate.base)}</span>
								<span dir="ltr" className="text-sm font-semibold tabular-nums">
									{priceText(rate)}
								</span>
							</li>
						))}
					</ul>
					{first ? (
						<p className="text-xs text-muted">
							{t.market.sourceLabel}: {t.market.sources[first.source] ?? first.source} ·{" "}
							{t.market.updated} {ageText(rates.ageOf(first.age_seconds))}
						</p>
					) : null}
				</div>
			)}
		</SectionCard>
	);
}
