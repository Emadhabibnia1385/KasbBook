import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	PageSkeleton,
	SectionCard,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import type {
	BookResponse,
	PerformanceResponse,
	PeriodResponse,
	ShareResponse,
} from "@/api/generated/model";
import {
	usePayrollListPerformance,
	usePayrollListShares,
	usePayrollRecordPerformance,
} from "@/api/generated/payroll/payroll";
import { formatAmount, toAscii } from "@/shared/format";
import { t } from "@/strings";
import { plain } from "./decimal";
import { isEditable } from "./status";
import { refreshPayroll, reportError } from "./shared";
import { Figure, ItemCard } from "./ui";

// Each measured basis reads one column of the record; the other columns are not asked for.
const MEASURES = {
	hours: { field: "hours_worked", unit: t.payroll.hours, hint: t.payroll.performance.hintHours },
	days: { field: "days_worked", unit: t.payroll.days, hint: t.payroll.performance.hintDays },
	points: { field: "points", unit: t.payroll.points, hint: t.payroll.performance.hintPoints },
} as const;
type Measured = keyof typeof MEASURES;
const isMeasured = (basis: string): basis is Measured => basis in MEASURES;

const schema = z.object({
	value: z
		.string()
		.transform(toAscii)
		.refine((value) => /^\d+(\.\d{1,4})?$/.test(value), { error: t.payroll.performance.bad }),
});
type Values = z.input<typeof schema>;

function RecordForm({
	book,
	period,
	share,
	record,
	onDone,
}: {
	book: BookResponse;
	period: PeriodResponse;
	share: ShareResponse;
	record?: PerformanceResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const save = usePayrollRecordPerformance();
	const measure = MEASURES[share.basis as Measured];
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { value: record ? plain(record[measure.field]) : "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					await save.mutateAsync({
						bookId: book.id,
						periodId: period.id,
						data: { user_id: share.user_id, [measure.field]: values.value },
					});
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.performance.saved);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<TextField
				name="value"
				label={`${t.payroll.performance.value} (${measure.unit})`}
				description={measure.hint}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

// Only the people whose share is paid by measure: asking for hours from someone on a flat percentage has no use.
export function PeriodPerformance({
	book,
	period,
}: {
	book: BookResponse;
	period: PeriodResponse;
}) {
	const shares = usePayrollListShares(book.id);
	const records = usePayrollListPerformance(book.id, period.id);
	const [editing, setEditing] = useState<ShareResponse | null>(null);
	if (shares.isLoading || records.isLoading) return <PageSkeleton header={false} rows={2} />;
	if (shares.isError || records.isError)
		return <ErrorState onRetry={() => void Promise.all([shares.refetch(), records.refetch()])} />;

	const measured = (shares.data ?? []).filter((share) => isMeasured(share.basis));
	const byMember = new Map((records.data ?? []).map((record) => [record.user_id, record]));
	const editable = isEditable(period.status);
	const editingShare = editing && measured.find((share) => share.user_id === editing.user_id);

	return (
		<SectionCard title={t.payroll.performance.title} description={t.payroll.performance.lead}>
			{measured.length === 0 ? (
				<EmptyState title={t.payroll.performance.none} />
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{measured.map((share) => {
						const measure = MEASURES[share.basis as Measured];
						const record = byMember.get(share.user_id);
						return (
							<ItemCard
								key={share.user_id}
								title={share.display_name}
								aside={
									record ? (
										<Figure>
											{formatAmount(record[measure.field])} {measure.unit}
										</Figure>
									) : (
										<Figure tone="muted">{t.payroll.performance.notRecorded}</Figure>
									)
								}
								actions={
									editable ? (
										<Button size="sm" variant="secondary" onPress={() => setEditing(share)}>
											{record ? t.payroll.performance.change : t.payroll.performance.record}
										</Button>
									) : null
								}
							/>
						);
					})}
				</ul>
			)}
			<Modal
				isOpen={editingShare !== null && editingShare !== undefined}
				onOpenChange={(open) => !open && setEditing(null)}
				title={`${t.payroll.performance.record} ${editingShare?.display_name ?? ""}`}
				size="sm"
			>
				{editingShare ? (
					<RecordForm
						key={editingShare.user_id}
						book={book}
						period={period}
						share={editingShare}
						record={byMember.get(editingShare.user_id)}
						onDone={() => setEditing(null)}
					/>
				) : null}
			</Modal>
		</SectionCard>
	);
}
