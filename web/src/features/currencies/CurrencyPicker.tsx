import { useMemo, useState } from "react";
import { tv } from "tailwind-variants";
import {
	BottomSheet,
	EmptyState,
	ErrorState,
	FilterChips,
	Modal,
	PageSkeleton,
	SearchBox,
	useMediaQuery,
} from "@nyxon/nasim";
import type { CatalogCurrencyResponse } from "@/api/generated/model";
import { CheckIcon } from "@/shared/icons";
import { toAscii } from "@/shared/format";
import { t } from "@/strings";
import { useCatalog } from "./useCatalog";

const row = tv({
	base: "flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-start transition-colors hover:bg-surface-secondary disabled:opacity-50",
	variants: { active: { true: "bg-accent-soft text-accent-soft-foreground" } },
});

type Kind = "all" | "crypto" | "fiat";

// Persian and Latin letters, any case, any digits: «دلار», «usd», «۱» all find what they mean.
const normal = (text: string) =>
	toAscii(text).toLowerCase().replace(/[يى]/g, "ی").replace(/ك/g, "ک");

function matches(currency: CatalogCurrencyResponse, query: string): boolean {
	if (!query) return true;
	const haystack = normal(
		`${currency.name} ${currency.code} ${currency.symbol} ${currency.region}`,
	);
	return query.split(/\s+/).every((word) => haystack.includes(word));
}

/**
 * Every currency the app knows, to choose one from: a sheet on a phone, a dialog on a desktop.
 * `disabled` lists codes that cannot be picked here, each with the reason it is shown beside it.
 */
export function CurrencyPicker({
	isOpen,
	onOpenChange,
	title,
	current,
	disabled = {},
	onPick,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	title: string;
	current?: string | undefined;
	disabled?: Record<string, string>;
	onPick: (code: string) => void;
}) {
	const wide = useMediaQuery("(min-width: 768px)");
	const catalog = useCatalog();
	const [query, setQuery] = useState("");
	const [kind, setKind] = useState<Kind>("all");

	const rows = useMemo(() => {
		const all = catalog.data ?? [];
		const needle = normal(query.trim());
		const picked = all.filter((c) => (kind === "all" || c.kind === kind) && matches(c, needle));
		// Without a search the common ones come first; a search is already narrow.
		return needle
			? picked
			: [...picked.filter((c) => c.popular), ...picked.filter((c) => !c.popular)];
	}, [catalog.data, query, kind]);

	const body = (
		<div className="flex flex-col gap-3">
			<SearchBox
				label={t.currencies.search}
				placeholder={t.currencies.searchHint}
				value={query}
				onChange={setQuery}
			/>
			<FilterChips
				label={t.currencies.kind}
				value={kind}
				onChange={(value) => setKind(value as Kind)}
				options={[
					{ value: "all", label: t.common.all },
					{ value: "crypto", label: t.currencies.crypto },
					{ value: "fiat", label: t.currencies.fiat },
				]}
			/>
			{catalog.isLoading ? (
				<PageSkeleton header={false} rows={5} />
			) : catalog.isError ? (
				<ErrorState onRetry={() => void catalog.refetch()} />
			) : rows.length === 0 ? (
				<EmptyState title={t.currencies.none} />
			) : (
				<ul
					className="flex max-h-[55dvh] flex-col gap-1 overflow-y-auto overscroll-contain"
					aria-label={title}
				>
					{rows.map((currency) => {
						const why = disabled[currency.code];
						return (
							<li key={currency.code}>
								<button
									type="button"
									disabled={Boolean(why)}
									aria-current={currency.code === current}
									className={row({ active: currency.code === current })}
									onClick={() => {
										onPick(currency.code);
										onOpenChange(false);
									}}
								>
									<span dir="ltr" className="w-12 shrink-0 text-sm font-semibold text-muted">
										{currency.code}
									</span>
									<span className="flex min-w-0 flex-1 flex-col">
										<span className="truncate font-medium">{currency.name}</span>
										<span className="truncate text-xs text-muted">{why ?? currency.region}</span>
									</span>
									{currency.code === current ? (
										<CheckIcon aria-hidden className="size-5 shrink-0" />
									) : null}
								</button>
							</li>
						);
					})}
				</ul>
			)}
		</div>
	);

	return wide ? (
		<Modal isOpen={isOpen} onOpenChange={onOpenChange} title={title} size="sm">
			{body}
		</Modal>
	) : (
		<BottomSheet isOpen={isOpen} onOpenChange={onOpenChange} title={title}>
			{body}
		</BottomSheet>
	);
}
