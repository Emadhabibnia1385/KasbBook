import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import {
	BarTable,
	Button,
	ConfirmDialog,
	EmptyState,
	ErrorState,
	KeyValueList,
	Modal,
	Notice,
	PageHeader,
	PageSkeleton,
	SectionCard,
	StatusChip,
	toast,
} from "@nyxon/nasim";
import type { BookResponse, DistributionResponse } from "@/api/generated/model";
import {
	usePayrollClose,
	usePayrollDeletePeriod,
	usePayrollDistribution,
	usePayrollListPayslips,
	usePayrollListPeriods,
	usePayrollListShares,
} from "@/api/generated/payroll/payroll";
import { formatFullDate, formatMoney } from "@/shared/format";
import { t } from "@/strings";
import { barLength, isNegative, isPositive, isZero } from "./decimal";
import { PeriodAdjustments } from "./PeriodAdjustments";
import { PeriodEdit } from "./PeriodEdit";
import { PeriodPayslips } from "./PeriodPayslips";
import { PeriodPerformance } from "./PeriodPerformance";
import { PayrollPage } from "./PayrollPage";
import { periodStatusLabel, refreshPayroll, reportError } from "./shared";
import { isEditable, periodTone } from "./status";
import { ActionMenu, Figure } from "./ui";

// The whole arithmetic, shown rather than asserted: somebody about to be paid a share of a number should
// be able to see how the number was reached.
function Arithmetic({
	book,
	distribution,
}: {
	book: BookResponse;
	distribution: DistributionResponse;
}) {
	const shares = usePayrollListShares(book.id);
	const money = (value: string) => formatMoney(value, book.currency);
	const noShares = shares.data !== undefined && shares.data.length === 0;
	const fromTreasury = distribution.cost_policy === "from_treasury";

	return (
		<SectionCard title={t.payroll.arithmetic.title} description={t.payroll.arithmetic.lead}>
			<div className="flex flex-col gap-4">
				{noShares ? (
					<Notice tone="warning" title={t.payroll.needShares}>
						{t.payroll.needSharesBody}{" "}
						<Link to="/team" className="text-accent">
							{t.payroll.goShares}
						</Link>
					</Notice>
				) : null}
				<KeyValueList
					items={[
						{
							label: t.payroll.arithmetic.income,
							value: money(distribution.gross_income),
							numeric: true,
						},
						{
							label: t.payroll.arithmetic.costs,
							value: money(distribution.direct_costs),
							numeric: true,
						},
						{
							label: t.payroll.arithmetic.profit,
							value: money(distribution.net_profit),
							numeric: true,
						},
						!isZero(distribution.treasury_total) && {
							label: t.payroll.arithmetic.treasury,
							value: money(distribution.treasury_total),
							numeric: true,
						},
						fromTreasury && {
							label: `${t.payroll.arithmetic.treasuryNet} (${t.payroll.arithmetic.treasuryNetHint})`,
							value: (
								<Figure tone={isNegative(distribution.treasury_net) ? "bad" : "plain"}>
									{money(distribution.treasury_net)}
								</Figure>
							),
						},
						{
							label: t.payroll.arithmetic.distributable,
							value: <strong>{money(distribution.distributable)}</strong>,
							numeric: true,
						},
					]}
				/>
				{isPositive(distribution.shortfall) ? (
					<Notice tone="warning">
						{t.payroll.arithmetic.shortfall} {money(distribution.shortfall)}
					</Notice>
				) : null}
				<div className="hidden sm:block">
					<BarTable
						title={t.payroll.arithmetic.chartTitle}
						hideTitle
						labelHeader={t.payroll.arithmetic.item}
						valueHeaders={[t.payroll.arithmetic.amount]}
						empty={t.payroll.arithmetic.chartTitle}
						barFrom="sm"
						rows={[
							{
								key: "income",
								label: t.payroll.arithmetic.income,
								value: barLength(distribution.gross_income),
								cells: [money(distribution.gross_income)],
							},
							{
								key: "costs",
								label: t.payroll.arithmetic.costs,
								value: barLength(distribution.direct_costs),
								cells: [money(distribution.direct_costs)],
							},
							{
								key: "profit",
								label: t.payroll.arithmetic.profit,
								value: barLength(distribution.net_profit),
								cells: [money(distribution.net_profit)],
							},
							{
								key: "treasury",
								label: t.payroll.arithmetic.treasury,
								value: barLength(distribution.treasury_total),
								cells: [money(distribution.treasury_total)],
							},
							{
								key: "distributable",
								label: t.payroll.arithmetic.distributable,
								value: barLength(distribution.distributable),
								cells: [money(distribution.distributable)],
							},
						]}
					/>
				</div>
			</div>
		</SectionCard>
	);
}

function Detail({ book, periodId }: { book: BookResponse; periodId: string }) {
	const queryClient = useQueryClient();
	const navigate = useNavigate();
	const periods = usePayrollListPeriods(book.id);
	const distribution = usePayrollDistribution(book.id, periodId);
	const payslips = usePayrollListPayslips(book.id, periodId);
	const close = usePayrollClose();
	const remove = usePayrollDeletePeriod();
	const [editing, setEditing] = useState(false);
	const [closing, setClosing] = useState(false);
	const [removing, setRemoving] = useState(false);

	if (periods.isLoading || distribution.isLoading || payslips.isLoading)
		return <PageSkeleton stats={4} />;
	if (periods.isError || distribution.isError || payslips.isError) {
		return (
			<ErrorState
				onRetry={() =>
					void Promise.all([periods.refetch(), distribution.refetch(), payslips.refetch()])
				}
			/>
		);
	}
	const period = periods.data?.find((candidate) => candidate.id === periodId);
	if (!period || !distribution.data) {
		return (
			<EmptyState
				as="h1"
				title={t.payroll.period.notFound}
				action={
					<Link to="/team/periods" className="text-accent">
						{t.payroll.period.back}
					</Link>
				}
			/>
		);
	}

	const slips = payslips.data ?? [];
	const editable = isEditable(period.status);
	const locked = period.status === "locked";

	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={period.label}
				description={`${book.name} · ${formatFullDate(period.starts_on)} – ${formatFullDate(period.ends_on)}`}
				backHref="/team/periods"
				meta={
					<StatusChip tone={periodTone(period.status)} label={periodStatusLabel(period.status)} />
				}
				actions={
					<>
						{slips.length > 0 && !locked ? (
							<Button onPress={() => setClosing(true)}>{t.payroll.period.close}</Button>
						) : null}
						<ActionMenu
							label={`${t.payroll.period.menu}: ${period.label}`}
							items={[
								...(editable ? [{ id: "edit", label: t.payroll.period.edit }] : []),
								...(editable && slips.length === 0
									? [{ id: "delete", label: t.payroll.period.delete, danger: true }]
									: []),
							]}
							onAction={(id) => (id === "edit" ? setEditing(true) : setRemoving(true))}
						/>
					</>
				}
			/>
			{locked ? <Notice tone="info">{t.payroll.period.locked}</Notice> : null}

			<Arithmetic book={book} distribution={distribution.data} />
			<PeriodPerformance book={book} period={period} />
			<PeriodAdjustments book={book} period={period} />
			<PeriodPayslips book={book} period={period} slips={slips} />

			<Modal
				isOpen={editing}
				onOpenChange={setEditing}
				title={t.payroll.period.editTitle}
				size="sm"
			>
				<PeriodEdit book={book} period={period} onDone={() => setEditing(false)} />
			</Modal>
			<ConfirmDialog
				isOpen={closing}
				onOpenChange={setClosing}
				title={t.payroll.period.closeTitle}
				description={`${period.label}. ${t.payroll.period.closeBody}`}
				confirmLabel={t.payroll.period.close}
				tone="danger"
				onConfirm={async () => {
					try {
						await close.mutateAsync({ bookId: book.id, periodId: period.id });
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.period.closed);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
			<ConfirmDialog
				isOpen={removing}
				onOpenChange={setRemoving}
				title={t.payroll.period.deleteTitle}
				description={`${period.label}. ${t.payroll.period.deleteBody}`}
				confirmLabel={t.payroll.period.delete}
				tone="danger"
				onConfirm={async () => {
					try {
						await remove.mutateAsync({ bookId: book.id, periodId: period.id });
						toast.success(t.payroll.period.deleted);
						// Leave first: refreshing while this page is mounted would ask for a period that is gone.
						await navigate({ to: "/team/periods" });
						await refreshPayroll(queryClient, book.id);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}

export function PeriodDetail({ periodId }: { periodId: string }) {
	return <PayrollPage>{(book) => <Detail book={book} periodId={periodId} />}</PayrollPage>;
}
