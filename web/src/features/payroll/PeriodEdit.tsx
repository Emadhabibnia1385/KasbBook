import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, DateTimeField, FormRoot, SubmitButton, TextField, toast } from "@nyxon/nasim";
import type { BookResponse, PeriodResponse } from "@/api/generated/model";
import { usePayrollUpdatePeriod } from "@/api/generated/payroll/payroll";
import { t } from "@/strings";
import { fromFieldValue, monthEndOf, toFieldValue } from "./calendar";
import { refreshPayroll, reportError } from "./shared";

const schema = z
	.object({
		label: z.string().trim().min(1, { error: t.payroll.period.needLabel }).max(40),
		starts_on: z.string().min(1, { error: t.payroll.period.needDate }),
		ends_on: z.string().min(1, { error: t.payroll.period.needDate }),
	})
	.refine((values) => fromFieldValue(values.ends_on) >= fromFieldValue(values.starts_on), {
		path: ["ends_on"],
		error: t.payroll.period.endBeforeStart,
	});
type Values = z.input<typeof schema>;

// Renaming, and moving either end of the window. Moving it recalculates payslips on the server, keeping payments.
export function PeriodEdit({
	book,
	period,
	onDone,
}: {
	book: BookResponse;
	period: PeriodResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const update = usePayrollUpdatePeriod();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			label: period.label,
			starts_on: toFieldValue(period.starts_on),
			ends_on: toFieldValue(period.ends_on),
		},
	});
	const calendar = {
		calendarLabel: t.payroll.period.calendarLabel,
		timeLabel: t.payroll.period.timeLabel,
		clearLabel: t.payroll.period.clearLabel,
	};
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (values) => {
				const data = {
					...(values.label.trim() !== period.label ? { label: values.label.trim() } : {}),
					...(fromFieldValue(values.starts_on) !== period.starts_on
						? { starts_on: fromFieldValue(values.starts_on) }
						: {}),
					...(fromFieldValue(values.ends_on) !== period.ends_on
						? { ends_on: fromFieldValue(values.ends_on) }
						: {}),
				};
				if (Object.keys(data).length === 0) {
					onDone();
					return;
				}
				try {
					await update.mutateAsync({ bookId: book.id, periodId: period.id, data });
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.period.updated);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<p className="text-sm text-muted text-pretty">{t.payroll.period.windowHelp}</p>
			<TextField name="label" label={t.payroll.period.label} isRequired />
			<DateTimeField
				name="starts_on"
				label={t.payroll.period.starts}
				description={t.payroll.period.dateHint}
				isRequired
				{...calendar}
			/>
			<DateTimeField
				name="ends_on"
				label={t.payroll.period.ends}
				description={t.payroll.period.dateHint}
				isRequired
				{...calendar}
			/>
			<Button
				variant="tertiary"
				size="sm"
				onPress={() =>
					form.setValue(
						"ends_on",
						toFieldValue(monthEndOf(fromFieldValue(form.getValues("starts_on")))),
						{ shouldDirty: true, shouldValidate: true },
					)
				}
			>
				{t.payroll.period.endOfMonth}
			</Button>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}
