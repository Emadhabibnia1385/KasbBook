import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { FormRoot, Modal, SubmitButton, TextField, toast } from "@nyxon/nasim";
import {
	getBooksListCategoriesQueryKey,
	useBooksCreateCategory,
} from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { BookField, FlowSwitch } from "@/features/transactions/FormControls";
import { BookIcon } from "@/shared/icons";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const schema = z.object({
	book_id: z.string().min(1),
	flow: z.enum(["income", "expense"]),
	name: z.string().trim().min(1, { error: t.categories.needName }).max(80),
});
type Values = z.input<typeof schema>;

function Fields({
	books,
	initial,
	onDone,
}: {
	books: BookResponse[];
	initial: string;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const create = useBooksCreateCategory();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { book_id: initial, flow: "expense", name: "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					await create.mutateAsync({
						bookId: values.book_id,
						data: { name: values.name, flow: values.flow },
					});
					await queryClient.invalidateQueries({
						queryKey: getBooksListCategoriesQueryKey(values.book_id),
					});
					toast.success(t.quick.categorySaved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<BookField name="book_id" books={books} label={t.scope.book} />
			<FlowSwitch name="flow" />
			<TextField name="name" label={t.quick.categoryName} isRequired />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function Body({ onDone }: { onDone: () => void }) {
	const { books, book } = useActiveBook();
	const [picked, setPicked] = useState<string | null>(null);
	const initial = picked ?? book?.id ?? null;
	if (initial) return <Fields books={books} initial={initial} onDone={onDone} />;
	return (
		<div className="flex flex-col gap-3">
			<p className="text-sm text-muted">{t.quick.categoryBookTitle}</p>
			<ul className="flex flex-col gap-2">
				{books.map((item) => (
					<li key={item.id}>
						<button
							type="button"
							className="flex min-h-14 w-full items-center gap-3 rounded-xl border border-border bg-surface px-4 text-start transition-colors hover:bg-surface-secondary"
							onClick={() => setPicked(item.id)}
						>
							<BookIcon aria-hidden className="size-5 shrink-0 text-muted" />
							<span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
						</button>
					</li>
				))}
			</ul>
		</div>
	);
}

/** A category from anywhere: asks which book first unless one is in view. */
export function AddCategoryDialog({
	isOpen,
	onOpenChange,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
}) {
	return (
		<Modal isOpen={isOpen} onOpenChange={onOpenChange} title={t.quick.addCategory} size="sm">
			<Body onDone={() => onOpenChange(false)} />
		</Modal>
	);
}
