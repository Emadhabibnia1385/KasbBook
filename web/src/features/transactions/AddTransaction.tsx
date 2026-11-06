import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { FormRoot, Modal, SubmitButton, TextField, toast } from "@nyxon/nasim";
import { booksAddAttachment, useBooksRecordTransaction } from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { lastBook, rememberBook } from "@/features/books/lastBook";
import { useActiveBook } from "@/features/books/useActiveBook";
import { pickedDay, toPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { toAscii } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { AttachmentsField } from "./AttachmentsField";
import { BookField, CategoryField, FlowSwitch } from "./FormControls";
import { todayIso } from "./filters";
import { MoneyFields } from "./MoneyFields";
import { amountRule } from "./rules";

const schema = z.object({
	book_id: z.string().min(1),
	flow: z.enum(["income", "expense"]),
	amount: amountRule,
	category: z.string().trim().min(1, { error: t.transactions.needCategory }).max(80),
	description: z.string().max(300),
	// The money it was paid in; the book's own currency unless chosen otherwise. A rate is only
	// asked for, and checked, when it is another one.
	currency: z.string(),
	rate: z.string().transform(toAscii),
	// Today unless changed: most entries are made the day they happen.
	occurred_on: z.string().min(1, { error: t.days.needDate }),
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
	const record = useBooksRecordTransaction();
	const first = books.find((b) => b.id === initial) ?? books[0];
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			book_id: first?.id ?? "",
			flow: "expense",
			amount: "",
			category: "",
			description: "",
			currency: first?.currency ?? "IRT",
			rate: "",
			occurred_on: toPicker(todayIso()),
		},
	});
	const flow = useWatch({ control: form.control, name: "flow" });
	const bookId = useWatch({ control: form.control, name: "book_id" });
	const book = books.find((b) => b.id === bookId) ?? first;
	// Files chosen before the transaction exists wait here and are sent once it does.
	const [files, setFiles] = useState<File[]>([]);

	// Another book has its own categories and its own unit: what was picked for the last one is not carried over.
	const seen = useRef(book?.id);
	useEffect(() => {
		if (!book || book.id === seen.current) return;
		seen.current = book.id;
		form.setValue("category", "");
		form.setValue("currency", book.currency);
		form.setValue("rate", "");
	}, [book, form]);

	if (!book) return null;
	return (
		<FormRoot
			form={form}
			className="grid gap-x-8 gap-y-4 md:grid-cols-2"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				const other = values.currency !== book.currency;
				if (other && !(/^\d+(\.\d+)?$/.test(values.rate) && Number(values.rate) > 0)) {
					form.setError("rate", { message: t.fx.needRate });
					return;
				}
				try {
					// Scope follows the book's kind on the server; the panel records what the person typed.
					const made = await record.mutateAsync({
						bookId: book.id,
						data: {
							flow: values.flow,
							scope:
								book.type === "personal" ? "personal" : book.type === "business" ? "work" : "team",
							category: values.category,
							amount: values.amount,
							description: values.description || null,
							occurred_on: pickedDay(values.occurred_on),
							currency: other ? values.currency : null,
							conversion_rate: other ? values.rate : null,
						},
					});
					let unsent = 0;
					for (const file of files) {
						try {
							await booksAddAttachment(book.id, made.id, { file });
						} catch {
							unsent += 1;
						}
					}
					rememberBook(book.id);
					await refreshMoney(queryClient, book.id);
					toast.success(t.transactions.saved);
					// The transaction is saved either way; a file that did not go is said plainly, and can be added by editing.
					if (unsent) toast.danger(t.attach.someUnsent);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<div className="flex flex-col gap-4">
				<BookField name="book_id" books={books} label={t.scope.book} />
				<FlowSwitch name="flow" />
				<MoneyFields key={book.id} book={book} initialCurrency={book.currency} initialRate="" />
				<DayField name="occurred_on" label={t.transactions.date} isRequired />
			</div>
			<div className="flex flex-col gap-4">
				<CategoryField
					key={book.id}
					name="category"
					bookId={book.id}
					flow={flow}
					label={t.transactions.category}
					isRequired
				/>
				<TextField name="description" label={t.transactions.note} />
				<AttachmentsField bookId={book.id} queue={files} onQueue={setFiles} />
			</div>
			<div className="md:col-span-2">
				<SubmitButton>{t.common.save}</SubmitButton>
			</div>
		</FormRoot>
	);
}

function Body({ onDone }: { onDone: () => void }) {
	const { books, book } = useActiveBook();
	// The chosen book; with all of them in view, the one used last. The form's own book menu changes it.
	const remembered = lastBook();
	const initial =
		book?.id ?? (books.some((b) => b.id === remembered) ? remembered : books[0]?.id) ?? null;
	return initial ? <Fields books={books} initial={initial} onDone={onDone} /> : null;
}

/**
 * Recording an entry. It opens straight on the form, with the book as its first field: the chosen
 * book, or the one used last when all of them are in view. The body is only there while the dialog is
 * open, so each opening starts over.
 */
export function AddTransactionDialog({
	isOpen,
	onOpenChange,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
}) {
	return (
		<Modal isOpen={isOpen} onOpenChange={onOpenChange} title={t.transactions.add} size="lg">
			<Body onDone={() => onOpenChange(false)} />
		</Modal>
	);
}
