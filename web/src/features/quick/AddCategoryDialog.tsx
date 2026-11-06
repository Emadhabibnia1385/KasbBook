import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { FormRoot, Modal, SubmitButton, TextField, toast } from "@nyxon/nasim";
import {
	getBooksListCategoriesQueryKey,
	useBooksCreateCategory,
} from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { lastBook } from "@/features/books/lastBook";
import { useActiveBook } from "@/features/books/useActiveBook";
import { BookField, FlowSwitch } from "@/features/transactions/FormControls";
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
	const remembered = lastBook();
	const initial =
		book?.id ?? (books.some((b) => b.id === remembered) ? remembered : books[0]?.id) ?? null;
	return initial ? <Fields books={books} initial={initial} onDone={onDone} /> : null;
}

/** A category from anywhere: the book is the form's first field, on the one in view or the one used last. */
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
