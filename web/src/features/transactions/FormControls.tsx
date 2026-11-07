import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useController } from "react-hook-form";
import { tv } from "tailwind-variants";
import {
	BottomSheet,
	Button,
	EmptyState,
	Modal,
	SearchBox,
	SelectField,
	toast,
	useIsNarrow,
} from "@nyxon/nasim";
import {
	getBooksListCategoriesQueryKey,
	useBooksCreateCategory,
	useBooksDeleteCategory,
	useBooksListCategories,
	useBooksRenameCategory,
} from "@/api/generated/books/books";
import type { CategoryResponse } from "@/api/generated/model";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { CheckIcon, ChevronDownIcon, EditIcon, TrashIcon } from "@/shared/icons";
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

/** Income or expense, as two buttons side by side (income first, so on the right in this right-to-left page): the one choice every entry starts with. */
export function FlowSwitch({ name }: { name: string }) {
	const { field } = useController({ name });
	return (
		<fieldset className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
			<legend className="mb-1.5 text-sm font-medium">{t.transactions.kind}</legend>
			<div className="flex rounded-full border border-border bg-surface p-1">
				{(["income", "expense"] as const).map((flow) => (
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

	const queryClient = useQueryClient();
	const rename = useBooksRenameCategory();
	const remove = useBooksDeleteCategory();
	const create = useBooksCreateCategory();
	// A brand-new category made right here, without leaving the form.
	const [adding, setAdding] = useState(false);
	const [addName, setAddName] = useState("");
	// The row being renamed in place, and what is typed for it.
	const [editing, setEditing] = useState<CategoryResponse | null>(null);
	const [newName, setNewName] = useState("");

	const saveRename = async () => {
		const name = newName.trim();
		if (!editing || !name) return;
		if (name === editing.name) {
			setEditing(null);
			return;
		}
		try {
			await rename.mutateAsync({ bookId, categoryId: editing.id, data: { name } });
			// Transactions, budgets and rules carry the name too, so they are all read again; and if the
			// renamed one is the one chosen here, the field follows it.
			await Promise.all([
				queryClient.invalidateQueries({ queryKey: getBooksListCategoriesQueryKey(bookId) }),
				refreshMoney(queryClient, bookId),
			]);
			if (value === editing.name) field.onChange(name);
			toast.success(t.categories.renamed);
			setEditing(null);
		} catch (error) {
			reportFailure(error);
		}
	};

	const deleteCategory = async (category: CategoryResponse) => {
		try {
			await remove.mutateAsync({ bookId, categoryId: category.id });
			await queryClient.invalidateQueries({ queryKey: getBooksListCategoriesQueryKey(bookId) });
			if (value === category.name) field.onChange("");
			toast.success(t.categories.deleted);
		} catch (error) {
			// A category that has transactions is refused with the reason; it is shown, not hidden.
			reportFailure(error);
		}
	};

	const addCategory = async () => {
		const fresh = addName.trim();
		if (!fresh) return;
		try {
			await create.mutateAsync({ bookId, data: { name: fresh, flow } });
			await queryClient.invalidateQueries({ queryKey: getBooksListCategoriesQueryKey(bookId) });
			toast.success(t.categories.created);
			setAdding(false);
			setAddName("");
			choose(fresh);
		} catch (error) {
			reportFailure(error);
		}
	};

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
						{editing?.id === category.id ? (
							<div className="flex items-center gap-2 rounded-xl bg-surface-secondary p-1.5">
								<input
									// The box was just asked for, so it takes focus as it appears.
									ref={(element) => element?.focus()}
									className="min-h-10 min-w-0 flex-1 rounded-field border border-border bg-field px-3 text-sm"
									value={newName}
									aria-label={t.categories.renameTitle}
									onChange={(event) => setNewName(event.target.value)}
									onKeyDown={(event) => {
										if (event.key === "Enter") void saveRename();
										if (event.key === "Escape") setEditing(null);
									}}
								/>
								<Button size="sm" isPending={rename.isPending} onPress={() => void saveRename()}>
									{t.common.save}
								</Button>
								<Button size="sm" variant="ghost" onPress={() => setEditing(null)}>
									{t.common.cancel}
								</Button>
							</div>
						) : (
							<div className="flex items-center gap-1">
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
								<Button
									isIconOnly
									size="sm"
									variant="ghost"
									aria-label={`${t.categories.rename}: ${category.name}`}
									onPress={() => {
										setEditing(category);
										setNewName(category.name);
									}}
								>
									<EditIcon aria-hidden />
								</Button>
								<Button
									isIconOnly
									size="sm"
									variant="ghost"
									aria-label={`${t.common.delete}: ${category.name}`}
									onPress={() => void deleteCategory(category)}
								>
									<TrashIcon aria-hidden />
								</Button>
							</div>
						)}
					</li>
				))}
				{!typed && categories.length === 0 ? (
					<li>
						<EmptyState title={t.txFilter.categoryNone} description={t.txFilter.categoryNoneHint} />
					</li>
				) : null}
			</ul>
			{adding ? (
				<div className="flex items-center gap-2 rounded-xl bg-surface-secondary p-1.5">
					<input
						// Asked for just now, so it takes focus as it appears.
						ref={(element) => element?.focus()}
						className="min-h-10 min-w-0 flex-1 rounded-field border border-border bg-field px-3 text-sm"
						value={addName}
						placeholder={t.txFilter.categoryNewName}
						aria-label={t.txFilter.categoryNewName}
						onChange={(event) => setAddName(event.target.value)}
						onKeyDown={(event) => {
							if (event.key === "Enter") void addCategory();
							if (event.key === "Escape") setAdding(false);
						}}
					/>
					<Button size="sm" isPending={create.isPending} onPress={() => void addCategory()}>
						{t.common.save}
					</Button>
					<Button size="sm" variant="ghost" onPress={() => setAdding(false)}>
						{t.common.cancel}
					</Button>
				</div>
			) : (
				<Button
					variant="secondary"
					onPress={() => {
						setAddName(typed);
						setAdding(true);
					}}
				>
					+ {t.txFilter.categoryNew}
				</Button>
			)}
			<Link to="/books" className="text-sm text-accent" onClick={() => setOpen(false)}>
				{t.txFilter.manageCategories}
			</Link>
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

/** Which book an entry belongs to: only asked when there is a choice. */
export function BookField({
	name,
	books,
	label,
}: {
	name: string;
	books: readonly { id: string; name: string }[];
	label: string;
}) {
	if (books.length < 2) return null;
	return (
		<SelectField
			name={name}
			label={label}
			options={books.map((book) => ({ value: book.id, label: book.name }))}
		/>
	);
}
