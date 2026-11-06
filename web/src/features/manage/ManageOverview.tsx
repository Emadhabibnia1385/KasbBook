import { Link } from "@tanstack/react-router";
import { EmptyState, ErrorState, PageHeader, PageSkeleton, SectionCard } from "@nyxon/nasim";
import { useAnalyticsCashflow } from "@/api/generated/analytics/analytics";
import { useBooksWallet } from "@/api/generated/books/books";
import { usePayrollListPayslips, usePayrollListPeriods } from "@/api/generated/payroll/payroll";
import type { BookResponse } from "@/api/generated/model";
import { Loaded } from "@/features/analytics/Loaded";
import { useActiveBook } from "@/features/books/useActiveBook";
import { isPayrollBook } from "@/features/payroll/shared";
import { GroupedColumns } from "@/shared/charts";
import { color } from "@/shared/charts";
import { calendarOf, formatMoney } from "@/shared/format";
import { periodLabel } from "@/shared/periods";
import { t } from "@/strings";
import { ManageTabs } from "./ManageTabs";

const money = (book: BookResponse) => (value: string) => formatMoney(value, book.currency);

function Balances({ book }: { book: BookResponse }) {
	const wallet = useBooksWallet(book.id);
	return (
		<SectionCard title={t.manage.balances} description={t.manage.balancesHint}>
			<Loaded query={wallet}>
				{(rows) =>
					rows.length === 0 ? (
						<p className="text-sm text-muted">{t.manage.noBalances}</p>
					) : (
						<ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
							{rows.map((row) => (
								<li
									key={row.code}
									className="flex flex-col gap-0.5 rounded-xl border border-border bg-surface p-3"
								>
									<span className="text-xs text-muted">{row.code}</span>
									<span className="font-semibold">{formatMoney(row.amount, row.code)}</span>
								</li>
							))}
						</ul>
					)
				}
			</Loaded>
		</SectionCard>
	);
}

/** Each month's savings as a bar, and the running total as a line across them. */
function Savings({ book }: { book: BookResponse }) {
	const cal = calendarOf(book.calendar);
	const query = useAnalyticsCashflow(book.id, { months: 12 });
	return (
		<SectionCard title={t.manage.savingsTitle} description={t.manage.savingsLead}>
			<Loaded query={query}>
				{(points) => (
					<GroupedColumns
						title={t.manage.savingsTitle}
						hideTitle
						summary={t.manage.savingsSummary}
						rowHeader={t.analytics.chart.month}
						formatValue={money(book)}
						rows={points.map((point) => ({
							key: point.period,
							label: point.label,
							title: periodLabel(point.period, cal),
							values: { net: point.net, cumulative: point.cumulative_net },
						}))}
						bars={[{ key: "net", name: t.manage.saved, color: color.net }]}
						lines={[{ key: "cumulative", name: t.manage.cumulative, color: color.income }]}
					/>
				)}
			</Loaded>
		</SectionCard>
	);
}

/** What each member is owed and has been paid in the latest payroll period. */
function Salaries({ book }: { book: BookResponse }) {
	const periods = usePayrollListPeriods(book.id);
	const latest = periods.data?.[0];
	const slips = usePayrollListPayslips(book.id, latest?.id ?? "", {
		query: { enabled: latest !== undefined },
	});
	return (
		<SectionCard
			title={t.manage.salaryTitle}
			description={
				latest ? `${t.manage.salaryLead} ${t.manage.period}: ${latest.label}` : t.manage.salaryLead
			}
		>
			{periods.isLoading ? null : latest === undefined ? (
				<div className="flex flex-col items-start gap-2">
					<p className="text-sm text-muted">{t.manage.noPeriod}</p>
					<Link to="/team/periods" className="text-sm text-accent">
						{t.manage.openTeam}
					</Link>
				</div>
			) : (
				<Loaded query={slips}>
					{(rows) => (
						<GroupedColumns
							title={t.manage.salaryTitle}
							hideTitle
							summary={t.manage.salarySummary}
							rowHeader={t.payroll.tabs.members}
							formatValue={money(book)}
							rows={rows.map((slip) => ({
								key: slip.id,
								label: slip.display_name,
								title: slip.display_name,
								values: { net: slip.net_pay, paid: slip.paid },
							}))}
							bars={[
								{ key: "net", name: t.manage.netPay, color: color.net },
								{ key: "paid", name: t.manage.paid, color: color.income },
							]}
						/>
					)}
				</Loaded>
			)}
		</SectionCard>
	);
}

export function ManageOverview() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	return (
		<div className="flex flex-col gap-5">
			<ManageTabs />
			<PageHeader title={t.manage.title} description={t.manage.lead} />
			{!book ? (
				<EmptyState title={t.manage.needBookTitle} description={t.manage.needBook} />
			) : (
				<>
					<Balances book={book} />
					<Savings book={book} />
					{isPayrollBook(book) ? <Salaries book={book} /> : null}
				</>
			)}
		</div>
	);
}
