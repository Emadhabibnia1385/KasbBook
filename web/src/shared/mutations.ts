// What every write does afterwards: tell the person why it failed, or refresh what the write changed.
import { toast } from "@nyxon/nasim";
import type { QueryClient } from "@tanstack/react-query";
import {
	getBooksListTransactionsQueryKey,
	getBooksWalletQueryKey,
} from "@/api/generated/books/books";
import { getPlanningListBudgetsQueryKey } from "@/api/generated/planning/planning";
import { t } from "@/strings";

export function reportFailure(error: unknown): void {
	toast.danger(error instanceof Error ? error.message : t.errors.unknown);
}

/**
 * Everything a recorded, edited or removed transaction moves: the list, the reports, the wallet and the
 * budgets (what a budget has spent is computed from transactions).
 */
export async function refreshMoney(queryClient: QueryClient, bookId: string): Promise<void> {
	await Promise.all([
		queryClient.invalidateQueries({ queryKey: getBooksListTransactionsQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getBooksWalletQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getPlanningListBudgetsQueryKey(bookId) }),
		queryClient.invalidateQueries({
			predicate: (query) => {
				const key = String(query.queryKey[0]);
				// Reports and charts of every book, and the list that spans all of them.
				return (
					key.includes("/reports/") || key.includes("/analytics/") || key === "/api/v1/transactions"
				);
			},
		}),
	]);
}
