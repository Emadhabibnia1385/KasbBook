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

/** What holding a currency's net amount from the day it was recorded until now has gained or lost. */
function Result({ value, base }: { value: number; base: string }) {
	const good = value >= 0;
	return (
		<b dir="ltr" className={good ? "text-success" : "text-danger"}>
			{good ? "+" : "−"}
			{formatMoney(String(Math.abs(Math.round(value))), base)}
		</b>
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
export function ForeignPanel({
	book,
	period,
	asReport = false,
}: {
	book: BookResponse;
	period: string;
	/** The full report: a profit-and-loss summary on top, and an explanation when there is nothing to show. */
	asReport?: boolean;
}) {
	const flows = useAnalyticsForeignFlows(book.id, { period });
	const rows = flows.data ?? [];
	const quotes = useQuotes(
		rows.map((row) => row.currency),
		book.currency,
		rows.length > 0,
	);
	if (rows.length === 0) {
		return asReport && !flows.isLoading ? (
			<SectionCard title={t.foreign.reportTitle}>
				<p className="text-sm text-muted">{t.foreign.noForeign}</p>
			</SectionCard>
		) : null;
	}
	const rateOf = (code: string) => {
		const found = quotes.data?.find((quote) => quote.code === code);
		return found ? Number(found.value) : null;
	};
	// The net amount held, as recorded and as worth now: its difference is the profit or loss.
	const positions = rows.map((row) => {
		const rate = rateOf(row.currency);
		const net = Number(row.income) - Number(row.expense);
		const recorded = Number(row.income_recorded) - Number(row.expense_recorded);
		return { row, net, recorded, now: rate === null ? null : net * rate };
	});
	const known = positions.every((position) => position.now !== null);
	const total = positions.reduce((sum, p) => sum + (p.now === null ? 0 : p.now - p.recorded), 0);
	return (
		<SectionCard
			title={asReport ? t.foreign.reportTitle : t.foreign.title}
			description={asReport ? t.foreign.reportLead : t.foreign.lead}
		>
			<div className="flex flex-col gap-4">
				{asReport ? (
					<div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-3">
						<ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
							{positions.map(({ row, net, recorded, now }) => (
								<li key={row.currency} className="flex flex-col gap-1 text-sm">
									<span className="font-medium">
										{currencyName(row.currency)}{" "}
										<span className="text-xs text-muted">{t.foreign.netPosition}</span>
									</span>
									<b>{formatMoney(String(net), row.currency)}</b>
									<span className="text-xs text-muted">
										{t.foreign.valueRecorded}:{" "}
										{formatMoney(String(Math.round(recorded)), book.currency)}
									</span>
									<span className="text-xs text-muted">
										{t.foreign.valueNow}:{" "}
										{now === null ? "—" : formatMoney(String(Math.round(now)), book.currency)}
									</span>
									{now === null ? null : (
										<span>
											{now - recorded >= 0 ? t.foreign.profit : t.foreign.loss}:{" "}
											<Result value={now - recorded} base={book.currency} />
										</span>
									)}
								</li>
							))}
						</ul>
						<p className="border-t border-separator pt-2 text-sm">
							<span className="text-muted">{t.foreign.totalResult}: </span>
							<Result value={total} base={book.currency} />
							{known ? null : <span className="text-xs text-muted"> — {t.foreign.partial}</span>}
						</p>
					</div>
				) : null}
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
