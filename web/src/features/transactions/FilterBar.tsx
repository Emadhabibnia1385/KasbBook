import { useQueries } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { tv } from "tailwind-variants";
import { BottomSheet, Button, Modal, SearchBox, useIsNarrow } from "@nyxon/nasim";
import {
	booksListCategories,
	booksListCurrencies,
	getBooksListCategoriesQueryKey,
	getBooksListCurrenciesQueryKey,
} from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { ChevronDownIcon } from "@/shared/icons";
import { DayField } from "@/shared/DayField";
import { currencyName, formatAmount } from "@/shared/format";
import { t } from "@/strings";
import {
	activeCount,
	type Filters,
	type FlowKey,
	NO_FILTERS,
	type RangeKey,
	type SortKey,
	toggle,
} from "./filters";

const row = tv({
	base: "flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-start transition-colors hover:bg-surface-secondary",
	variants: { on: { true: "bg-accent-soft font-semibold text-accent-soft-foreground" } },
});

// Every filter is the same shape: the name small above, what it is set to below, a chevron at the end.
// In a grid they line up in columns instead of wrapping into rows of different lengths.
const trigger = tv({
	base: "flex min-h-14 w-full min-w-0 items-center gap-2 rounded-2xl border px-3 py-1.5 text-start transition-colors",
	variants: {
		on: {
			true: "border-accent bg-accent-soft font-semibold text-accent-soft-foreground",
			false: "border-border bg-surface text-foreground hover:bg-surface-secondary",
		},
	},
});

const RANGES: { value: RangeKey; label: string }[] = [
	{ value: "all", label: t.txFilter.all },
	{ value: "today", label: t.txFilter.today },
	{ value: "yesterday", label: t.txFilter.yesterday },
	{ value: "d3", label: t.txFilter.d3 },
	{ value: "d7", label: t.txFilter.d7 },
	{ value: "d30", label: t.txFilter.d30 },
	{ value: "d90", label: t.txFilter.d90 },
	{ value: "year", label: t.txFilter.year },
	{ value: "custom", label: t.txFilter.custom },
];
const SORTS: { value: SortKey; label: string }[] = [
	{ value: "newest", label: t.txFilter.sortNewest },
	{ value: "oldest", label: t.txFilter.sortOldest },
	{ value: "amount_desc", label: t.txFilter.sortLargest },
	{ value: "amount_asc", label: t.txFilter.sortSmallest },
	{ value: "category", label: t.txFilter.sortCategory },
];
const FLOW_LABEL: Record<FlowKey, string> = {
	expense: t.txFilter.onlyExpense,
	income: t.txFilter.onlyIncome,
};

/** The search box types every keystroke; the list should ask once the person pauses. */
function useDebounced(value: string, ms = 350) {
	const [debounced, setDebounced] = useState(value);
	useEffect(() => {
		const id = setTimeout(() => setDebounced(value), ms);
		return () => clearTimeout(id);
	}, [value, ms]);
	return debounced;
}

// One filter, closed into a button that says what it is set to; the choices open in a sheet on a phone
// and a dialog on a desktop. Four rows of chips were three screens of controls before any transaction.
function Picker({
	label,
	summary,
	active,
	title,
	children,
}: {
	label: string;
	summary: string;
	active: boolean;
	title: string;
	children: React.ReactNode;
}) {
	const [open, setOpen] = useState(false);
	const narrow = useIsNarrow("md");
	return (
		<>
			<button
				type="button"
				className={trigger({ on: active })}
				aria-haspopup="dialog"
				onClick={() => setOpen(true)}
			>
				<span className="flex min-w-0 flex-1 flex-col leading-tight">
					<span className="truncate text-xs text-muted">{label}</span>
					<span className="truncate text-sm">{summary}</span>
				</span>
				<ChevronDownIcon aria-hidden className="size-4 shrink-0 text-muted" />
			</button>
			{narrow ? (
				<BottomSheet isOpen={open} onOpenChange={setOpen} title={title}>
					{children}
				</BottomSheet>
			) : (
				<Modal isOpen={open} onOpenChange={setOpen} title={title} size="xs">
					{children}
				</Modal>
			)}
		</>
	);
}

export function FilterBar({
	books,
	value,
	onChange,
	leading,
}: {
	/** The books the list is about: one, or all of them. */
	books: BookResponse[];
	value: Filters;
	onChange: (next: Filters) => void;
	leading?: React.ReactNode;
}) {
	// Across several books the same name is one choice, and a currency is offered if any of them holds it.
	const categoryLists = useQueries({
		queries: books.map((book) => ({
			queryKey: getBooksListCategoriesQueryKey(book.id),
			queryFn: () => booksListCategories(book.id),
		})),
	});
	const seen = new Set<string>();
	const categories = categoryLists
		.flatMap((query) => query.data ?? [])
		.filter((category) => {
			const key = `${category.flow ?? ""}:${category.name}`;
			if (seen.has(key)) return false;
			seen.add(key);
			return true;
		});
	// The money a payment can have been in: each book's own, then whatever it holds.
	const currencyLists = useQueries({
		queries: books.map((book) => ({
			queryKey: getBooksListCurrenciesQueryKey(book.id),
			queryFn: () => booksListCurrencies(book.id),
		})),
	});
	const currencyOptions = [
		...new Set(
			currencyLists.flatMap((query) =>
				(query.data ?? []).filter((option) => option.enabled).map((option) => option.code),
			),
		),
	];
	// What is typed is shown at once; what the list asks for follows after a pause.
	const [typed, setTyped] = useState(value.q);
	const settled = useDebounced(typed);
	useEffect(() => {
		if (settled !== value.q) onChange({ ...value, q: settled });
	}, [settled]); // oxlint-disable-line react/exhaustive-deps

	const count = activeCount(value);
	// Only the categories that fit the chosen kinds: asking for «فروش» among expenses finds nothing.
	const offered = categories.filter(
		(category) =>
			value.flows.length === 0 ||
			category.flow === null ||
			value.flows.includes(category.flow as FlowKey),
	);
	// Range, kind and sort are always there; categories and a second currency only when there is a choice.
	const cells = 3 + (offered.length ? 1 : 0) + (currencyOptions.length > 1 ? 1 : 0);
	const rangeLabel = RANGES.find((item) => item.value === value.range)?.label ?? t.txFilter.all;
	const wrongRange =
		value.range === "custom" && value.since && value.until && value.since > value.until;
	const clearAll = () => {
		setTyped("");
		// The order is the person's way of reading, not a narrowing: it survives clearing.
		onChange({ ...NO_FILTERS, sort: value.sort });
	};

	return (
		<div className="flex flex-col gap-3">
			<div className="flex items-center gap-3">
				{/* The main action sits first in the row, at the reading start, beside what is searched. */}
				{leading}
				<div className="min-w-0 flex-1">
					<SearchBox
						label={t.txFilter.search}
						placeholder={t.txFilter.searchHint}
						value={typed}
						onChange={setTyped}
					/>
				</div>
			</div>
			<div
				className={
					cells >= 5
						? "grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5"
						: "grid grid-cols-2 gap-2 md:grid-cols-4"
				}
			>
				<Picker
					label={t.txFilter.range}
					summary={rangeLabel}
					active={value.range !== "all"}
					title={t.txFilter.range}
				>
					<div className="flex flex-col gap-1">
						{RANGES.map((item) => (
							<button
								key={item.value}
								type="button"
								aria-pressed={value.range === item.value}
								className={row({ on: value.range === item.value })}
								onClick={() => onChange({ ...value, range: item.value })}
							>
								{item.label}
							</button>
						))}
						{value.range === "custom" ? (
							<fieldset className="mt-2 grid gap-3">
								<legend className="sr-only">{t.txFilter.custom}</legend>
								<DayField
									label={t.txExtra.since}
									value={value.since}
									onChange={(since) => onChange({ ...value, since })}
								/>
								<DayField
									label={t.txExtra.until}
									value={value.until}
									errorMessage={wrongRange ? t.txExtra.badRange : undefined}
									onChange={(until) => onChange({ ...value, until })}
								/>
							</fieldset>
						) : null}
					</div>
				</Picker>
				<Picker
					label={t.txFilter.kind}
					summary={
						value.flows.length ? value.flows.map((f) => FLOW_LABEL[f]).join("، ") : t.common.all
					}
					active={value.flows.length > 0}
					title={t.txFilter.kind}
				>
					<div className="flex flex-col gap-1">
						{(["expense", "income"] as FlowKey[]).map((flow) => (
							<button
								key={flow}
								type="button"
								aria-pressed={value.flows.includes(flow)}
								className={row({ on: value.flows.includes(flow) })}
								onClick={() => onChange({ ...value, flows: toggle(value.flows, flow) })}
							>
								{FLOW_LABEL[flow]}
							</button>
						))}
					</div>
				</Picker>
				{offered.length ? (
					<Picker
						label={t.txFilter.categories}
						summary={
							value.categories.length
								? `${formatAmount(value.categories.length)} ${t.txFilter.picked}`
								: t.common.all
						}
						active={value.categories.length > 0}
						title={t.txFilter.categories}
					>
						<div className="flex max-h-[55dvh] flex-col gap-1 overflow-y-auto overscroll-contain">
							{offered.map((category) => (
								<button
									key={category.id}
									type="button"
									aria-pressed={value.categories.includes(category.name)}
									className={row({ on: value.categories.includes(category.name) })}
									onClick={() =>
										onChange({ ...value, categories: toggle(value.categories, category.name) })
									}
								>
									{category.name}
								</button>
							))}
						</div>
					</Picker>
				) : null}
				{currencyOptions.length > 1 ? (
					<Picker
						label={t.txFilter.currency}
						summary={
							value.currencies.length
								? value.currencies.map((code) => currencyName(code)).join("، ")
								: t.common.all
						}
						active={value.currencies.length > 0}
						title={t.txFilter.currency}
					>
						<div className="flex flex-col gap-1">
							{currencyOptions.map((code) => (
								<button
									key={code}
									type="button"
									aria-pressed={value.currencies.includes(code)}
									className={row({ on: value.currencies.includes(code) })}
									onClick={() => onChange({ ...value, currencies: toggle(value.currencies, code) })}
								>
									{currencyName(code)}
									<span dir="ltr" className="text-xs text-muted">
										{code}
									</span>
								</button>
							))}
						</div>
					</Picker>
				) : null}
				<Picker
					label={t.txFilter.sort}
					summary={SORTS.find((item) => item.value === value.sort)?.label ?? ""}
					active={value.sort !== "newest"}
					title={t.txFilter.sort}
				>
					<div className="flex flex-col gap-1">
						{SORTS.map((item) => (
							<button
								key={item.value}
								type="button"
								aria-pressed={value.sort === item.value}
								className={row({ on: value.sort === item.value })}
								onClick={() => onChange({ ...value, sort: item.value })}
							>
								{item.label}
							</button>
						))}
					</div>
				</Picker>
				{count > 0 ? (
					<div className="col-span-full flex justify-end">
						<Button size="sm" variant="ghost" onPress={clearAll}>
							{t.txFilter.clear}
						</Button>
					</div>
				) : null}
			</div>
		</div>
	);
}
