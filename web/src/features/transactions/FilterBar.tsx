import { useEffect, useState } from "react";
import { tv } from "tailwind-variants";
import { Button, Collapsible, FilterChips, SearchBox, useIsNarrow } from "@nyxon/nasim";
import { useBooksListCategories } from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { DayField } from "@/shared/DayField";
import { formatAmount } from "@/shared/format";
import { t } from "@/strings";
import {
	activeCount,
	type Filters,
	type FlowKey,
	NO_FILTERS,
	type RangeKey,
	toggle,
} from "./filters";

const chip = tv({
	base: "inline-flex min-h-9 items-center rounded-full border px-3 text-sm transition-colors",
	variants: {
		on: {
			true: "border-accent bg-accent-soft font-semibold text-accent-soft-foreground",
			false: "border-border bg-surface text-muted hover:text-foreground",
		},
	},
});

// A chip that is on or off, for choices that can be combined; the single-choice ones are FilterChips.
function Toggle({
	on,
	onPress,
	children,
}: {
	on: boolean;
	onPress: () => void;
	children: React.ReactNode;
}) {
	return (
		<button type="button" aria-pressed={on} className={chip({ on })} onClick={onPress}>
			{children}
		</button>
	);
}

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

/** The search box types every keystroke; the list should ask once the person pauses. */
function useDebounced(value: string, ms = 350) {
	const [debounced, setDebounced] = useState(value);
	useEffect(() => {
		const id = setTimeout(() => setDebounced(value), ms);
		return () => clearTimeout(id);
	}, [value, ms]);
	return debounced;
}

export function FilterBar({
	book,
	value,
	onChange,
}: {
	book: BookResponse;
	value: Filters;
	onChange: (next: Filters) => void;
}) {
	const narrow = useIsNarrow("md");
	const categories = useBooksListCategories(book.id).data ?? [];
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
	const wrongRange =
		value.range === "custom" && value.since && value.until && value.since > value.until;

	const body = (
		<div className="flex flex-col gap-3">
			<FilterChips
				label={t.txFilter.range}
				value={value.range}
				onChange={(range) => onChange({ ...value, range: range as RangeKey })}
				options={RANGES}
			/>
			{value.range === "custom" ? (
				<fieldset className="grid gap-3 sm:grid-cols-2">
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
			<fieldset className="m-0 flex min-w-0 flex-wrap items-center gap-2 border-0 p-0">
				<legend className="sr-only">{t.txFilter.kind}</legend>
				<Toggle
					on={value.flows.includes("expense")}
					onPress={() => onChange({ ...value, flows: toggle(value.flows, "expense") })}
				>
					{t.txFilter.onlyExpense}
				</Toggle>
				<Toggle
					on={value.flows.includes("income")}
					onPress={() => onChange({ ...value, flows: toggle(value.flows, "income") })}
				>
					{t.txFilter.onlyIncome}
				</Toggle>
			</fieldset>
			{offered.length ? (
				<Collapsible
					title={`${t.txFilter.categories}${value.categories.length ? ` (${formatAmount(value.categories.length)})` : ""}`}
					defaultOpen={value.categories.length > 0}
				>
					<fieldset className="m-0 flex min-w-0 flex-wrap gap-2 border-0 p-0 pt-3">
						<legend className="sr-only">{t.txFilter.categories}</legend>
						{offered.map((category) => (
							<Toggle
								key={category.id}
								on={value.categories.includes(category.name)}
								onPress={() =>
									onChange({ ...value, categories: toggle(value.categories, category.name) })
								}
							>
								{category.name}
							</Toggle>
						))}
					</fieldset>
				</Collapsible>
			) : null}
			{count > 0 ? (
				<Button
					size="sm"
					variant="ghost"
					className="self-start"
					onPress={() => {
						setTyped("");
						onChange(NO_FILTERS);
					}}
				>
					{t.txFilter.clear}
				</Button>
			) : null}
		</div>
	);

	return (
		<div className="flex flex-col gap-3">
			<SearchBox
				label={t.txFilter.search}
				placeholder={t.txFilter.searchHint}
				value={typed}
				onChange={setTyped}
			/>
			{narrow ? (
				<Collapsible
					title={`${t.txFilter.title}${count ? ` (${formatAmount(count)})` : ""}`}
					defaultOpen={count > 0}
				>
					<div className="pt-3">{body}</div>
				</Collapsible>
			) : (
				body
			)}
		</div>
	);
}
