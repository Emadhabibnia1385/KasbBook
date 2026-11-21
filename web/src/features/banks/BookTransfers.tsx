import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	FormRoot,
	Modal,
	RadioGroupField,
	SectionCard,
	SelectField,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	useBanksCreateBookTransfer,
	useBanksDeleteBookTransfer,
	useBanksListBookTransfers,
	useBanksListForBook,
} from "@/api/generated/banks/banks";
import type { BookResponse, BookTransferResponse } from "@/api/generated/model";
import { Loaded } from "@/features/analytics/Loaded";
import { todayIso } from "@/features/transactions/filters";
import { amountRule } from "@/features/transactions/rules";
import { pickedDay, toPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { DayPair } from "@/shared/DayPair";
import { formatMoney, toAscii } from "@/shared/format";
import { PlusIcon } from "@/shared/icons";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const schema = z.object({
	direction: z.enum(["out", "in"]),
	mine: z.string().min(1),
	other_book: z.string().min(1),
	other: z.string().min(1),
	amount: amountRule,
	occurred_on: z.string().min(1, { error: t.days.needDate }),
	note: z.string().transform(toAscii).pipe(z.string().max(500)),
});
type Values = z.input<typeof schema>;

function Form({
	book,
	others,
	onDone,
}: {
	book: BookResponse;
	/** The other books of the same unit: money cannot move between two currencies. */
	others: BookResponse[];
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const create = useBanksCreateBookTransfer();
	const mine = (useBanksListForBook(book.id).data ?? []).filter((bank) => bank.is_active);
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			direction: "out",
			mine: "",
			other_book: others[0]?.id ?? "",
			other: "",
			amount: "",
			occurred_on: toPicker(todayIso()),
			note: "",
		},
	});
	const otherBook = useWatch({ control: form.control, name: "other_book" });
	const theirs = (useBanksListForBook(otherBook || book.id).data ?? []).filter(
		(bank) => bank.is_active,
	);
	// Each side starts on its book's default, and follows the book chosen on the other end.
	useEffect(() => {
		const standing = mine.find((bank) => bank.is_default) ?? mine[0];
		if (standing && !form.getValues("mine")) form.setValue("mine", standing.id);
	}, [mine, form]);
	useEffect(() => {
		const standing = theirs.find((bank) => bank.is_default) ?? theirs[0];
		if (otherBook && !theirs.some((bank) => bank.id === form.getValues("other")))
			form.setValue("other", standing?.id ?? "");
	}, [theirs, otherBook, form]);
	const toOptions = (list: typeof mine) =>
		list.map((bank) => ({ value: bank.id, label: bank.title }));
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				const out = values.direction === "out";
				try {
					await create.mutateAsync({
						data: {
							from_book_id: out ? book.id : values.other_book,
							to_book_id: out ? values.other_book : book.id,
							from_bank_account_id: out ? values.mine : values.other,
							to_bank_account_id: out ? values.other : values.mine,
							amount: values.amount,
							occurred_on: pickedDay(values.occurred_on),
							note: values.note.trim() || null,
						},
					});
					await Promise.all([
						refreshMoney(queryClient, book.id),
						refreshMoney(queryClient, values.other_book),
					]);
					toast.success(t.banks.bookTransferDone);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<RadioGroupField
				name="direction"
				label={t.banks.bookTransferDirection}
				options={[
					{ value: "out", label: t.banks.bookTransferOut },
					{ value: "in", label: t.banks.bookTransferIn },
				]}
			/>
			<SelectField name="mine" label={t.banks.bookTransferMine} options={toOptions(mine)} />
			<SelectField
				name="other_book"
				label={t.banks.bookTransferOtherBook}
				options={others.map((other) => ({ value: other.id, label: other.name }))}
			/>
			<SelectField name="other" label={t.banks.bookTransferOther} options={toOptions(theirs)} />
			<TextField name="amount" label={t.banks.transferAmount} inputMode="decimal" isRequired />
			<DayField name="occurred_on" label={t.banks.transferDate} isRequired />
			<TextField name="note" label={t.banks.transferNote} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

/** Money moved to or from another of your books: this book's side of each, and the dialog that adds one. */
export function BookTransfers({ book, books }: { book: BookResponse; books: BookResponse[] }) {
	const queryClient = useQueryClient();
	const legs = useBanksListBookTransfers(book.id);
	const accounts = (useBanksListForBook(book.id).data ?? []).filter((bank) => bank.is_active);
	const remove = useBanksDeleteBookTransfer();
	const [adding, setAdding] = useState(false);
	const [removing, setRemoving] = useState<BookTransferResponse | null>(null);
	const others = books.filter((other) => other.id !== book.id && other.currency === book.currency);
	// Nothing to show for a person with one book and no past transfer: the section would only be noise.
	if (others.length === 0 && (legs.data ?? []).length === 0) return null;
	return (
		<SectionCard
			title={t.banks.bookTransfers}
			description={t.banks.bookTransfersHint}
			actions={
				others.length > 0 && accounts.length > 0 ? (
					<Button size="sm" onPress={() => setAdding(true)}>
						<PlusIcon aria-hidden className="size-4" />
						{t.banks.bookTransferAdd}
					</Button>
				) : undefined
			}
		>
			<Loaded query={legs}>
				{(rows) =>
					rows.length === 0 ? (
						<p className="text-sm text-muted">{t.banks.bookTransferEmpty}</p>
					) : (
						<ul className="flex flex-col">
							{rows.map((leg) => (
								<li
									key={`${leg.pair_id}:${leg.direction}`}
									className="flex flex-wrap items-center justify-between gap-3 border-b border-separator py-2 last:border-b-0"
								>
									<div className="flex min-w-0 flex-col text-sm">
										<bdi className="truncate font-medium">
											{leg.direction === "out" ? t.banks.bookTransferTo : t.banks.bookTransferFrom}{" "}
											{leg.other_book_name ?? t.banks.anotherBook} · {leg.bank_title}
										</bdi>
										<span className="flex items-center gap-2 text-xs text-muted">
											<DayPair iso={leg.occurred_on} bookId={book.id} inline />
											{leg.note ? <bdi className="truncate">{leg.note}</bdi> : null}
										</span>
									</div>
									<div className="flex items-center gap-3">
										<span
											className={
												leg.direction === "in" ? "tabular-nums text-success" : "tabular-nums"
											}
										>
											{leg.direction === "in" ? "+" : "−"}
											{formatMoney(leg.amount, book.currency)}
										</span>
										<Button size="sm" variant="danger-soft" onPress={() => setRemoving(leg)}>
											{t.common.delete}
										</Button>
									</div>
								</li>
							))}
						</ul>
					)
				}
			</Loaded>
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.banks.bookTransferAdd}>
				{adding ? <Form book={book} others={others} onDone={() => setAdding(false)} /> : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.banks.bookTransferRemoveTitle}
				description={t.banks.bookTransferRemoveBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, pairId: removing.pair_id });
						await Promise.all([
							refreshMoney(queryClient, book.id),
							refreshMoney(queryClient, removing.other_book_id),
						]);
						toast.success(t.banks.bookTransferRemoved);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</SectionCard>
	);
}
