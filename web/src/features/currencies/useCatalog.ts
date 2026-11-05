import { useEffect } from "react";
import { useCurrenciesCatalog } from "@/api/generated/currencies/currencies";
import { registerCurrencies } from "@/shared/format";

/** The whole catalog, fetched once per visit: it is static, so it never goes stale within one. */
export function useCatalog() {
	const query = useCurrenciesCatalog({ query: { staleTime: Number.POSITIVE_INFINITY } });
	useEffect(() => {
		if (query.data) registerCurrencies(query.data);
	}, [query.data]);
	return query;
}
