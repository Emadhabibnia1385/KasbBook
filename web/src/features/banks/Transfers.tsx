import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	FormRoot,
	Modal,
	SectionCard,
	SelectField,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	useBanksCreateTransfer,
	useBanksDeleteTransfer,
	useBanksListForBook,
	useBanksListTransfers,
} from "@/api/generated/banks/banks";
import type { BankTransferResponse, BookResponse } from "@/api/generated/model";
import { Loaded } from "@/features/analytics/Loaded";
import { amountRule } from "@/features/transactions/rules";
import { todayIso } from "@/features/transactions/filters";
import { pickedDay, toPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { DayPair } from "@/shared/DayPair";
import { toAscii } from "@/shared/format";
import { formatMoney } from "@/shared/format";
import { PlusIcon } from "@/shared/icons";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const schema = z
	.object({
		from: z.string().min(1),
		to: z.string().min(1),
		amount: amountRule,
		occurred_on: z.string().min(1, { error: t.days.needDate }),
		note: z.string().transform(toAscii).pipe(z.string().max(500)),
	})
	.refine((values) => values.from !== values.to, { path: ["to"], error: t.banks.transferSame });
type Values = z.input<typeof schema>;

function TransferForm({
	book,
	accounts,
	onDone,
}: {
	book: BookResponse;
	accounts: { id: string; title: string }[];
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const create = useBanksCreateTransfer();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			from: accounts[0]?.id ?? "",
			to: accounts[1]?.id ?? "",
			amount: "",
			occurred_on: toPicker(todayIso()),
			note: "",
		},
	});
	const options = accounts.map((account) => ({ value: account.id, label: account.title }));
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					await create.mutateAsync({
						bookId: book.id,
						data: {
							from_bank_account_id: values.from,
							to_bank_account_id: values.to,
							amount: values.amount,
							occurred_on: pickedDay(values.occurred_on),
							note: values.note.trim() || null,
						},
					});
					await refreshMoney(queryClient, book.id);
					toast.success(t.banks.transferDone);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<SelectField name="from" label={t.banks.transferFrom} options={options} />
			<SelectField name="to" label={t.banks.transferTo} options={options} />
			<TextField name="amount" label={t.banks.transferAmount} inputMode="decimal" isRequired />
			<DayField name="occurred_on" label={t.banks.transferDate} isRequired />
			<TextField name="note" label={t.banks.transferNote} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function Row({
	transfer,
	book,
	onRemove,
}: {
	transfer: BankTransferResponse;
	book: BookResponse;
	onRemove: () => void;
}) {
	return (
		<li className="flex flex-wrap items-center justify-between gap-3 border-b border-separator py-2 last:border-b-0">
			<div className="flex min-w-0 flex-col text-sm">
				<bdi className="truncate font-medium">
					{transfer.from_title} ← {transfer.to_title}
				</bdi>
				<span className="flex items-center gap-2 text-xs text-muted">
					<DayPair iso={transfer.occurred_on} bookId={book.id} inline />
					{transfer.note ? <bdi className="truncate">{transfer.note}</bdi> : null}
				</span>
			</div>
			<div className="flex items-center gap-3">
				<span className="tabular-nums">{formatMoney(transfer.amount, book.currency)}</span>
				<Button size="sm" variant="danger-soft" onPress={onRemove}>
					{t.common.delete}
				</Button>
			</div>
		</li>
	);
}

/** Money moved between this book's own accounts: a list, and the dialog that adds one. */
export function Transfers({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const transfers = useBanksListTransfers(book.id);
	const banks = useBanksListForBook(book.id);
	const remove = useBanksDeleteTransfer();
	const [adding, setAdding] = useState(false);
	const [removing, setRemoving] = useState<BankTransferResponse | null>(null);
	const accounts = (banks.data ?? []).filter((bank) => bank.is_active);
	return (
		<SectionCard
			title={t.banks.transfers}
			description={t.banks.transfersHint}
			actions={
				accounts.length >= 2 ? (
					<Button size="sm" onPress={() => setAdding(true)}>
						<PlusIcon aria-hidden className="size-4" />
						{t.banks.transferAdd}
					</Button>
				) : undefined
			}
		>
			{accounts.length < 2 ? <p className="text-sm text-muted">{t.banks.transferNeedTwo}</p> : null}
			<Loaded query={transfers}>
				{(rows) =>
					rows.length === 0 ? (
						<p className="text-sm text-muted">{t.banks.transferEmpty}</p>
					) : (
						<ul className="flex flex-col">
							{rows.map((transfer) => (
								<Row
									key={transfer.id}
									transfer={transfer}
									book={book}
									onRemove={() => setRemoving(transfer)}
								/>
							))}
						</ul>
					)
				}
			</Loaded>
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.banks.transferAdd}>
				{adding ? (
					<TransferForm book={book} accounts={accounts} onDone={() => setAdding(false)} />
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.banks.transferRemoveTitle}
				description={t.banks.transferRemoveBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, transferId: removing.id });
						await refreshMoney(queryClient, book.id);
						toast.success(t.banks.transferRemoved);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</SectionCard>
	);
}
