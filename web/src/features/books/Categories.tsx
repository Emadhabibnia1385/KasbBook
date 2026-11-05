import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	EmptyState,
	FilterChips,
	FormRoot,
	Modal,
	PageSkeleton,
	RadioGroupField,
	SectionCard,
	StatusChip,
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
import { formatAmount } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const nameRule = z.string().trim().min(1, { error: t.categories.needName }).max(80);

const createSchema = z.object({ name: nameRule, flow: z.enum(["income", "expense"]) });
type CreateValues = z.input<typeof createSchema>;
const renameSchema = z.object({ name: nameRule });
type RenameValues = z.input<typeof renameSchema>;

function CreateForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const create = useBooksCreateCategory();
	const form = useForm<CreateValues>({
		resolver: zodResolver(createSchema),
		defaultValues: { name: "", flow: "expense" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					await create.mutateAsync({
						bookId: book.id,
						data: { name: values.name.trim(), flow: values.flow },
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
			<RadioGroupField
				name="flow"
				label={t.categories.flow}
				options={[
					{ value: "expense", label: t.common.expense },
					{ value: "income", label: t.common.income },
				]}
			/>
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

/** The active book's categories: what the transaction form suggests, kept tidy here. */
export function Categories({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = useBooksListCategories(book.id);
	const remove = useBooksDeleteCategory();
	const [adding, setAdding] = useState(false);
	// «همه» is the default: the person sees every category first and narrows only if they want to.
	const [shown, setShown] = useState<"all" | "income" | "expense">("all");
	const [renaming, setRenaming] = useState<CategoryResponse | null>(null);
	const [removing, setRemoving] = useState<CategoryResponse | null>(null);
	const visible = shown === "all" ? data : data.filter((category) => category.flow === shown);
	const count = (flow: "income" | "expense") =>
		data.filter((category) => category.flow === flow).length;
	return (
		<SectionCard
			title={t.categories.title}
			description={t.categories.description}
			actions={
				<Button size="sm" onPress={() => setAdding(true)}>
					{t.categories.add}
				</Button>
			}
		>
			{isLoading ? (
				<PageSkeleton header={false} rows={3} />
			) : data.length === 0 ? (
				<EmptyState title={t.categories.emptyTitle} description={t.categories.empty} />
			) : (
				<div className="flex flex-col gap-3">
					<FilterChips
						label={t.categories.filterLabel}
						value={shown}
						onChange={(value) => setShown(value as typeof shown)}
						options={[
							{ value: "all", label: `${t.common.all} (${formatAmount(data.length)})` },
							{
								value: "expense",
								label: `${t.common.expense} (${formatAmount(count("expense"))})`,
							},
							{ value: "income", label: `${t.common.income} (${formatAmount(count("income"))})` },
						]}
					/>
					{visible.length === 0 ? (
						<p className="text-sm text-muted">{t.categories.noneInFilter}</p>
					) : null}
					<ul className="flex flex-col">
						{visible.map((category) => (
							<li
								key={category.id}
								className="flex flex-wrap items-center justify-between gap-2 border-b border-separator py-2 last:border-b-0"
							>
								<span className="flex min-w-0 items-center gap-2">
									<span className="min-w-0 break-words font-medium">{category.name}</span>
									{category.flow ? (
										<StatusChip
											tone={category.flow === "income" ? "success" : "neutral"}
											label={category.flow === "income" ? t.common.income : t.common.expense}
										/>
									) : null}
								</span>
								<span className="flex gap-1">
									<Button size="sm" variant="ghost" onPress={() => setRenaming(category)}>
										{t.categories.rename}
									</Button>
									<Button size="sm" variant="ghost" onPress={() => setRemoving(category)}>
										{t.common.delete}
									</Button>
								</span>
							</li>
						))}
					</ul>
				</div>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.categories.add} size="sm">
				<CreateForm book={book} onDone={() => setAdding(false)} />
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
