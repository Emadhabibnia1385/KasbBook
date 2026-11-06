import type { QueryClient } from "@tanstack/react-query";
import {
	getCapitalListAssetsQueryKey,
	getCapitalListFundsQueryKey,
	getCapitalOverviewQueryKey,
} from "@/api/generated/capital/capital";
import { getPortfolioPortfolioQueryKey } from "@/api/generated/portfolio/portfolio";
import { getPlanningListLoansQueryKey } from "@/api/generated/planning/planning";
import { refreshMoney } from "@/shared/mutations";

/** What changes when something is bought, sold, paid into or taken back: the lists, the loans and the wallet. */
export async function refresh(queryClient: QueryClient, bookId: string) {
	await Promise.all([
		queryClient.invalidateQueries({ queryKey: getCapitalListAssetsQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getCapitalListFundsQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getCapitalOverviewQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getPlanningListLoansQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getPortfolioPortfolioQueryKey(bookId) }),
		refreshMoney(queryClient, bookId),
	]);
}
