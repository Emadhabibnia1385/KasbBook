import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	PageSkeleton,
	SectionCard,
	SelectField,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import { useBooksListMembers } from "@/api/generated/books/books";
import type { BookResponse, PeriodResponse } from "@/api/generated/model";
import {
	usePayrollAddAdjustment,
	usePayrollListAdjustments,
} from "@/api/generated/payroll/payroll";
import { formatAmount, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";
import { isPositive, isZero, multiply, toUnits } from "./decimal";
import { adjustmentKindLabel, refreshPayroll, reportError, signed } from "./shared";
import { isEditable } from "./status";
import { Figure, ItemCard } from "./ui";

const LOWERS = new Set(["penalty", "shortfall", "advance"]);
const RAISES = new Set(["bonus", "overtime"]);
const KINDS = (["penalty", "shortfall", "advance", "bonus", "overtime", "correction"] as const).map(
	(value) => ({ value, label: t.payroll.adjustments.kindOptions[value] }),
);
const MODES = [
	{ value: "amount", label: t.payroll.adjustments.modeAmount },
	{ value: "percent", label: t.payroll.adjustments.modePercent },
];
const PLAIN = /^\d+(\.\d{1,4})?$/;
const SIGNED = /^-?\d+(\.\d{1,4})?$/;

const clean = (value: string) => toAscii(value).replace(/^[−–]/, "-").replace(/^\+/, "");

// What was typed becomes one signed amount: the kind says the direction, so the person only writes a size.
// For a correction, which can go either way, the sign they type is kept.
const schema = z
	.object({
		user_id: z
			.string({ error: t.payroll.adjustments.needMember })
			.min(1, { error: t.payroll.adjustments.needMember }),
		kind: z.string().min(1),
		mode: z.string().min(1),
		value: z.string().transform(clean),
		days: z.string().transform(clean),
		daily: z.string().transform(clean),
		reason: z.string().trim().max(500),
	})
	.superRefine((values, context) => {
		const helped = values.mode === "amount" && (values.days !== "" || values.daily !== "");
		if (helped) {
			if (
				!PLAIN.test(values.days) ||
				!PLAIN.test(values.daily) ||
				isZero(values.days) ||
				isZero(values.daily)
			)
				context.addIssue({
					code: "custom",
					path: ["days"],
					message: t.payroll.adjustments.helperBad,
				});
			return;
		}
		const correction = values.kind === "correction";
		const ok = (correction ? SIGNED : PLAIN).test(values.value) && !isZero(values.value);
		if (!ok)
			context.addIssue({
				code: "custom",
				path: ["value"],
				message: correction ? t.payroll.adjustments.badCorrection : t.payroll.adjustments.badValue,
			});
		else if (values.mode === "percent" && toUnits(values.value) > 100n * 10_000n)
			context.addIssue({
				code: "custom",
				path: ["value"],
				message: t.payroll.adjustments.badPercent,
			});
	});
type Values = z.input<typeof schema>;

/** The signed figure the server stores for what the form holds, or null while the helper is half filled. */
function signedValue(values: z.output<typeof schema>): string {
	const size =
		values.mode === "amount" && values.days !== "" && values.daily !== ""
			? multiply(values.days, values.daily)
			: values.value;
	if (values.kind === "correction") return size;
	const magnitude = size.replace(/^-/, "");
	return LOWERS.has(values.kind) ? `-${magnitude}` : RAISES.has(values.kind) ? magnitude : size;
}

function AddForm({
	book,
	period,
	onDone,
}: {
	book: BookResponse;
	period: PeriodResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const members = useBooksListMembers(book.id);
	const add = usePayrollAddAdjustment();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			user_id: "",
			kind: "penalty",
			mode: "amount",
			value: "",
			days: "",
			daily: "",
			reason: "",
		},
	});
	const [kind, mode, days, daily] = useWatch({
		control: form.control,
		name: ["kind", "mode", "days", "daily"],
	});
	const dayAmount =
		PLAIN.test(clean(days)) && PLAIN.test(clean(daily)) && clean(days) && clean(daily)
			? multiply(clean(days), clean(daily))
			: null;
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					await add.mutateAsync({
						bookId: book.id,
						periodId: period.id,
						data: {
							user_id: values.user_id,
							kind: values.kind,
							mode: values.mode,
							value: signedValue(values),
							reason: values.reason || null,
						},
					});
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.adjustments.saved);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<SelectField
				name="user_id"
				label={t.payroll.adjustments.member}
				options={(members.data ?? []).map((member) => ({
					value: member.user_id,
					label: member.display_name,
				}))}
				isRequired
			/>
			<SelectField
				name="kind"
				label={t.payroll.adjustments.kind}
				description={t.payroll.adjustments.kindHelp}
				options={KINDS}
			/>
			<SelectField name="mode" label={t.payroll.adjustments.mode} options={MODES} />
			{mode === "amount" ? (
				<div className="flex flex-col gap-3 rounded-xl border border-border p-3">
					<div>
						<p className="text-sm font-medium">{t.payroll.adjustments.helper}</p>
						<p className="text-xs text-muted">{t.payroll.adjustments.helperHint}</p>
					</div>
					<div className="grid grid-cols-2 gap-3">
						<TextField
							name="days"
							label={t.payroll.adjustments.days}
							inputMode="decimal"
							dir="ltr"
						/>
						<TextField
							name="daily"
							label={t.payroll.adjustments.daily}
							inputMode="decimal"
							dir="ltr"
						/>
					</div>
					{dayAmount ? (
						<p className="text-sm">
							{t.payroll.adjustments.helperResult}:{" "}
							<Figure tone={LOWERS.has(kind) ? "bad" : RAISES.has(kind) ? "good" : "plain"}>
								{formatMoney(dayAmount, book.currency)}
							</Figure>
						</p>
					) : null}
				</div>
			) : null}
			{dayAmount && mode === "amount" ? null : (
				<TextField
					name="value"
					label={
						mode === "percent"
							? t.payroll.adjustments.valuePercentLabel
							: t.payroll.adjustments.value
					}
					description={
						kind === "correction"
							? t.payroll.adjustments.valueHintCorrection
							: t.payroll.adjustments.valueHint
					}
					inputMode="decimal"
					dir="ltr"
					isRequired
				/>
			)}
			<TextField
				name="reason"
				label={t.payroll.adjustments.reason}
				description={t.payroll.adjustments.reasonHint}
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

export function PeriodAdjustments({
	book,
	period,
}: {
	book: BookResponse;
	period: PeriodResponse;
}) {
	const query = usePayrollListAdjustments(book.id, period.id);
	const [adding, setAdding] = useState(false);
	const editable = isEditable(period.status);

	return (
		<SectionCard
			title={t.payroll.adjustments.title}
			description={t.payroll.adjustments.lead}
			actions={
				editable ? (
					<Button size="sm" onPress={() => setAdding(true)}>
						{t.payroll.adjustments.add}
					</Button>
				) : null
			}
		>
			{query.isLoading ? (
				<PageSkeleton header={false} rows={2} />
			) : query.isError ? (
				<ErrorState onRetry={() => void query.refetch()} />
			) : query.data?.length ? (
				<ul className="grid gap-3 md:grid-cols-2">
					{query.data.map((row) => (
						<ItemCard key={row.id} title={row.display_name}>
							<p className="text-lg font-semibold">
								<Figure tone={isPositive(row.value) ? "good" : "bad"}>
									{signed(
										row.value,
										row.mode === "percent"
											? `${formatAmount(row.value)}٪`
											: formatMoney(row.value, book.currency),
									)}
								</Figure>
							</p>
							<p className="text-sm text-muted">
								{adjustmentKindLabel(row.kind)}
								{row.reason ? ` · ${row.reason}` : ""}
							</p>
						</ItemCard>
					))}
				</ul>
			) : (
				<EmptyState title={t.payroll.adjustments.empty} />
			)}

			<Modal isOpen={adding} onOpenChange={setAdding} title={t.payroll.adjustments.add} size="sm">
				<AddForm book={book} period={period} onDone={() => setAdding(false)} />
			</Modal>
		</SectionCard>
	);
}
