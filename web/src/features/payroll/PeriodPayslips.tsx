import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	BarTable,
	Button,
	ConfirmDialog,
	EmptyState,
	FormRoot,
	KeyValueList,
	Modal,
	Notice,
	SectionCard,
	SelectField,
	StatusChip,
	SubmitButton,
	TextField,
	toast,
	type StatusTone,
} from "@nyxon/nasim";
import { useEffect, useRef } from "react";
import { useBooksListCurrencies } from "@/api/generated/books/books";
import { useRates } from "@/features/market/useRates";
import type {
	BookResponse,
	PaymentResponse,
	PayslipResponse,
	PeriodResponse,
} from "@/api/generated/model";
import { usePayrollPay, usePayrollVoidPayment } from "@/api/generated/payroll/payroll";
import { currencyName, formatFullDate, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";
import { barLength, ceilDivide, isPositive, isZero, multiply, plain, sum } from "./decimal";
import { refreshPayroll, reportError, shareBasisLabel, shareValueText, signed } from "./shared";
import { Figure, ItemCard } from "./ui";

function slipState(slip: PayslipResponse): { tone: StatusTone; label: string } {
	if (!isZero(slip.overpaid)) return { tone: "danger", label: t.payroll.slips.over };
	if (isPositive(slip.outstanding)) {
		return isPositive(slip.paid)
			? { tone: "warning", label: t.payroll.slips.partial }
			: { tone: "neutral", label: t.payroll.slips.unpaid };
	}
	return isZero(slip.net_pay) && isZero(slip.paid)
		? { tone: "neutral", label: t.payroll.slips.zero }
		: { tone: "success", label: t.payroll.slips.settled };
}

const DECIMAL = /^\d+(\.\d{1,4})?$/;

function PayForm({
	book,
	slip,
	onDone,
}: {
	book: BookResponse;
	slip: PayslipResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const pay = usePayrollPay();
	const currencies = useBooksListCurrencies(book.id);
	const options = (currencies.data ?? [])
		.filter((currency) => currency.enabled)
		.map((currency) => ({ value: currency.code, label: currency.name }));
	const owes = isPositive(slip.outstanding);

	// A token needs the rate it changed hands at; the payslip's own currency never does.
	const schema = z
		.object({
			amount: z
				.string()
				.transform(toAscii)
				.refine((value) => DECIMAL.test(value) && isPositive(value), {
					error: t.payroll.pay.badAmount,
				}),
			currency: z.string(),
			rate: z.string().transform(toAscii),
			reference: z.string().trim().max(80),
		})
		.superRefine((values, context) => {
			if (values.currency === slip.currency) return;
			if (!values.rate)
				context.addIssue({ code: "custom", path: ["rate"], message: t.payroll.pay.needRate });
			else if (!DECIMAL.test(values.rate) || !isPositive(values.rate))
				context.addIssue({ code: "custom", path: ["rate"], message: t.payroll.pay.badRate });
		});
	type Values = z.input<typeof schema>;

	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			amount: owes ? plain(slip.outstanding) : "",
			currency: slip.currency,
			rate: "",
			reference: "",
		},
	});
	const currency = useWatch({ control: form.control, name: "currency" });
	const rate = useWatch({ control: form.control, name: "rate" });
	const foreign = currency !== slip.currency;
	// What the market says one unit of the chosen currency is worth in the slip's own. Prefilled once
	// per currency and then left alone: a rate the person typed is the rate they meant.
	const market = useRates(foreign ? `${currency}/${slip.currency}` : undefined);
	const quote = foreign ? market.data?.[0] : undefined;
	const filledFor = useRef<string | null>(null);
	useEffect(() => {
		if (!foreign) {
			filledFor.current = null;
			return;
		}
		if (quote && filledFor.current !== currency && !form.getValues("rate")) {
			form.setValue("rate", quote.value, { shouldDirty: true });
			filledFor.current = currency;
		}
	}, [foreign, quote, currency, form]);
	const rateOk = DECIMAL.test(toAscii(rate)) && isPositive(toAscii(rate));

	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				const other = values.currency !== slip.currency;
				try {
					await pay.mutateAsync({
						bookId: book.id,
						payslipId: slip.id,
						data: {
							amount: values.amount,
							currency: other ? values.currency : null,
							conversion_rate: other ? values.rate : null,
							reference: values.reference || null,
						},
					});
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.slips.paidToast);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<p className="text-sm text-muted">
				{t.payroll.pay.owed}: <Figure>{formatMoney(slip.outstanding, slip.currency)}</Figure>
			</p>
			{options.length > 1 ? (
				<SelectField name="currency" label={t.payroll.pay.currency} options={options} />
			) : null}
			{foreign ? (
				<TextField
					name="rate"
					label={`${t.payroll.pay.rate} (${currencyName(currency)} → ${currencyName(slip.currency)})`}
					description={
						// Only a warning is worth saying: the price is old, or there is none to fill in.
						quote
							? quote.stale
								? t.rateNote.stale
								: undefined
							: market.isLoading
								? undefined
								: t.rateNote.missing
					}
					inputMode="decimal"
					dir="ltr"
					isRequired
				/>
			) : null}
			<TextField
				name="amount"
				label={`${t.payroll.pay.amount} (${currencyName(currency)})`}
				description={t.payroll.pay.amountHint}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			{owes && (!foreign || rateOk) ? (
				<Button
					variant="tertiary"
					size="sm"
					onPress={() =>
						form.setValue(
							"amount",
							foreign
								? plain(ceilDivide(slip.outstanding, toAscii(rate)))
								: plain(slip.outstanding),
							{ shouldDirty: true, shouldValidate: true },
						)
					}
				>
					{t.payroll.pay.fillRest}
				</Button>
			) : null}
			<TextField
				name="reference"
				label={t.payroll.pay.reference}
				description={t.payroll.pay.referenceHint}
				dir="ltr"
			/>
			<SubmitButton>{t.payroll.pay.submit}</SubmitButton>
		</FormRoot>
	);
}

function Payments({
	slip,
	payments,
	canVoid,
	onVoid,
}: {
	slip: PayslipResponse;
	payments: readonly PaymentResponse[];
	canVoid: boolean;
	onVoid: (payment: PaymentResponse) => void;
}) {
	if (payments.length === 0)
		return <p className="text-sm text-muted">{t.payroll.slips.noPayments}</p>;
	return (
		<ul className="flex flex-col divide-y divide-separator rounded-xl border border-border">
			{payments.map((payment) => (
				<li
					key={payment.id}
					className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-3 py-2 text-sm"
				>
					<span className="flex min-w-0 flex-col">
						<Figure>
							{formatMoney(payment.amount, payment.currency)}
							{payment.currency !== slip.currency
								? ` (≈ ${formatMoney(multiply(payment.amount, payment.conversion_rate), slip.currency)})`
								: ""}
						</Figure>
						<span className="text-xs text-muted">
							{formatFullDate(payment.paid_on)}
							{payment.reference ? ` · ${payment.reference}` : ""}
						</span>
					</span>
					{canVoid ? (
						<Button size="sm" variant="ghost" onPress={() => onVoid(payment)}>
							{t.payroll.slips.void}
						</Button>
					) : null}
				</li>
			))}
		</ul>
	);
}

export function PeriodPayslips({
	book,
	period,
	slips,
}: {
	book: BookResponse;
	period: PeriodResponse;
	slips: readonly PayslipResponse[];
}) {
	const queryClient = useQueryClient();
	const pay = usePayrollPay();
	const voidPayment = usePayrollVoidPayment();
	const [paying, setPaying] = useState<PayslipResponse | null>(null);
	const [payingAll, setPayingAll] = useState<PayslipResponse | null>(null);
	const [voiding, setVoiding] = useState<{
		slip: PayslipResponse;
		payment: PaymentResponse;
	} | null>(null);
	const open = period.status !== "locked";
	const owedTotal = sum(
		slips.filter((slip) => isPositive(slip.outstanding)).map((slip) => slip.outstanding),
	);

	if (slips.length === 0) {
		return (
			<SectionCard title={t.payroll.slips.title}>
				<EmptyState title={t.payroll.slips.empty} />
			</SectionCard>
		);
	}

	return (
		<SectionCard
			title={t.payroll.slips.title}
			description={
				<>
					{t.payroll.slips.total}:{" "}
					<Figure>{formatMoney(sum(slips.map((slip) => slip.net_pay)), book.currency)}</Figure>
					{" · "}
					{isPositive(owedTotal) ? (
						<>
							{t.payroll.slips.owedTotal}: <Figure>{formatMoney(owedTotal, book.currency)}</Figure>
						</>
					) : (
						t.payroll.slips.allPaid
					)}
				</>
			}
		>
			<div className="flex flex-col gap-5">
				<div className="hidden sm:block">
					<BarTable
						title={t.payroll.slips.chartTitle}
						hideTitle
						labelHeader={t.payroll.slips.chartMember}
						valueHeaders={[t.payroll.slips.net, t.payroll.slips.owed]}
						empty={t.payroll.slips.empty}
						barFrom="sm"
						rows={slips.map((slip) => ({
							key: slip.id,
							label: slip.display_name,
							value: barLength(slip.net_pay),
							cells: [
								formatMoney(slip.net_pay, slip.currency),
								isPositive(slip.outstanding) ? formatMoney(slip.outstanding, slip.currency) : "—",
							],
						}))}
					/>
				</div>
				<ul className="grid gap-3 lg:grid-cols-2">
					{slips.map((slip) => {
						const state = slipState(slip);
						return (
							<ItemCard
								key={slip.id}
								title={slip.display_name}
								aside={<StatusChip tone={state.tone} label={state.label} />}
								tone={isZero(slip.overpaid) ? "plain" : "danger"}
								actions={
									open ? (
										<>
											{isPositive(slip.outstanding) ? (
												<Button size="sm" onPress={() => setPayingAll(slip)}>
													{t.payroll.slips.payAll} ({formatMoney(slip.outstanding, slip.currency)})
												</Button>
											) : null}
											<Button size="sm" variant="secondary" onPress={() => setPaying(slip)}>
												{t.payroll.slips.payPart}
											</Button>
										</>
									) : null
								}
							>
								<KeyValueList
									layout="grid"
									items={[
										{
											label: t.payroll.slips.basis,
											value: `${shareBasisLabel(slip.share_basis)} (${shareValueText(slip.share_basis, slip.share_value, (value) => formatMoney(value, slip.currency))})`,
										},
										{
											label: t.payroll.slips.distributable,
											value: formatMoney(slip.distributable_snapshot, slip.currency),
											numeric: true,
										},
										{
											label: t.payroll.slips.shareBase,
											value: formatMoney(slip.base_share, slip.currency),
											numeric: true,
										},
										!isZero(slip.adjustments_total) && {
											label: t.payroll.slips.adjustments,
											value: signed(
												slip.adjustments_total,
												formatMoney(slip.adjustments_total, slip.currency),
											),
											numeric: true,
										},
										{
											label: t.payroll.slips.net,
											value: <strong>{formatMoney(slip.net_pay, slip.currency)}</strong>,
											numeric: true,
										},
										{
											label: t.payroll.slips.paid,
											value: formatMoney(slip.paid, slip.currency),
											numeric: true,
										},
										isPositive(slip.outstanding) && {
											label: t.payroll.slips.owed,
											value: formatMoney(slip.outstanding, slip.currency),
											numeric: true,
										},
									]}
								/>
								{isZero(slip.overpaid) ? null : (
									<Notice
										tone="danger"
										title={`${t.payroll.slips.overpaid}: ${formatMoney(slip.overpaid, slip.currency)}`}
									>
										{t.payroll.slips.overpaidHint}
									</Notice>
								)}
								<div className="flex flex-col gap-2">
									<h3 className="text-sm font-semibold">{t.payroll.slips.payments}</h3>
									<Payments
										slip={slip}
										payments={slip.payments}
										canVoid={open}
										onVoid={(payment) => setVoiding({ slip, payment })}
									/>
								</div>
							</ItemCard>
						);
					})}
				</ul>
			</div>

			<Modal
				isOpen={paying !== null}
				onOpenChange={(isOpen) => !isOpen && setPaying(null)}
				title={`${t.payroll.pay.title} ${paying?.display_name ?? ""}`}
				size="sm"
			>
				{paying ? (
					<PayForm key={paying.id} book={book} slip={paying} onDone={() => setPaying(null)} />
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={payingAll !== null}
				onOpenChange={(isOpen) => !isOpen && setPayingAll(null)}
				title={t.payroll.slips.payAllTitle}
				description={
					payingAll
						? `${payingAll.display_name}: ${formatMoney(payingAll.outstanding, payingAll.currency)}. ${t.payroll.slips.payAllBody}`
						: undefined
				}
				confirmLabel={t.payroll.slips.payAll}
				onConfirm={async () => {
					if (!payingAll) return;
					try {
						await pay.mutateAsync({
							bookId: book.id,
							payslipId: payingAll.id,
							data: { amount: payingAll.outstanding },
						});
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.slips.paidToast);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
			<ConfirmDialog
				isOpen={voiding !== null}
				onOpenChange={(isOpen) => !isOpen && setVoiding(null)}
				title={t.payroll.slips.voidTitle}
				description={
					voiding
						? `${formatMoney(voiding.payment.amount, voiding.payment.currency)} · ${formatFullDate(voiding.payment.paid_on)}. ${t.payroll.slips.voidBody}`
						: undefined
				}
				confirmLabel={t.payroll.slips.void}
				tone="danger"
				onConfirm={async () => {
					if (!voiding) return;
					try {
						await voidPayment.mutateAsync({
							bookId: book.id,
							payslipId: voiding.slip.id,
							paymentId: voiding.payment.id,
						});
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.slips.voided);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
		</SectionCard>
	);
}
