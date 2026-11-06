import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { FormRoot, SelectField, SubmitButton, SwitchField, TextField, toast } from "@nyxon/nasim";
import {
	getCapitalListAssetsQueryKey,
	getCapitalListFundsQueryKey,
	getCapitalOverviewQueryKey,
	useCapitalBuyAsset,
	useCapitalContribute,
	useCapitalCreateFund,
	useCapitalReceivePayout,
	useCapitalSellAsset,
} from "@/api/generated/capital/capital";
import { getPlanningListLoansQueryKey } from "@/api/generated/planning/planning";
import type { AssetResponse, BookResponse, CircleResponse } from "@/api/generated/model";
import { pickedDay, todayPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { formatMoney, toAscii } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

// Money stays a string from the keyboard to the API: validated here, never turned into a number to send.
const amount = z
	.string()
	.transform(toAscii)
	.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, {
		error: t.capital.needAmount,
	});
const optionalAmount = z
	.string()
	.transform(toAscii)
	.refine((value) => value === "" || (/^\d+(\.\d{1,4})?$/.test(value) && Number(value) >= 0), {
		error: t.capital.needAmount,
	});
const count = z
	.string()
	.transform(toAscii)
	.refine((value) => /^\d+$/.test(value) && Number(value) > 0, { error: t.capital.needCount });

const KINDS = [
	{ value: "gold", label: t.capital.kinds.gold },
	{ value: "savings", label: t.capital.kinds.savings },
	{ value: "property", label: t.capital.kinds.property },
	{ value: "other", label: t.capital.kinds.other },
];

async function refresh(queryClient: ReturnType<typeof useQueryClient>, bookId: string) {
	await Promise.all([
		queryClient.invalidateQueries({ queryKey: getCapitalListAssetsQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getCapitalListFundsQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getCapitalOverviewQueryKey(bookId) }),
		queryClient.invalidateQueries({ queryKey: getPlanningListLoansQueryKey(bookId) }),
		refreshMoney(queryClient, bookId),
	]);
}

// ---------------------------------------------------------------- buying
const buySchema = z.object({
	name: z.string().trim().min(1, { error: t.capital.needName }).max(80),
	kind: z.string(),
	cost: amount,
	acquired_on: z.string().min(1),
	quantity: optionalAmount,
	unit: z.string().max(16),
	loan: z.boolean(),
	down: optionalAmount,
	installment: z.string(),
	installment_count: z.string(),
	loan_starts_on: z.string(),
});
type BuyValues = z.input<typeof buySchema>;

/** Buying something that is kept: in cash, or on a loan where no cash moves and the debt is booked with it. */
export function BuyAssetForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const buy = useCapitalBuyAsset();
	const form = useForm<BuyValues>({
		resolver: zodResolver(buySchema),
		defaultValues: {
			name: "",
			kind: "gold",
			cost: "",
			acquired_on: todayPicker(),
			quantity: "",
			unit: "",
			loan: false,
			down: "",
			installment: "",
			installment_count: "",
			loan_starts_on: todayPicker(),
		},
	});
	const loan = useWatch({ control: form.control, name: "loan" });
	const cost = toAscii(useWatch({ control: form.control, name: "cost" }) ?? "");
	const down = toAscii(useWatch({ control: form.control, name: "down" }) ?? "");
	const each = toAscii(useWatch({ control: form.control, name: "installment" }) ?? "");
	const times = toAscii(useWatch({ control: form.control, name: "installment_count" }) ?? "");
	const borrowed = Number(cost) - Number(down || 0);
	const total = Number(each) * Number(times);
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = buySchema.parse(raw);
				if (values.loan) {
					const piece = toAscii(values.installment);
					const n = toAscii(values.installment_count);
					if (!/^\d+(\.\d{1,4})?$/.test(piece) || Number(piece) <= 0) {
						form.setError("installment", { message: t.capital.needAmount });
						return;
					}
					if (!/^\d+$/.test(n) || Number(n) <= 0) {
						form.setError("installment_count", { message: t.capital.needCount });
						return;
					}
				}
				try {
					await buy.mutateAsync({
						bookId: book.id,
						data: {
							name: values.name,
							kind: values.kind,
							cost: values.cost,
							acquired_on: pickedDay(values.acquired_on),
							quantity: values.quantity ? values.quantity : null,
							unit: values.unit || null,
							...(values.loan
								? {
										down_payment: values.down ? values.down : null,
										installment_amount: toAscii(values.installment),
										installment_count: Number(toAscii(values.installment_count)),
										loan_starts_on: pickedDay(values.loan_starts_on),
									}
								: {}),
						},
					});
					await refresh(queryClient, book.id);
					toast.success(t.capital.saved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField name="name" label={t.capital.name} isRequired />
			<SelectField name="kind" label={t.capital.kind} options={KINDS} />
			<TextField name="cost" label={t.capital.cost} inputMode="decimal" dir="ltr" isRequired />
			<DayField name="acquired_on" label={t.capital.date} isRequired />
			<div className="grid grid-cols-2 gap-3">
				<TextField name="quantity" label={t.capital.quantity} inputMode="decimal" dir="ltr" />
				<TextField name="unit" label={t.capital.unit} />
			</div>
			<SwitchField name="loan" label={t.capital.withLoan} description={t.capital.withLoanHint} />
			{loan ? (
				<div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-3">
					<TextField name="down" label={t.capital.down} inputMode="decimal" dir="ltr" />
					<div className="grid grid-cols-2 gap-3">
						<TextField
							name="installment"
							label={t.capital.installment}
							inputMode="decimal"
							dir="ltr"
						/>
						<TextField
							name="installment_count"
							label={t.capital.installmentCount}
							inputMode="numeric"
							dir="ltr"
						/>
					</div>
					<DayField name="loan_starts_on" label={t.capital.loanStarts} />
					{Number.isFinite(borrowed) && borrowed > 0 ? (
						<p className="text-sm text-muted">
							{t.plan.totalPayable}:{" "}
							<b className="text-foreground">
								{Number.isFinite(total) && total > 0
									? formatMoney(String(total), book.currency)
									: "—"}
							</b>{" "}
							· {formatMoney(String(borrowed), book.currency)}
						</p>
					) : null}
					<p className="text-xs text-muted">{t.capital.interestNote}</p>
				</div>
			) : null}
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

// --------------------------------------------------------------- selling
const sellSchema = z.object({ price: amount, sold_on: z.string().min(1) });
type SellValues = z.input<typeof sellSchema>;

export function SellAssetForm({
	book,
	asset,
	onDone,
}: {
	book: BookResponse;
	asset: AssetResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const sell = useCapitalSellAsset();
	const form = useForm<SellValues>({
		resolver: zodResolver(sellSchema),
		defaultValues: { price: String(Number(asset.cost)), sold_on: todayPicker() },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = sellSchema.parse(raw);
				try {
					await sell.mutateAsync({
						bookId: book.id,
						assetId: asset.id,
						data: { price: values.price, sold_on: pickedDay(values.sold_on) },
					});
					await refresh(queryClient, book.id);
					toast.success(t.capital.sellDone);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<p className="text-sm text-muted">{t.capital.sellNote}</p>
			<TextField
				name="price"
				label={t.capital.sellPrice}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<DayField name="sold_on" label={t.capital.sellDate} isRequired />
			<SubmitButton>{t.capital.sell}</SubmitButton>
		</FormRoot>
	);
}

// ----------------------------------------------------------------- funds
const fundSchema = z.object({
	name: z.string().trim().min(1, { error: t.capital.needName }).max(80),
	monthly_amount: amount,
	months: count,
	payout_amount: amount,
	starts_on: z.string().min(1),
	turn_month: z.string().transform(toAscii),
});
type FundValues = z.input<typeof fundSchema>;

export function FundForm({ book, onDone }: { book: BookResponse; onDone: () => void }) {
	const queryClient = useQueryClient();
	const create = useCapitalCreateFund();
	const form = useForm<FundValues>({
		resolver: zodResolver(fundSchema),
		defaultValues: {
			name: "",
			monthly_amount: "",
			months: "",
			payout_amount: "",
			starts_on: todayPicker(),
			turn_month: "",
		},
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = fundSchema.parse(raw);
				const turn = values.turn_month ? Number(values.turn_month) : null;
				if (
					turn !== null &&
					(!Number.isInteger(turn) || turn < 1 || turn > Number(values.months))
				) {
					form.setError("turn_month", { message: t.capital.needCount });
					return;
				}
				try {
					await create.mutateAsync({
						bookId: book.id,
						data: {
							name: values.name,
							monthly_amount: values.monthly_amount,
							months: Number(values.months),
							payout_amount: values.payout_amount,
							starts_on: pickedDay(values.starts_on),
							turn_month: turn,
						},
					});
					await refresh(queryClient, book.id);
					toast.success(t.capital.fundSaved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<TextField name="name" label={t.capital.fundName} isRequired />
			<TextField
				name="monthly_amount"
				label={t.capital.monthly}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<div className="grid grid-cols-2 gap-3">
				<TextField
					name="months"
					label={t.capital.months}
					inputMode="numeric"
					dir="ltr"
					isRequired
				/>
				<TextField name="turn_month" label={t.capital.turn} inputMode="numeric" dir="ltr" />
			</div>
			<TextField
				name="payout_amount"
				label={t.capital.payout}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<DayField name="starts_on" label={t.capital.fundStarts} isRequired />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

// ------------------------------------------------- paying in, being paid
const moveSchema = z.object({ on: z.string().min(1), amount: optionalAmount });
type MoveValues = z.input<typeof moveSchema>;

/** One month into the fund, or the turn out of it: the day, and an amount only when it differs from the fund's own. */
export function FundMoveForm({
	book,
	fund,
	mode,
	onDone,
}: {
	book: BookResponse;
	fund: CircleResponse;
	mode: "pay" | "receive";
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const contribute = useCapitalContribute();
	const receive = useCapitalReceivePayout();
	const form = useForm<MoveValues>({
		resolver: zodResolver(moveSchema),
		defaultValues: { on: todayPicker(), amount: "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = moveSchema.parse(raw);
				const data = { on: pickedDay(values.on), amount: values.amount ? values.amount : null };
				try {
					if (mode === "pay") {
						await contribute.mutateAsync({ bookId: book.id, fundId: fund.id, data });
					} else {
						await receive.mutateAsync({ bookId: book.id, fundId: fund.id, data });
					}
					await refresh(queryClient, book.id);
					toast.success(mode === "pay" ? t.capital.paidDone : t.capital.receiveDone);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			<p className="text-sm text-muted">
				{mode === "pay" ? t.capital.payNote : t.capital.receiveNote}
			</p>
			<DayField name="on" label={t.capital.moveDate} isRequired />
			<TextField
				name="amount"
				label={t.capital.moveAmount}
				description={formatMoney(
					mode === "pay" ? fund.monthly_amount : fund.payout_amount,
					book.currency,
				)}
				inputMode="decimal"
				dir="ltr"
			/>
			<SubmitButton>{mode === "pay" ? t.capital.payMonth : t.capital.receive}</SubmitButton>
		</FormRoot>
	);
}
