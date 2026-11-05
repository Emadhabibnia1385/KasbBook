import { BottomSheet, Button, KeyValueList, Modal, useIsNarrow } from "@nyxon/nasim";
import { useBooksListAttachments } from "@/api/generated/books/books";
import type { BookResponse, TransactionResponse } from "@/api/generated/model";
import { useQuotes } from "@/features/market/useQuotes";
import { multiply } from "@/features/payroll/decimal";
import { currencyName, formatAmount, formatFullDate, formatMoney } from "@/shared/format";
import { t } from "@/strings";
import { AttachmentItem } from "./AttachmentsField";

function Body({ book, row }: { book: BookResponse; row: TransactionResponse }) {
	const files = useBooksListAttachments(book.id, row.id, {
		query: { enabled: (row.attachment_count ?? 0) > 0 },
	});
	const income = row.flow === "income";
	const foreign = row.original_currency !== book.currency;
	// What it was worth when recorded is on the row; what it is worth now is asked of the market.
	const now = useQuotes([row.original_currency], book.currency, foreign).data?.[0];
	const recordedRate =
		foreign && Number(row.original_amount) > 0
			? Number(row.converted_amount) / Number(row.original_amount)
			: null;
	return (
		<div className="flex flex-col gap-4">
			<KeyValueList
				items={[
					{
						label: t.transactions.amount,
						value: (
							<span dir="ltr" className={income ? "text-success" : undefined}>
								{income ? "+" : "−"}
								{formatMoney(row.converted_amount, book.currency)}
							</span>
						),
					},
					foreign
						? {
								label: t.txExtra.original,
								value: (
									<span dir="ltr">{formatMoney(row.original_amount, row.original_currency)}</span>
								),
							}
						: null,
					recordedRate !== null
						? {
								label: t.fx.recorded,
								value: (
									<span dir="ltr">
										1 {currencyName(row.original_currency)} ={" "}
										{formatAmount(recordedRate.toFixed(4), 4)} {currencyName(book.currency)}
									</span>
								),
							}
						: null,
					foreign && now
						? {
								label: t.fx.today,
								value: (
									<span dir="ltr">
										{formatMoney(multiply(row.original_amount, now.value), book.currency)}
										{now.exact ? "" : ` (${t.fx.estimateShort})`}
									</span>
								),
							}
						: null,
					{ label: t.transactions.kind, value: income ? t.common.income : t.common.expense },
					{ label: t.transactions.date, value: formatFullDate(row.occurred_on) },
					// The whole note, wrapped: the list only shows its first line.
					row.description
						? {
								label: t.transactions.note,
								value: <span className="whitespace-pre-wrap break-words">{row.description}</span>,
							}
						: null,
				]}
			/>
			{(row.attachment_count ?? 0) > 0 ? (
				<div className="flex flex-col gap-2">
					<span className="text-sm font-medium">{t.attach.title}</span>
					<ul className="flex flex-col gap-2">
						{(files.data ?? []).map((file) => (
							<AttachmentItem key={file.id} bookId={book.id} transactionId={row.id} file={file} />
						))}
					</ul>
				</div>
			) : null}
		</div>
	);
}

/** Everything about one transaction, with its full note and files, and the two things to do with it. */
export function TransactionDetail({
	book,
	row,
	onClose,
	onEdit,
	onRemove,
}: {
	book: BookResponse;
	row: TransactionResponse | null;
	onClose: () => void;
	onEdit: (row: TransactionResponse) => void;
	onRemove: (row: TransactionResponse) => void;
}) {
	const narrow = useIsNarrow("md");
	const footer = row ? (
		<>
			<Button
				variant="danger-soft"
				onPress={() => {
					onRemove(row);
					onClose();
				}}
			>
				{t.common.delete}
			</Button>
			<Button
				onPress={() => {
					onEdit(row);
					onClose();
				}}
			>
				{t.common.edit}
			</Button>
		</>
	) : null;
	const title = row?.category ?? t.attach.detailTitle;
	const body = row ? <Body book={book} row={row} /> : null;
	return narrow ? (
		<BottomSheet
			isOpen={row !== null}
			onOpenChange={(open) => !open && onClose()}
			title={title}
			footer={footer}
		>
			{body}
		</BottomSheet>
	) : (
		<Modal
			isOpen={row !== null}
			onOpenChange={(open) => !open && onClose()}
			title={title}
			footer={footer}
			size="sm"
		>
			{body}
		</Modal>
	);
}
