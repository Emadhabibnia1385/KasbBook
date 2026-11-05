import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	PageSkeleton,
	SectionCard,
	SelectField,
	StatusChip,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import { useBooksListMembers } from "@/api/generated/books/books";
import type { AdjustmentResponse, BookResponse, PeriodResponse } from "@/api/generated/model";
import {
	usePayrollAddAdjustment,
	usePayrollApproveAdjustment,
	usePayrollListAdjustments,
} from "@/api/generated/payroll/payroll";
import { formatAmount, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";
import { isNegative, isPositive, isZero } from "./decimal";
import { adjustmentKindLabel, refreshPayroll, reportError, signed } from "./shared";
import { isEditable } from "./status";
import { Figure, ItemCard } from "./ui";

// Signed on purpose: one field, because a value and a direction can disagree and a sign can not.
const schema = z.object({
	user_id: z
		.string({ error: t.payroll.adjustments.needMember })
		.min(1, { error: t.payroll.adjustments.needMember }),
	value: z
		.string()
		.transform((value) => toAscii(value).replace(/^[−–]/, "-").replace(/^\+/, ""))
		.refine((value) => /^-?\d+(\.\d{1,4})?$/.test(value) && !isZero(value), {
			error: t.payroll.adjustments.badValue,
		}),
	reason: z.string().trim().max(500),
});
type Values = z.input<typeof schema>;

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
		defaultValues: { user_id: "", value: "", reason: "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					// The sign already says which it is, so the person is not asked twice.
					await add.mutateAsync({
						bookId: book.id,
						periodId: period.id,
						data: {
							user_id: values.user_id,
							kind: isNegative(values.value) ? "penalty" : "bonus",
							mode: "amount",
							value: values.value,
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
			<TextField
				name="value"
				label={t.payroll.adjustments.value}
				description={t.payroll.adjustments.valueHint}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
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
	const queryClient = useQueryClient();
	const query = usePayrollListAdjustments(book.id, period.id);
	const approve = usePayrollApproveAdjustment();
	const [adding, setAdding] = useState(false);
	const [approving, setApproving] = useState<AdjustmentResponse | null>(null);
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
						<ItemCard
							key={row.id}
							title={row.display_name}
							aside={
								<StatusChip
									tone={row.is_approved ? "success" : "warning"}
									label={
										row.is_approved ? t.payroll.adjustments.approved : t.payroll.adjustments.pending
									}
								/>
							}
							actions={
								row.is_approved || !editable ? null : (
									<Button size="sm" variant="secondary" onPress={() => setApproving(row)}>
										{t.payroll.adjustments.approve}
									</Button>
								)
							}
						>
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
			<ConfirmDialog
				isOpen={approving !== null}
				onOpenChange={(open) => !open && setApproving(null)}
				title={t.payroll.adjustments.approveTitle}
				description={
					approving
						? `${approving.display_name}: ${approving.mode === "percent" ? `${formatAmount(approving.value)}٪` : formatMoney(approving.value, book.currency)}. ${t.payroll.adjustments.approveBody}`
						: undefined
				}
				confirmLabel={t.payroll.adjustments.approve}
				onConfirm={async () => {
					if (!approving) return;
					try {
						await approve.mutateAsync({
							bookId: book.id,
							periodId: period.id,
							adjustmentId: approving.id,
						});
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.adjustments.approvedToast);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
		</SectionCard>
	);
}
