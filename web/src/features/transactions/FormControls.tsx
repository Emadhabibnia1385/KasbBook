import { useState } from "react";
import { useController } from "react-hook-form";
import { tv } from "tailwind-variants";
import { BottomSheet, EmptyState, Modal, SearchBox, useIsNarrow } from "@nyxon/nasim";
import { useBooksListCategories } from "@/api/generated/books/books";
import { CheckIcon, ChevronDownIcon } from "@/shared/icons";
import { t } from "@/strings";

const segment = tv({
	base: "min-h-11 flex-1 rounded-full px-4 text-sm font-medium transition-colors",
	variants: {
		on: { true: "text-accent-foreground", false: "text-muted hover:text-foreground" },
		tone: { expense: "", income: "" },
	},
	compoundVariants: [
		{ on: true, tone: "expense", class: "bg-danger" },
		{ on: true, tone: "income", class: "bg-success" },
	],
});

/** Expense or income, as two buttons side by side: the one choice every entry starts with. */
export function FlowSwitch({ name }: { name: string }) {
	const { field } = useController({ name });
	return (
		<fieldset className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
			<legend className="mb-1.5 text-sm font-medium">{t.transactions.kind}</legend>
			<div className="flex rounded-full border border-border bg-surface p-1">
				{(["expense", "income"] as const).map((flow) => (
					<button
						key={flow}
						type="button"
						aria-pressed={field.value === flow}
						className={segment({ on: field.value === flow, tone: flow })}
						onClick={() => field.onChange(flow)}
					>
						{flow === "expense" ? t.common.expense : t.common.income}
					</button>
				))}
			</div>
		</fieldset>
	);
}

const option = tv({
	base: "flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-start transition-colors hover:bg-surface-secondary",
	variants: { on: { true: "bg-accent-soft font-semibold text-accent-soft-foreground" } },
});

/**
 * The category as a menu: a field that shows the choice and opens the book's categories for this kind,
 * with a box that filters them and, when what is typed is not one yet, a row that adds it. A category is
 * only a name, so a new one needs nothing more than being picked.
 */
export function CategoryField({
	name,
	bookId,
	flow,
	label,
	isRequired,
}: {
	name: string;
	bookId: string;
	flow: "income" | "expense";
	label: string;
	isRequired?: boolean;
}) {
	const { field, fieldState } = useController({ name });
	const [open, setOpen] = useState(false);
	const [query, setQuery] = useState("");
	const narrow = useIsNarrow("md");
	const categories = useBooksListCategories(bookId, { flow }).data ?? [];
	const value = typeof field.value === "string" ? field.value : "";
	const typed = query.trim();
	const shown = categories.filter((category) => category.name.includes(typed));
	const exists = categories.some((category) => category.name === typed);

	const choose = (picked: string) => {
		field.onChange(picked);
		setOpen(false);
		setQuery("");
	};

	const list = (
		<div className="flex flex-col gap-3">
			<SearchBox
				label={t.txFilter.categoryFind}
				placeholder={t.txFilter.categoryFindHint}
				value={query}
				onChange={setQuery}
			/>
			<ul
				className="flex max-h-[50dvh] flex-col gap-1 overflow-y-auto overscroll-contain"
				aria-label={label}
			>
				{typed && !exists ? (
					<li>
						<button type="button" className={option({})} onClick={() => choose(typed)}>
							<span aria-hidden className="text-accent">
								+
							</span>
							<span className="min-w-0 flex-1 truncate">
								{t.txFilter.categoryAdd} «{typed}»
							</span>
						</button>
					</li>
				) : null}
				{shown.map((category) => (
					<li key={category.id}>
						<button
							type="button"
							aria-pressed={category.name === value}
							className={option({ on: category.name === value })}
							onClick={() => choose(category.name)}
						>
							<span className="min-w-0 flex-1 truncate">{category.name}</span>
							{category.name === value ? (
								<CheckIcon aria-hidden className="size-5 shrink-0" />
							) : null}
						</button>
					</li>
				))}
				{!typed && categories.length === 0 ? (
					<li>
						<EmptyState title={t.txFilter.categoryNone} description={t.txFilter.categoryNoneHint} />
					</li>
				) : null}
			</ul>
		</div>
	);

	return (
		<div className="flex flex-col gap-1.5">
			<span className="text-sm font-medium">
				{label}
				{isRequired ? <span className="text-danger"> *</span> : null}
			</span>
			<button
				type="button"
				aria-haspopup="dialog"
				data-invalid={fieldState.invalid}
				className="flex min-h-11 w-full items-center justify-between gap-2 rounded-field border border-border bg-field px-3 text-start text-sm transition-colors hover:bg-surface-secondary data-[invalid=true]:border-danger"
				onClick={() => setOpen(true)}
				onBlur={field.onBlur}
			>
				<span className={value ? "min-w-0 truncate" : "text-muted"}>
					{value || t.txFilter.categoryChoose}
				</span>
				<ChevronDownIcon aria-hidden className="size-4 shrink-0 text-muted" />
			</button>
			{fieldState.error?.message ? (
				<p className="text-xs text-danger">{fieldState.error.message}</p>
			) : null}
			{narrow ? (
				<BottomSheet isOpen={open} onOpenChange={setOpen} title={label}>
					{list}
				</BottomSheet>
			) : (
				<Modal isOpen={open} onOpenChange={setOpen} title={label} size="xs">
					{list}
				</Modal>
			)}
		</div>
	);
}
