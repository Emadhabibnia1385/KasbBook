import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate } from "@tanstack/react-router";
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
	PageHeader,
	PageSkeleton,
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
import { ItemCard } from "./ui";

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
	// The month being paid is the one on top.
	const periods = [...(query.data ?? [])].sort((a, b) => b.starts_on.localeCompare(a.starts_on));
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.payroll.periods.title}
				description={book.name}
				actions={<Button onPress={() => setOpening(true)}>{t.payroll.periods.open}</Button>}
			/>
			<p className="text-sm text-muted">{t.payroll.periods.lead}</p>
			{query.isLoading ? (
				<PageSkeleton header={false} rows={3} />
			) : query.isError ? (
				<ErrorState onRetry={() => void query.refetch()} />
			) : periods.length === 0 ? (
				<EmptyState
					title={t.payroll.periods.emptyTitle}
					description={t.payroll.periods.empty}
					action={<Button onPress={() => setOpening(true)}>{t.payroll.periods.open}</Button>}
				/>
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{periods.map((period) => (
						<ItemCard
							key={period.id}
							title={
								<Link
									to="/team/periods/$periodId"
									params={{ periodId: period.id }}
									className="text-accent"
								>
									{period.label}
								</Link>
							}
							aside={
								<StatusChip
									tone={periodTone(period.status)}
									label={periodStatusLabel(period.status)}
								/>
							}
						>
							<p className="text-sm text-muted">
								{formatFullDate(period.starts_on)} – {formatFullDate(period.ends_on)}
							</p>
						</ItemCard>
					))}
				</ul>
			)}
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
