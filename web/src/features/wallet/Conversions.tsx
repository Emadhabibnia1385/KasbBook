import { DayPair } from "@/shared/DayPair";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	DataTable,
	FormRoot,
	Modal,
	SelectField,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getBooksListConversionsQueryKey,
	getBooksWalletQueryKey,
	useBooksAddConversionAttachment,
	useBooksConvert,
	useBooksDeleteConversion,
	useBooksListConversions,
	useBooksUpdateConversion,
	useBooksWallet,
} from "@/api/generated/books/books";
import type {
	BookResponse,
	ConversionResponse,
	CurrencyOptionResponse,
} from "@/api/generated/model";
import { useQuotes } from "@/features/market/useQuotes";
import { AttachmentsField } from "@/features/transactions/AttachmentsField";
import { prepareFile } from "@/features/transactions/attachments";
import { pickedDay, todayPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { addMoney, multiplyMoney, percentOf } from "@/shared/decimal";
import { calendarOf, currencyName, formatAmount, formatMoney, toAscii } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const PER_PAGE = 10;

// Money stays a string from the keyboard to the API: it is only checked here, never parsed into a float.
const amount = z
	.string()
	.transform(toAscii)
	.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, {
		error: t.wallet.badAmount,
	});

function conversionSchema(baseCode: string | undefined) {
	return z
		.object({
			from: z.string({ error: t.wallet.needCurrency }).min(1, { error: t.wallet.needCurrency }),
			to: z.string({ error: t.wallet.needCurrency }).min(1, { error: t.wallet.needCurrency }),
			fromAmount: amount,
			toAmount: amount,
			baseValue: z.string(),
			occurred_on: z.string().min(1, { error: t.days.needDate }),
			note: z.string().max(300),
		})
		.superRefine((value, ctx) => {
			if (value.from && value.from === value.to) {
				ctx.addIssue({ code: "custom", path: ["to"], message: t.wallet.sameCurrency });
			}
			// The server says so rather than guess a rate when neither side is the book's own currency.
			const needsBase = value.from && value.to && value.from !== baseCode && value.to !== baseCode;
			if (needsBase && !amount.safeParse(value.baseValue).success) {
				ctx.addIssue({ code: "custom", path: ["baseValue"], message: t.wallet.badAmount });
			}
		});
}
type Values = z.input<ReturnType<typeof conversionSchema>>;

/** «۱ تتر ≈ ۲۶۹٬۸۰۷ تومان», turned round when the paid unit is the small one so the figure is not «۰». */
function priceLine(quote: { value: string; exact?: boolean }, from: string, to: string): string {
	const rate = Number(quote.value);
	const mark = quote.exact ? "" : ` (${t.fx.estimateShort})`;
	const line =
		rate > 0 && rate < 1
			? `${formatMoney("1", to)} ≈ ${formatAmount(String(Math.round((1 / rate) * 100) / 100), 2)} ${currencyName(from)}`
			: `${formatMoney("1", from)} ≈ ${formatAmount(quote.value, 4)} ${currencyName(to)}`;
	return `${t.wallet.suggestHint}: ${line}${mark}`;
}

// How much of the balance to move, one tap: the box is filled and can still be changed by hand.
const PORTIONS = [
	{ percent: 25, label: t.wallet.quarter },
	{ percent: 50, label: t.wallet.half },
	{ percent: 75, label: t.wallet.threeQuarters },
	{ percent: 100, label: t.wallet.all },
];

/** A new conversion, or with `conversion` the correction of one: units, amounts, day, note and files. */
function ConvertForm({
	book,
	options,
	conversion,
	onDone,
}: {
	book: BookResponse;
	options: CurrencyOptionResponse[];
	conversion?: ConversionResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const convert = useBooksConvert();
	const update = useBooksUpdateConversion();
	const addFile = useBooksAddConversionAttachment();
	const [queue, setQueue] = useState<File[]>([]);
	const held = options.filter((option) => option.enabled);
	const baseCode = options.find((option) => option.is_base)?.code;
	const schema = useMemo(() => conversionSchema(baseCode), [baseCode]);
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: conversion
			? {
					from: conversion.from_currency,
					to: conversion.to_currency,
					fromAmount: String(Number(conversion.from_amount)),
					toAmount: String(Number(conversion.to_amount)),
					baseValue: String(Number(conversion.base_value)),
					occurred_on: `${conversion.occurred_on}T12:00`,
					note: conversion.note ?? "",
				}
			: {
					from: held[0]?.code ?? "",
					to: held[1]?.code ?? "",
					fromAmount: "",
					toAmount: "",
					baseValue: "",
					occurred_on: todayPicker(),
					note: "",
				},
	});
	const from = useWatch({ control: form.control, name: "from" });
	const to = useWatch({ control: form.control, name: "to" });
	const fromAmount = toAscii(useWatch({ control: form.control, name: "fromAmount" }) ?? "");
	const toAmount = useWatch({ control: form.control, name: "toAmount" });
	// What can be moved out of the paid currency: the wallet's balance, plus what this very conversion
	// already took out of it when it is being corrected.
	const wallet = useBooksWallet(book.id);
	const balance = (() => {
		const held = wallet.data?.find((row) => row.code === from)?.amount;
		if (held === undefined) return "";
		return conversion && conversion.from_currency === from
			? addMoney(held, conversion.from_amount)
			: held;
	})();
	const positive = /^\d+(\.\d+)?$/.test(balance) && Number(balance) > 0;
	const needsBase = Boolean(from && to && from !== to && from !== baseCode && to !== baseCode);

	// Today's price of what is paid, in what is received: it fills the received amount as the paid one is
	// typed, until the person writes that one themselves.
	const quote = useQuotes(from && to && from !== to ? [from] : [], to || "IRT", !conversion)
		.data?.[0];
	const suggested =
		quote && /^\d+(\.\d+)?$/.test(fromAmount) ? multiplyMoney(fromAmount, quote.value) : "";
	const lastSuggested = useRef("");
	useEffect(() => {
		if (conversion || !suggested || Number(suggested) <= 0) return;
		const current = toAscii(toAmount ?? "");
		// Only an empty box, or the figure this put there itself, is replaced: never what was typed.
		if (current === "" || current === lastSuggested.current) {
			const shown = String(Number(suggested));
			lastSuggested.current = shown;
			form.setValue("toAmount", shown, { shouldValidate: false });
		}
	}, [suggested, conversion, form, toAmount]);

	const choices = held.map((option) => ({
		value: option.code,
		label: `${option.name} (${option.code})`,
	}));
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				const data = {
					from_currency: values.from,
					from_amount: values.fromAmount,
					to_currency: values.to,
					to_amount: values.toAmount,
					base_value: needsBase ? values.baseValue : null,
					occurred_on: pickedDay(values.occurred_on),
					note: values.note || null,
				};
				try {
					let id = conversion?.id;
					if (conversion) {
						await update.mutateAsync({ bookId: book.id, conversionId: conversion.id, data });
					} else {
						id = (await convert.mutateAsync({ bookId: book.id, data })).id;
					}
					let failed = 0;
					for (const file of queue) {
						try {
							await addFile.mutateAsync({
								bookId: book.id,
								conversionId: id as string,
								data: { file: await prepareFile(file) },
							});
						} catch {
							failed += 1;
						}
					}
					await queryClient.invalidateQueries({ queryKey: getBooksWalletQueryKey(book.id) });
					await queryClient.invalidateQueries({
						queryKey: getBooksListConversionsQueryKey(book.id),
					});
					toast.success(t.wallet.saved);
					if (failed) toast.danger(t.attach.someFailed);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<SelectField name="from" label={t.wallet.from} options={choices} isRequired />
			<TextField
				name="fromAmount"
				label={t.wallet.fromAmount}
				description={balance ? `${t.wallet.available}: ${formatMoney(balance, from)}` : undefined}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			{positive ? (
				<fieldset className="flex flex-wrap gap-2 border-0 p-0" aria-label={t.wallet.portion}>
					{PORTIONS.map((portion) => (
						<Button
							key={portion.percent}
							size="sm"
							variant="secondary"
							onPress={() =>
								form.setValue("fromAmount", percentOf(balance, portion.percent), {
									shouldValidate: true,
									shouldDirty: true,
								})
							}
						>
							{portion.label}
						</Button>
					))}
				</fieldset>
			) : null}
			<SelectField name="to" label={t.wallet.to} options={choices} isRequired />
			<TextField
				name="toAmount"
				label={t.wallet.toAmount}
				description={quote && !conversion ? priceLine(quote, from, to) : undefined}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			{needsBase ? (
				<TextField
					name="baseValue"
					label={`${t.wallet.baseValue} (${currencyName(baseCode ?? book.currency)})`}
					description={t.wallet.baseValueHint}
					inputMode="decimal"
					dir="ltr"
					isRequired
				/>
			) : null}
			<DayField name="occurred_on" label={t.wallet.date} isRequired />
			<TextField name="note" label={t.wallet.note} />
			<AttachmentsField
				bookId={book.id}
				{...(conversion ? { transactionId: conversion.id } : {})}
				segment="conversions"
				queue={queue}
				onQueue={setQueue}
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

/** Every conversion of the book in a table, a page at a time, each one editable, removable and with its files. */
export function Conversions({
	book,
	options,
}: {
	book: BookResponse;
	options: CurrencyOptionResponse[];
}) {
	const queryClient = useQueryClient();
	const [page, setPage] = useState(1);
	const [adding, setAdding] = useState(false);
	const [editing, setEditing] = useState<ConversionResponse | null>(null);
	const [removing, setRemoving] = useState<ConversionResponse | null>(null);
	const remove = useBooksDeleteConversion();
	const query = useBooksListConversions(book.id, { page, per_page: PER_PAGE });
	const cal = calendarOf(book.calendar);
	const enough = options.filter((option) => option.enabled).length >= 2;
	const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PER_PAGE));
	return (
		<div className="flex flex-col gap-3">
			<p className="text-sm text-muted">{t.wallet.conversionsHint}</p>
			{enough ? (
				<Button className="self-start" onPress={() => setAdding(true)}>
					{t.wallet.convert}
				</Button>
			) : (
				<p className="text-sm text-muted">{t.wallet.needTwo}</p>
			)}
			<DataTable<ConversionResponse>
				ariaLabel={t.wallet.conversions}
				cards="md"
				status={query.isLoading ? "loading" : query.isError ? "error" : "ready"}
				onRetry={() => void query.refetch()}
				rows={query.data?.items}
				getRowId={(row) => row.id}
				emptyTitle={t.wallet.noConversions}
				pagination={{ page, pageCount: pages, onPageChange: setPage }}
				columns={[
					{
						id: "date",
						header: t.wallet.date,
						isRowHeader: true,
						align: "center",
						className: "w-28 whitespace-nowrap",
						cell: (row) => <DayPair iso={row.occurred_on} cal={cal} />,
					},
					{
						id: "from",
						header: t.wallet.paid,
						align: "center",
						cell: (row) => <span dir="ltr">{formatMoney(row.from_amount, row.from_currency)}</span>,
					},
					{
						id: "to",
						header: t.wallet.received,
						align: "center",
						cell: (row) => <span dir="ltr">{formatMoney(row.to_amount, row.to_currency)}</span>,
					},
					{
						id: "note",
						header: t.wallet.note,
						align: "center",
						cell: (row) => (
							<span className="inline-flex max-w-56 items-center gap-1.5">
								<bdi className="truncate">{row.note ?? "—"}</bdi>
								{(row.attachment_count ?? 0) > 0 ? (
									<span title={t.attach.clip} className="shrink-0 text-xs text-muted">
										<span aria-hidden>📎</span>
										<span className="sr-only">{t.attach.clip}</span>{" "}
										{formatAmount(row.attachment_count ?? 0)}
									</span>
								) : null}
							</span>
						),
					},
					{
						id: "actions",
						header: <span className="sr-only">{t.wallet.edit}</span>,
						align: "center",
						isActions: true,
						className: "w-40",
						cell: (row) => (
							<span className="inline-flex gap-1">
								<Button size="sm" variant="secondary" onPress={() => setEditing(row)}>
									{t.wallet.edit}
								</Button>
								<Button size="sm" variant="ghost" onPress={() => setRemoving(row)}>
									{t.common.delete}
								</Button>
							</span>
						),
					},
				]}
			/>
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.wallet.convert} size="sm">
				<ConvertForm book={book} options={options} onDone={() => setAdding(false)} />
			</Modal>
			<Modal
				isOpen={editing !== null}
				onOpenChange={(open) => !open && setEditing(null)}
				title={t.wallet.editConversion}
				size="sm"
			>
				{editing ? (
					<ConvertForm
						key={editing.id}
						book={book}
						options={options}
						conversion={editing}
						onDone={() => setEditing(null)}
					/>
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.wallet.deleteTitle}
				description={t.wallet.deleteBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, conversionId: removing.id });
						await queryClient.invalidateQueries({ queryKey: getBooksWalletQueryKey(book.id) });
						await queryClient.invalidateQueries({
							queryKey: getBooksListConversionsQueryKey(book.id),
						});
						toast.success(t.wallet.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}
