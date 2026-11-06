import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { useState } from "react";
import { Button, FormRoot, SelectField, SubmitButton, TextField, toast } from "@nyxon/nasim";
import {
	getPortfolioListNotesQueryKey,
	getPortfolioPortfolioQueryKey,
	usePortfolioAddEntry,
	usePortfolioAddHolding,
	usePortfolioAddNote,
	usePortfolioUpdateEntry,
	usePortfolioUpdateHolding,
	usePortfolioUpdateNote,
} from "@/api/generated/portfolio/portfolio";
import type {
	BookResponse,
	FinancialNoteResponse,
	InstrumentResponse,
	NoteEntryResponse,
	PortfolioHoldingResponse,
} from "@/api/generated/model";
import { useCapitalBuyAsset } from "@/api/generated/capital/capital";
import { usePlanningListLoans } from "@/api/generated/planning/planning";
import { refresh } from "@/features/capital/refresh";
import { CurrencyPicker } from "@/features/currencies/CurrencyPicker";
import { pickedDay, todayPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { currencyName, formatAmount, formatMoney, toAscii } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const positive = (message: string) =>
	z
		.string()
		.transform(toAscii)
		.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, { error: message });
const optional = (message: string) =>
	z
		.string()
		.transform(toAscii)
		.refine((value) => value === "" || (/^\d+(\.\d{1,4})?$/.test(value) && Number(value) >= 0), {
			error: message,
		});

// ---------------------------------------------------------------- holdings
const holdingSchema = z.object({
	instrument: z.string().min(1),
	quantity: positive(t.portfolio.needQuantity),
	cost: optional(t.portfolio.needAmount),
	label: z.string().max(80),
	unit_price: optional(t.portfolio.needAmount),
	acquired_on: z.string(),
	note: z.string().max(500),
});
type HoldingValues = z.input<typeof holdingSchema>;

/** Adding something held, or changing how much of it and what it cost. */
export function HoldingForm({
	book,
	instruments,
	holding,
	onDone,
}: {
	book: BookResponse;
	instruments: InstrumentResponse[];
	holding?: PortfolioHoldingResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const add = usePortfolioAddHolding();
	const update = usePortfolioUpdateHolding();
	const form = useForm<HoldingValues>({
		resolver: zodResolver(holdingSchema),
		defaultValues: {
			instrument: holding?.instrument ?? "gold18",
			quantity: holding ? String(Number(holding.quantity)) : "",
			cost: holding?.cost ? String(Number(holding.cost)) : "",
			label:
				holding && holding.name !== instruments.find((i) => i.code === holding.instrument)?.name
					? holding.name
					: "",
			unit_price: "",
			acquired_on: holding?.acquired_on ? `${holding.acquired_on}T12:00` : todayPicker(),
			note: holding?.note ?? "",
		},
	});
	const code = useWatch({ control: form.control, name: "instrument" });
	const [picking, setPicking] = useState(false);
	const picked = instruments.find((item) => item.code === code);
	const manual = picked?.source === "manual";
	// Gold, coins and metals (and «other») are listed above; every currency and coin comes from the catalog.
	const things = instruments
		.filter((item) => item.source !== "market")
		.map((item) => ({ code: item.code, name: item.name, note: item.unit }));
	const pickedName = picked?.name ?? currencyName(code);
	const unit = picked?.unit ?? currencyName(code);
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = holdingSchema.parse(raw);
				if (
					manual &&
					(!values.label.trim() || Number(values.unit_price) <= 0 || !values.unit_price)
				) {
					form.setError("unit_price", { message: t.portfolio.needAmount });
					return;
				}
				try {
					if (holding) {
						await update.mutateAsync({
							bookId: book.id,
							holdingId: holding.id,
							data: {
								quantity: values.quantity,
								cost: values.cost ? values.cost : null,
								note: values.note || null,
								label: values.label || null,
								unit_price: manual && values.unit_price ? values.unit_price : null,
							},
						});
					} else {
						await add.mutateAsync({
							bookId: book.id,
							data: {
								instrument: values.instrument,
								quantity: values.quantity,
								cost: values.cost ? values.cost : null,
								label: values.label || null,
								unit_price: manual && values.unit_price ? values.unit_price : null,
								acquired_on: values.acquired_on ? pickedDay(values.acquired_on) : null,
								note: values.note || null,
							},
						});
					}
					await queryClient.invalidateQueries({ queryKey: getPortfolioPortfolioQueryKey(book.id) });
					toast.success(t.portfolio.saved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			{holding ? null : (
				<div className="flex flex-col gap-1.5">
					<span className="text-sm font-medium">{t.portfolio.instrument}</span>
					<Button
						variant="outline"
						className="w-full justify-between"
						onPress={() => setPicking(true)}
					>
						<span>{pickedName}</span>
						<span dir="ltr" className="text-sm text-muted">
							{picked?.source === "manual" || !/^[A-Z0-9]{2,8}$/.test(code) ? "" : code}
						</span>
					</Button>
					<CurrencyPicker
						isOpen={picking}
						onOpenChange={setPicking}
						title={t.portfolio.instrument}
						current={code}
						extras={things}
						extraLabel={t.portfolio.everything}
						without={["metal"]}
						onPick={(value) => form.setValue("instrument", value, { shouldValidate: true })}
					/>
				</div>
			)}
			{manual ? <TextField name="label" label={t.portfolio.label} isRequired /> : null}
			<TextField
				name="quantity"
				label={`${t.portfolio.quantity}${unit ? ` (${unit})` : ""}`}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			{manual ? (
				<TextField
					name="unit_price"
					label={t.portfolio.unitPrice}
					description={t.portfolio.unitPriceHint}
					inputMode="decimal"
					dir="ltr"
				/>
			) : null}
			<TextField
				name="cost"
				label={t.portfolio.costLabel}
				description={t.portfolio.costHint}
				inputMode="decimal"
				dir="ltr"
			/>
			{holding ? null : <DayField name="acquired_on" label={t.portfolio.date} />}
			<TextField name="note" label={t.portfolio.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

// ------------------------------------------------------------------- notes
const noteSchema = z.object({
	title: z.string().trim().min(1, { error: t.portfolio.needName }).max(120),
	text: z.string().max(2000),
});
type NoteValues = z.input<typeof noteSchema>;

export function NoteForm({
	book,
	note,
	onDone,
}: {
	book: BookResponse;
	note?: FinancialNoteResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const add = usePortfolioAddNote();
	const update = usePortfolioUpdateNote();
	const form = useForm<NoteValues>({
		resolver: zodResolver(noteSchema),
		defaultValues: { title: note?.title ?? "", text: note?.text ?? "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				try {
					if (note) {
						await update.mutateAsync({
							bookId: book.id,
							noteId: note.id,
							data: { title: values.title.trim(), text: values.text },
						});
					} else {
						await add.mutateAsync({
							bookId: book.id,
							data: { title: values.title.trim(), text: values.text || null },
						});
					}
					await queryClient.invalidateQueries({ queryKey: getPortfolioListNotesQueryKey(book.id) });
					toast.success(t.portfolio.saved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField name="title" label={t.portfolio.noteTitle} isRequired />
			<TextField name="text" label={t.portfolio.noteText} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

const entrySchema = z.object({
	kind: z.enum(["spent", "note"]),
	amount: optional(t.portfolio.needAmount),
	occurred_on: z.string().min(1),
	memo: z.string().max(1000),
});
type EntryValues = z.input<typeof entrySchema>;

/** One line of a note: money put in, or just a remark. With `entry`, a line already written is corrected. */
export function EntryForm({
	book,
	note,
	entry,
	onDone,
}: {
	book: BookResponse;
	note: FinancialNoteResponse;
	entry?: NoteEntryResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const add = usePortfolioAddEntry();
	const update = usePortfolioUpdateEntry();
	const form = useForm<EntryValues>({
		resolver: zodResolver(entrySchema),
		defaultValues: {
			kind: entry?.kind === "note" ? "note" : "spent",
			amount: entry?.amount ? String(Number(entry.amount)) : "",
			occurred_on: entry ? `${entry.occurred_on}T12:00` : todayPicker(),
			memo: entry?.memo ?? "",
		},
	});
	const kind = useWatch({ control: form.control, name: "kind" });
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = entrySchema.parse(raw);
				if (values.kind !== "note" && (!values.amount || Number(values.amount) <= 0)) {
					form.setError("amount", { message: t.portfolio.needAmount });
					return;
				}
				if (values.kind === "note" && !values.memo.trim()) {
					form.setError("memo", { message: t.portfolio.needMemo });
					return;
				}
				try {
					if (entry) {
						await update.mutateAsync({
							bookId: book.id,
							noteId: note.id,
							entryId: entry.id,
							data: {
								occurred_on: pickedDay(values.occurred_on),
								amount: values.kind === "note" ? null : values.amount,
								memo: values.memo,
							},
						});
					} else {
						await add.mutateAsync({
							bookId: book.id,
							noteId: note.id,
							data: {
								kind: values.kind,
								occurred_on: pickedDay(values.occurred_on),
								amount: values.kind === "note" ? null : values.amount,
								memo: values.memo || null,
							},
						});
					}
					await queryClient.invalidateQueries({ queryKey: getPortfolioListNotesQueryKey(book.id) });
					toast.success(t.portfolio.saved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			{entry ? null : (
				<>
					<SelectField
						name="kind"
						label={t.portfolio.entryKind}
						options={[
							{ value: "spent", label: t.portfolio.kinds.spent },
							{ value: "note", label: t.portfolio.kinds.note },
						]}
					/>
					<p className="text-sm text-muted">{t.portfolio.kindHint[kind]}</p>
				</>
			)}
			{kind === "note" ? null : (
				<TextField
					name="amount"
					label={t.portfolio.entryAmount}
					inputMode="decimal"
					dir="ltr"
					isRequired
				/>
			)}
			<DayField name="occurred_on" label={t.portfolio.entryDate} isRequired />
			<TextField name="memo" label={t.portfolio.entryMemo} isRequired={kind === "note"} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

// --------------------------------------------------- adding something held
const itemSchema = z.object({
	instrument: z.string().min(1),
	quantity: positive(t.portfolio.needQuantity),
	cost: optional(t.portfolio.needAmount),
	label: z.string().max(80),
	unit_price: optional(t.portfolio.needAmount),
	acquired_on: z.string(),
	note: z.string().max(500),
	pay: z.enum(["record", "cash", "loan"]),
	loan_id: z.string(),
	down: optional(t.portfolio.needAmount),
});
type ItemValues = z.input<typeof itemSchema>;

const PAYS = ["record", "cash", "loan"] as const;

/**
 * Adding something held: pick what it is, how much and what it cost, and how it was paid: only written
 * down, in cash from the wallet, or on one of the loans made under the instalments.
 */
export function AddItemForm({
	book,
	instruments,
	onDone,
}: {
	book: BookResponse;
	instruments: InstrumentResponse[];
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const add = usePortfolioAddHolding();
	const buy = useCapitalBuyAsset();
	const loans = usePlanningListLoans(book.id).data ?? [];
	// A loan can be tied to a purchase while it is still a plain one and nothing has been paid on it.
	const free = loans.filter((loan) => loan.kind === "consumer" && loan.paid_count === 0);
	const form = useForm<ItemValues>({
		resolver: zodResolver(itemSchema),
		defaultValues: {
			instrument: "gold18",
			quantity: "",
			cost: "",
			label: "",
			unit_price: "",
			acquired_on: todayPicker(),
			note: "",
			pay: "record",
			loan_id: "",
			down: "",
		},
	});
	const code = useWatch({ control: form.control, name: "instrument" });
	const pay = useWatch({ control: form.control, name: "pay" });
	const [picking, setPicking] = useState(false);
	const picked = instruments.find((item) => item.code === code);
	const manual = picked?.source === "manual";
	const things = instruments
		.filter((item) => item.source !== "market")
		.map((item) => ({ code: item.code, name: item.name, note: item.unit }));
	const pickedName = picked?.name ?? currencyName(code);
	const unit = picked?.unit ?? currencyName(code);
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = itemSchema.parse(raw);
				if (manual && !values.label.trim()) {
					form.setError("label", { message: t.portfolio.needName });
					return;
				}
				if (values.pay === "record") {
					if (manual && (!values.unit_price || Number(values.unit_price) <= 0)) {
						form.setError("unit_price", { message: t.portfolio.needAmount });
						return;
					}
				} else {
					if (!values.cost || Number(values.cost) <= 0) {
						form.setError("cost", { message: t.portfolio.needCost });
						return;
					}
					if (values.pay === "loan" && !values.loan_id) {
						form.setError("loan_id", { message: t.portfolio.needLoan });
						return;
					}
				}
				try {
					if (values.pay === "record") {
						await add.mutateAsync({
							bookId: book.id,
							data: {
								instrument: values.instrument,
								quantity: values.quantity,
								cost: values.cost ? values.cost : null,
								label: values.label || null,
								unit_price: manual && values.unit_price ? values.unit_price : null,
								acquired_on: values.acquired_on ? pickedDay(values.acquired_on) : null,
								note: values.note || null,
							},
						});
					} else {
						const group = picked?.group ?? "other";
						await buy.mutateAsync({
							bookId: book.id,
							data: {
								name: values.label || "",
								kind: ["gold", "coin", "metal"].includes(group) ? "gold" : "other",
								cost: values.cost,
								acquired_on: pickedDay(values.acquired_on),
								quantity: values.quantity,
								unit: manual ? null : unit,
								note: values.note || null,
								instrument: manual ? null : values.instrument,
								...(values.pay === "loan"
									? { loan_id: values.loan_id, down_payment: values.down ? values.down : null }
									: {}),
							},
						});
					}
					await refresh(queryClient, book.id);
					toast.success(t.portfolio.saved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<div className="flex flex-col gap-1.5">
				<span className="text-sm font-medium">{t.portfolio.instrument}</span>
				<Button
					variant="outline"
					className="w-full justify-between"
					onPress={() => setPicking(true)}
				>
					<span>{pickedName}</span>
					<span dir="ltr" className="text-sm text-muted">
						{manual || !/^[A-Z0-9]{2,8}$/.test(code) ? "" : code}
					</span>
				</Button>
				<CurrencyPicker
					isOpen={picking}
					onOpenChange={setPicking}
					title={t.portfolio.instrument}
					current={code}
					extras={things}
					extraLabel={t.portfolio.everything}
					without={["metal"]}
					onPick={(value) => form.setValue("instrument", value, { shouldValidate: true })}
				/>
			</div>
			{manual ? <TextField name="label" label={t.portfolio.label} isRequired /> : null}
			<TextField
				name="quantity"
				label={`${t.portfolio.quantity}${unit ? ` (${unit})` : ""}`}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			{manual && pay === "record" ? (
				<TextField
					name="unit_price"
					label={t.portfolio.unitPrice}
					description={t.portfolio.unitPriceHint}
					inputMode="decimal"
					dir="ltr"
				/>
			) : null}
			<TextField
				name="cost"
				label={t.portfolio.costLabel}
				description={t.portfolio.costHint}
				inputMode="decimal"
				dir="ltr"
			/>
			<DayField name="acquired_on" label={t.portfolio.date} />
			<div className="flex flex-col gap-1.5">
				<SelectField
					name="pay"
					label={t.portfolio.payWith}
					options={PAYS.map((kind) => ({
						value: kind,
						label:
							kind === "record"
								? t.portfolio.payRecord
								: kind === "cash"
									? t.portfolio.payCash
									: t.portfolio.payLoan,
					}))}
				/>
				<p className="text-sm text-muted">{t.portfolio.payHint[pay]}</p>
			</div>
			{pay === "loan" ? (
				free.length === 0 ? (
					<p className="rounded-xl border border-border p-3 text-sm text-muted">
						{t.portfolio.noLoans}
					</p>
				) : (
					<>
						<SelectField
							name="loan_id"
							label={t.portfolio.pickLoan}
							options={free.map((loan) => ({
								value: loan.id,
								label: `${loan.title} · ${formatAmount(loan.installment_count)} × ${formatMoney(loan.installment_amount, book.currency)}`,
							}))}
							isRequired
						/>
						<TextField name="down" label={t.portfolio.down} inputMode="decimal" dir="ltr" />
					</>
				)
			) : null}
			<TextField name="note" label={t.portfolio.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}
