import { EmptyState, ErrorState, PageSkeleton, SectionCard, StatusChip } from "@nyxon/nasim";
import { formatAmount } from "@/shared/format";
import { t } from "@/strings";
import { currencyName } from "@/shared/format";
import { ageText } from "./format";
import { useNowSeconds } from "@/shared/clock";
import { useTickerCodes } from "./tickerPrefs";
import { PriceBoard } from "./PriceBoard";
import { useQuotes } from "./useQuotes";
import { useTickerRows } from "./useTickerRows";

/** Today's prices of what was chosen for the strip (dollar, gold, coins, coins of crypto), and every other price below. */
export function RatesCard() {
	const codes = useTickerCodes();
	const ticker = useTickerRows(codes);
	const now = useNowSeconds();
	const rows = ticker.rows;
	const first = rows.find((row) => row.age > 0) ?? rows[0];
	const approximate = rows.some((row) => !row.exact);
	// Age as of this second: the server's age at fetch time plus however long ago that was received.
	const ageOf = (age: number) => age + Math.max(0, now - Math.floor(ticker.updatedAt / 1000));
	return (
		<SectionCard
			title={t.market.title}
			description={t.market.lead}
			actions={approximate ? <StatusChip tone="warning" label={t.fx.estimateShort} /> : undefined}
		>
			<div className="flex flex-col gap-3">
				{ticker.isLoading ? (
					<PageSkeleton header={false} rows={3} label={t.market.loading} />
				) : ticker.isError ? (
					<ErrorState message={t.market.unavailable} onRetry={ticker.refetch} />
				) : rows.length === 0 ? (
					<EmptyState title={t.market.empty} />
				) : (
					<>
						<ul className="flex flex-col">
							{rows.map((rate) => (
								<li
									key={rate.code}
									className="flex items-center justify-between gap-3 border-b border-separator py-2 last:border-b-0"
								>
									<span className="font-medium">{rate.name}</span>
									<span dir="ltr" className="text-sm font-semibold tabular-nums">
										{rate.exact ? "" : "≈ "}
										{formatAmount(rate.value, 0)} {t.money.toman}
									</span>
								</li>
							))}
						</ul>
						{first ? (
							<p className="text-xs text-muted">
								{t.market.updated} {ageText(ageOf(first.age))}
							</p>
						) : null}
					</>
				)}
				<PriceBoard />
			</div>
		</SectionCard>
	);
}

const COUNTRY_CODES = ["USD", "EUR", "GBP", "AED", "TRY", "CNY", "JPY", "CAD", "AUD", "CHF"];

/** National currencies in toman. No feed publishes these, so they are estimates and are labelled as such. */
export function CountryRates() {
	const quotes = useQuotes(COUNTRY_CODES, "IRT");
	const rows = quotes.data ?? [];
	if (rows.length === 0) return null;
	return (
		<SectionCard
			title={t.fx.countries}
			actions={<StatusChip tone="warning" label={t.fx.estimateShort} />}
		>
			<ul className="flex flex-col">
				{rows.map((row) => (
					<li
						key={row.code}
						className="flex items-center justify-between gap-3 border-b border-separator py-2 last:border-b-0"
					>
						<span className="font-medium">
							{currencyName(row.code)}{" "}
							<span dir="ltr" className="text-xs text-muted">
								{row.code}
							</span>
						</span>
						<span dir="ltr" className="text-sm font-semibold tabular-nums">
							{formatAmount(row.value, 0)} {t.money.toman}
						</span>
					</li>
				))}
			</ul>
		</SectionCard>
	);
}
