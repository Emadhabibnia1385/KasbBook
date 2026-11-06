import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	DataTable,
	FormRoot,
	Modal,
	PageHeader,
	SectionCard,
	SelectField,
	StatusChip,
	SubmitButton,
	toast,
} from "@nyxon/nasim";
import type { BookResponse, PeriodResponse } from "@/api/generated/model";
import { usePayrollListPeriods, usePayrollOpenPeriod } from "@/api/generated/payroll/payroll";
import { calendarOf, formatFullDate, recentPeriods, toAscii } from "@/shared/format";
import { t } from "@/strings";
import { monthWindow } from "./calendar";
import { PayrollPage } from "./PayrollPage";
import { periodStatusLabel, refreshPayroll, reportError } from "./shared";
import { periodTone } from "./status";

const schema = z.object({
	month: z
		.string({ error: t.payroll.periods.needMonth })
		.min(1, { error: t.payroll.periods.needMonth }),
});
type Values = z.input<typeof schema>;

function OpenForm({
	book,
	onDone,
}: {
	book: BookResponse;
	onDone: (period: PeriodResponse) => void;
}) {
	const queryClient = useQueryClient();
	const open = usePayrollOpenPeriod();
	const MONTHS = recentPeriods(12, calendarOf(book.calendar));
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { month: MONTHS[0]?.value ?? "" },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				const month = MONTHS.find((candidate) => candidate.value === values.month);
				if (!month) return;
				try {
					// The same label the bot writes for a month, so the two never open it twice under different names.
					const period = await open.mutateAsync({
						bookId: book.id,
						data: {
							label: toAscii(month.label),
							...monthWindow(month.value, calendarOf(book.calendar)),
						},
					});
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.periods.opened);
					onDone(period);
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<SelectField name="month" label={t.payroll.periods.month} options={MONTHS} />
			<SubmitButton>{t.payroll.periods.open}</SubmitButton>
		</FormRoot>
	);
}

function List({ book }: { book: BookResponse }) {
	const navigate = useNavigate();
	const [opening, setOpening] = useState(false);
	const query = usePayrollListPeriods(book.id);
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.team}
				description={book.name}
				actions={<Button onPress={() => setOpening(true)}>{t.payroll.periods.open}</Button>}
			/>
			<SectionCard title={t.payroll.periods.title} description={t.payroll.periods.lead}>
				<DataTable<PeriodResponse>
					ariaLabel={t.payroll.periods.title}
					cards="md"
					status={query.isError ? "error" : query.isLoading ? "loading" : "ready"}
					onRetry={() => void query.refetch()}
					rows={query.data}
					getRowId={(row) => row.id}
					emptyTitle={t.payroll.periods.emptyTitle}
					empty={t.payroll.periods.empty}
					columns={[
						{
							id: "name",
							header: t.payroll.periods.name,
							isRowHeader: true,
							cell: (row) => (
								<Link
									to="/team/periods/$periodId"
									params={{ periodId: row.id }}
									className="font-medium text-accent"
								>
									{row.label}
								</Link>
							),
						},
						{
							id: "status",
							header: t.payroll.periods.status,
							cell: (row) => (
								<StatusChip tone={periodTone(row.status)} label={periodStatusLabel(row.status)} />
							),
						},
						{
							id: "window",
							header: t.payroll.periods.window,
							cell: (row) => `${formatFullDate(row.starts_on)} – ${formatFullDate(row.ends_on)}`,
						},
						{
							id: "see",
							header: "",
							isActions: true,
							cell: (row) => (
								<Link
									to="/team/periods/$periodId"
									params={{ periodId: row.id }}
									className="text-sm text-accent"
								>
									{t.payroll.periods.see}
								</Link>
							),
						},
					]}
				/>
			</SectionCard>
			<Modal isOpen={opening} onOpenChange={setOpening} title={t.payroll.periods.open} size="sm">
				<OpenForm
					book={book}
					onDone={(period) => {
						setOpening(false);
						void navigate({ to: "/team/periods/$periodId", params: { periodId: period.id } });
					}}
				/>
			</Modal>
		</div>
	);
}

export function Periods() {
	return <PayrollPage>{(book) => <List book={book} />}</PayrollPage>;
}
