import type { BookResponse, TransactionResponse } from "@/api/generated/model";

/** The two facts about a book that an amount needs: which currency it adds up in. */
export type BookRef = Pick<BookResponse, "id" | "currency">;
import { formatMoney } from "@/shared/format";

/**
 * What a transaction was, in the money it was paid in. A payment of 20 TON is «۲۰ تون», with what it
 * was worth in the book's currency when it was recorded beneath it; only a book-currency payment is
 * just its amount. Reports add the second figure, so this shows both without choosing between them.
 */
export function Amount({
	row,
	book,
	align = "end",
}: {
	row: TransactionResponse;
	book: BookRef;
	align?: "start" | "end";
}) {
	const income = row.flow === "income";
	const foreign = row.original_currency !== book.currency;
	const sign = income ? "+" : "−";
	return (
		<span
			dir="ltr"
			className={`flex flex-col ${align === "end" ? "items-end" : "items-start"} leading-tight`}
		>
			<span className={`whitespace-nowrap font-semibold ${income ? "text-success" : ""}`}>
				<span className="sr-only">{income ? "درآمد" : "هزینه"} </span>
				{sign}
				{formatMoney(
					foreign ? row.original_amount : row.converted_amount,
					foreign ? row.original_currency : book.currency,
				)}
			</span>
			{foreign ? (
				<span className="whitespace-nowrap text-xs font-normal text-muted">
					≈ {formatMoney(row.converted_amount, book.currency)}
				</span>
			) : null}
		</span>
	);
}
