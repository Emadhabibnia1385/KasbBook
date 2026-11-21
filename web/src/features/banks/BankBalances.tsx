import { SectionCard } from "@nyxon/nasim";
import { useBanksListForBook, useBanksListMine } from "@/api/generated/banks/banks";
import type { BankAccountResponse, BookResponse } from "@/api/generated/model";
import { Loaded } from "@/features/analytics/Loaded";
import { categoryColor, Donut, type Slice } from "@/shared/charts";
import { addMoney } from "@/shared/decimal";
import { formatCompact, formatMoney } from "@/shared/format";
import { t } from "@/strings";

/**
 * How one account's money divides between the books that use it: a ring with every book named, its
 * share and its exact amount. The opening balance is a slice of its own, because it belongs to no
 * book; a book that is out of pocket (a negative share) shows in the list but not in the ring.
 */
export function BankShareDonut({
	bank,
	currency,
	highlightBookId,
}: {
	bank: BankAccountResponse;
	currency: string;
	highlightBookId?: string;
}) {
	const slices: Slice[] = bank.shares.map((share, index) => ({
		key: share.book_id,
		label:
			share.book_id === highlightBookId
				? `${share.book_name} (${t.banks.thisBook})`
				: share.book_name,
		value: share.balance,
		color: categoryColor(index),
	}));
	if (Number(bank.opening_balance) !== 0) {
		slices.push({
			key: "opening",
			label: t.banks.openingLine,
			value: bank.opening_balance,
			color: categoryColor(slices.length),
		});
	}
	return (
		<Donut
			title={`${t.banks.shareTitle}: ${bank.title}`}
			hideTitle
			summary={`${bank.title}: ${slices.map((slice) => slice.label).join("، ")}`}
			slices={slices}
			formatValue={(value) => formatMoney(value, currency)}
			center={{ label: t.banks.total, value: formatCompact(Number(bank.total_balance)) }}
			emptyText={t.banks.balancesEmpty}
		/>
	);
}

/** This book's own share of each account it uses, as a ring and a list. */
export function BankBalances({ book }: { book: BookResponse }) {
	const query = useBanksListForBook(book.id);
	return (
		<SectionCard title={t.banks.balancesTitle} description={t.banks.balancesHint}>
			<Loaded query={query}>
				{(rows) => {
					// Someone who may not view reports gets no balance; there is nothing to draw for them.
					const shown = rows.filter((row) => row.balance !== null && row.balance !== undefined);
					if (rows.length === 0)
						return <p className="text-sm text-muted">{t.banks.balancesEmpty}</p>;
					const slices: Slice[] = shown.map((row, index) => ({
						key: row.id,
						label: row.title,
						value: row.balance ?? "0",
						color: categoryColor(index),
					}));
					const total = addMoney("0", ...shown.map((row) => row.balance ?? "0"));
					return (
						<Donut
							title={t.banks.balancesTitle}
							hideTitle
							summary={`${t.banks.balancesTitle}: ${slices.map((slice) => slice.label).join("، ")}`}
							slices={slices}
							formatValue={(value) => formatMoney(value, book.currency)}
							center={{ label: t.banks.balancesCenter, value: formatCompact(Number(total)) }}
							emptyText={t.banks.noFlows}
						/>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}

/**
 * Every account you own, and how much of it is for this book and how much for the others: the owner's
 * view, since only the owner may see what the other books did.
 */
export function BankSplitPanel({ book }: { book: BookResponse }) {
	const query = useBanksListMine();
	return (
		<SectionCard title={t.banks.shareTitle} description={t.banks.shareHint}>
			<Loaded query={query}>
				{(banks) => {
					const mine = banks.filter(
						(bank) =>
							bank.currency === book.currency && bank.shares.some((s) => s.book_id === book.id),
					);
					if (mine.length === 0)
						return <p className="text-sm text-muted">{t.banks.balancesEmpty}</p>;
					return (
						<div className="grid gap-6 lg:grid-cols-2">
							{mine.map((bank) => {
								const here = bank.shares.find((s) => s.book_id === book.id)?.balance ?? "0";
								const others = addMoney(
									"0",
									...bank.shares.filter((s) => s.book_id !== book.id).map((s) => s.balance),
								);
								return (
									<div key={bank.id} className="flex flex-col gap-3">
										<h3 className="font-semibold">{bank.title}</h3>
										<BankShareDonut
											bank={bank}
											currency={book.currency}
											highlightBookId={book.id}
										/>
										<p className="text-sm text-muted">
											{t.banks.thisBook}:{" "}
											<b className="text-foreground">{formatMoney(here, book.currency)}</b>
											{" · "}
											{t.banks.otherBooks}:{" "}
											<b className="text-foreground">{formatMoney(others, book.currency)}</b>
										</p>
									</div>
								);
							})}
						</div>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}
