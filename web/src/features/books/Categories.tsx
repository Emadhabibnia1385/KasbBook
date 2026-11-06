import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	EmptyState,
	FormRoot,
	Modal,
	PageSkeleton,
	SectionCard,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getBooksListCategoriesQueryKey,
	useBooksCreateCategory,
	useBooksDeleteCategory,
	useBooksListCategories,
	useBooksRenameCategory,
} from "@/api/generated/books/books";
import type { BookResponse, CategoryResponse } from "@/api/generated/model";
import { EditIcon, TrashIcon } from "@/shared/icons";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const nameRule = z.string().trim().min(1, { error: t.categories.needName }).max(80);

const createSchema = z.object({ name: nameRule });
type CreateValues = z.input<typeof createSchema>;
const renameSchema = z.object({ name: nameRule });
type RenameValues = z.input<typeof renameSchema>;

// The kind is chosen by which button opened the form, so it is not asked again.
function CreateForm({
	book,
	flow,
	onDone,
}: {
	book: BookResponse;
	flow: "income" | "expense";
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const create = useBooksCreateCategory();
	const form = useForm<CreateValues>({
		resolver: zodResolver(createSchema),
		defaultValues: { name: "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					await create.mutateAsync({
						bookId: book.id,
						data: { name: values.name.trim(), flow },
					});
					await queryClient.invalidateQueries({
						queryKey: getBooksListCategoriesQueryKey(book.id),
					});
					toast.success(t.categories.created);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField name="name" label={t.categories.name} isRequired />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function RenameForm({
	book,
	category,
	onDone,
}: {
	book: BookResponse;
	category: CategoryResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const rename = useBooksRenameCategory();
	const form = useForm<RenameValues>({
		resolver: zodResolver(renameSchema),
		defaultValues: { name: category.name },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				const name = values.name.trim();
				if (name === category.name) {
					onDone();
					return;
				}
				try {
					await rename.mutateAsync({ bookId: book.id, categoryId: category.id, data: { name } });
					// Transactions, budgets and rules carry the name too, so they are all read again.
					await Promise.all([
						queryClient.invalidateQueries({ queryKey: getBooksListCategoriesQueryKey(book.id) }),
						refreshMoney(queryClient, book.id),
					]);
					toast.success(t.categories.renamed);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField name="name" label={t.categories.name} isRequired />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function CategoryList({
	categories,
	onRename,
	onRemove,
}: {
	categories: CategoryResponse[];
	onRename: (category: CategoryResponse) => void;
	onRemove: (category: CategoryResponse) => void;
}) {
	return (
		<ul className="flex flex-col gap-2">
			{categories.map((category) => (
				<li
					key={category.id}
					className="flex min-w-0 items-center gap-2 rounded-xl border border-border bg-surface py-1.5 ps-3 pe-1.5"
				>
					<span className="min-w-0 flex-1 truncate font-medium">{category.name}</span>
					<Button
						isIconOnly
						size="sm"
						variant="ghost"
						aria-label={`${t.categories.rename}: ${category.name}`}
						onPress={() => onRename(category)}
					>
						<EditIcon aria-hidden />
					</Button>
					<Button
						isIconOnly
						size="sm"
						variant="ghost"
						aria-label={`${t.common.delete}: ${category.name}`}
						onPress={() => onRemove(category)}
					>
						<TrashIcon aria-hidden />
					</Button>
				</li>
			))}
		</ul>
	);
}

/** The active book's categories, expense ones and income ones apart: what the transaction form suggests, kept tidy here. */
export function Categories({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = useBooksListCategories(book.id);
	const remove = useBooksDeleteCategory();
	const [adding, setAdding] = useState<"income" | "expense" | null>(null);
	const [renaming, setRenaming] = useState<CategoryResponse | null>(null);
	const [removing, setRemoving] = useState<CategoryResponse | null>(null);
	const column = (flow: "income" | "expense") => {
		const mine = data.filter((category) => category.flow === flow);
		const expense = flow === "expense";
		return (
			<section className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border p-4">
				<div className="flex items-start justify-between gap-2">
					<div className="flex min-w-0 flex-col gap-0.5">
						<h3 className="font-semibold">
							{expense ? t.categories.expenseTitle : t.categories.incomeTitle}
						</h3>
						<p className="text-xs text-muted">
							{expense ? t.categories.expenseHint : t.categories.incomeHint}
						</p>
					</div>
					<Button
						size="sm"
						variant={expense ? "primary" : "secondary"}
						onPress={() => setAdding(flow)}
					>
						{expense ? t.categories.addExpense : t.categories.addIncome}
					</Button>
				</div>
				{isLoading ? (
					<PageSkeleton header={false} rows={2} />
				) : mine.length === 0 ? (
					<EmptyState
						title={expense ? t.categories.noExpense : t.categories.noIncome}
						description={t.categories.empty}
					/>
				) : (
					<CategoryList categories={mine} onRename={setRenaming} onRemove={setRemoving} />
				)}
			</section>
		);
	};
	return (
		<SectionCard title={t.manage.categoriesTitle} description={t.manage.categoriesHint}>
			<div className="grid gap-4 md:grid-cols-2">
				{column("expense")}
				{column("income")}
			</div>
			<Modal
				isOpen={adding !== null}
				onOpenChange={(open) => !open && setAdding(null)}
				title={adding === "income" ? t.categories.addIncome : t.categories.addExpense}
				size="sm"
			>
				{adding ? <CreateForm book={book} flow={adding} onDone={() => setAdding(null)} /> : null}
			</Modal>
			<Modal
				isOpen={renaming !== null}
				onOpenChange={(open) => !open && setRenaming(null)}
				title={t.categories.renameTitle}
				size="sm"
			>
				{renaming ? (
					<RenameForm
						key={renaming.id}
						book={book}
						category={renaming}
						onDone={() => setRenaming(null)}
					/>
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.categories.deleteTitle}
				description={t.categories.deleteBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, categoryId: removing.id });
						await queryClient.invalidateQueries({
							queryKey: getBooksListCategoriesQueryKey(book.id),
						});
						toast.success(t.categories.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</SectionCard>
	);
}
