import { SectionCard } from "@nyxon/nasim";
import { useAnalyticsForeignFlows } from "@/api/generated/analytics/analytics";
import type { BookResponse } from "@/api/generated/model";
import { useQuotes } from "@/features/market/useQuotes";
import { currencyName, formatMoney } from "@/shared/format";
import { t } from "@/strings";

/** «+۲٫۳٪» style change of `now` against `then`, or nothing when there was nothing to compare. */
function Difference({ now, then, goodWhenUp }: { now: number; then: number; goodWhenUp: boolean }) {
	const diff = now - then;
	if (!Number.isFinite(diff) || Math.round(diff) === 0)
		return <span className="text-muted">—</span>;
	const up = diff > 0;
	const good = up === goodWhenUp;
	return (
		<span dir="ltr" className={good ? "text-success" : "text-danger"}>
			{up ? "+" : "−"}
			{Math.abs(Math.round(diff)).toLocaleString("en")}
		</span>
	);
}

type Line = {
	key: string;
	label: string;
	native: string;
	code: string;
	recorded: string;
	goodWhenUp: boolean;
};

/**
 * The money paid in other currencies during a period, set against today's price: what each amount
 * was worth in the book's currency when it was recorded, and what it would be worth now. The book's
 * own figures stay at the recorded rate; this only shows how far the market has moved since.
 */
export function ForeignPanel({ book, period }: { book: BookResponse; period: string }) {
	const flows = useAnalyticsForeignFlows(book.id, { period });
	const rows = flows.data ?? [];
	const quotes = useQuotes(
		rows.map((row) => row.currency),
		book.currency,
		rows.length > 0,
	);
	if (rows.length === 0) return null;
	const rateOf = (code: string) => {
		const found = quotes.data?.find((quote) => quote.code === code);
		return found ? Number(found.value) : null;
	};
	return (
		<SectionCard title={t.foreign.title} description={t.foreign.lead}>
			<div className="flex flex-col gap-4">
				{rows.map((row) => {
					const rate = rateOf(row.currency);
					const lines: Line[] = [
						{
							key: "income",
							label: t.common.income,
							native: row.income,
							code: row.currency,
							recorded: row.income_recorded,
							goodWhenUp: true,
						},
						{
							key: "expense",
							label: t.common.expense,
							native: row.expense,
							code: row.currency,
							recorded: row.expense_recorded,
							goodWhenUp: false,
						},
					].filter((line) => Number(line.native) > 0);
					return (
						<section key={row.currency} className="flex flex-col gap-2">
							<div className="flex flex-wrap items-baseline justify-between gap-2">
								<h3 className="font-semibold">
									{currencyName(row.currency)}{" "}
									<span className="text-xs text-muted">{row.currency}</span>
								</h3>
								<span className="text-sm text-muted">
									{rate === null
										? t.foreign.noRate
										: `${t.foreign.todayRate}: ${formatMoney(String(rate), book.currency)}`}
								</span>
							</div>
							<ul className="flex flex-col gap-2">
								{lines.map((line) => {
									const now = rate === null ? null : Number(line.native) * rate;
									return (
										<li
											key={line.key}
											className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-xl border border-border bg-surface p-3 text-sm sm:grid-cols-4"
										>
											<span className="flex flex-col">
												<span className="text-xs text-muted">{line.label}</span>
												<b>{formatMoney(line.native, line.code)}</b>
											</span>
											<span className="flex flex-col">
												<span className="text-xs text-muted">{t.foreign.atRecording}</span>
												<b>{formatMoney(line.recorded, book.currency)}</b>
											</span>
											<span className="flex flex-col">
												<span className="text-xs text-muted">{t.foreign.atToday}</span>
												<b>
													{now === null ? "—" : formatMoney(String(Math.round(now)), book.currency)}
												</b>
											</span>
											<span className="flex flex-col">
												<span className="text-xs text-muted">{t.foreign.difference}</span>
												<b>
													{now === null ? (
														"—"
													) : (
														<Difference
															now={now}
															then={Number(line.recorded)}
															goodWhenUp={line.goodWhenUp}
														/>
													)}
												</b>
											</span>
										</li>
									);
								})}
							</ul>
						</section>
					);
				})}
			</div>
		</SectionCard>
	);
}
