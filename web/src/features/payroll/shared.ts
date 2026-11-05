import type { QueryClient } from "@tanstack/react-query";
import { toast } from "@nyxon/nasim";
import type { BookResponse } from "@/api/generated/model";
import { formatAmount } from "@/shared/format";
import { t } from "@/strings";
import { isPositive } from "./decimal";

/** A refusal from the server arrives as a Persian sentence; say it as it is. */
export function reportError(error: unknown) {
	toast.danger(error instanceof Error ? error.message : t.errors.unknown);
}

/** Payroll moves the wallet and the reports too, so a change anywhere refreshes everything it touches. */
export function refreshPayroll(queryClient: QueryClient, bookId: string) {
	const prefix = `/api/v1/books/${bookId}/`;
	return queryClient.invalidateQueries({
		predicate: ({ queryKey }) => {
			const key = String(queryKey[0]);
			return (
				key.startsWith(prefix) &&
				/^(periods|shares|funds|wallet|reports)/.test(key.slice(prefix.length))
			);
		},
	});
}

export const isPayrollBook = (book: BookResponse) =>
	book.type === "team" || book.type === "organization";

/** A bonus reads «+», with a left-to-right mark so the sign stays beside its digits in a right-to-left line. */
export const signed = (value: string, text: string) => (isPositive(value) ? `‎+${text}` : text);

const label = (map: object, key: string) => (map as Record<string, string>)[key] ?? key;
export const shareBasisLabel = (basis: string) => label(t.payroll.shareBasis, basis);
export const fundKindLabel = (kind: string) => label(t.payroll.fundKind, kind);
export const ruleBasisLabel = (basis: string) => label(t.payroll.ruleBasis, basis);
export const periodStatusLabel = (status: string) => label(t.payroll.status, status);
export const adjustmentKindLabel = (kind: string) => label(t.payroll.adjustments.kinds, kind);

/** A share's value in the words of its basis: ۵۰٪, ۱۵٬۰۰۰٬۰۰۰ تومان, ضریب ۱٫۵. */
export function shareValueText(
	basis: string,
	value: string,
	formatMoney: (value: string) => string,
): string {
	if (basis === "percent") return `${formatAmount(value)}٪`;
	if (basis === "fixed") return formatMoney(value);
	return `${t.payroll.weight} ${formatAmount(value)}`;
}
