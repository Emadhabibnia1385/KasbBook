import { BarTable, SectionCard } from "@nyxon/nasim";
import {
	useAnalyticsBudgetVsActual,
	useAnalyticsTopCategories,
} from "@/api/generated/analytics/analytics";
import type { BookResponse } from "@/api/generated/model";
import { DeltaChip, Gauge } from "@/shared/charts";
import { formatMoney } from "@/shared/format";
import { t } from "@/strings";
import { Loaded } from "./Loaded";

/** The month's budgets as rings: how much of each ceiling is used, against how much of the month has gone. */
export function BudgetGauges({ book, period }: { book: BookResponse; period: string }) {
	const query = useAnalyticsBudgetVsActual(book.id, { period });
	return (
		<SectionCard title={t.analytics.dashboard.budgetsTitle} description={t.analytics.budget.pace}>
			<Loaded query={query}>
				{(data) =>
					data.items.length === 0 ? (
						<p className="text-sm text-muted">{t.analytics.dashboard.noBudgets}</p>
					) : (
						<div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
							{data.items.map((item) => (
								<Gauge
									key={`${item.kind}:${item.label}`}
									label={item.label}
									percent={item.percent_used}
									elapsedPercent={data.elapsed_percent}
									detail={`${formatMoney(item.spent, book.currency)} ${t.analytics.budget.ofLimit} ${formatMoney(item.limit, book.currency)}`}
								/>
							))}
						</div>
					)
				}
			</Loaded>
		</SectionCard>
	);
}

/** The period's biggest categories, each with how it moved since the one before. */
export function TopCategories({
	book,
	period,
	flow,
	title,
	limit = 8,
}: {
	book: BookResponse;
	period: string;
	flow: "expense" | "income";
	title: string;
	limit?: number;
}) {
	const query = useAnalyticsTopCategories(book.id, { period, flow, limit });
	const money = (value: string) => formatMoney(value, book.currency);
	return (
		<SectionCard title={title}>
			<Loaded query={query}>
				{(rows) => (
					<BarTable
						title={title}
						hideTitle
						labelHeader={t.analytics.top.category}
						valueHeaders={[t.analytics.top.current, t.analytics.top.change]}
						empty={t.analytics.top.empty}
						barFrom="sm"
						tone={flow === "income" ? "success" : "accent"}
						rows={rows.map((row) => ({
							key: row.category,
							label: row.category,
							value: Number(row.current),
							cells: [
								<div key="now" className="flex flex-col items-end">
									<span>{money(row.current)}</span>
									<span className="text-xs text-muted">
										{t.analytics.top.previous}: {money(row.previous)}
									</span>
								</div>,
								<DeltaChip
									key="chip"
									percent={row.percent}
									absolute={row.absolute}
									goodWhen={flow === "income" ? "up" : "down"}
								/>,
							],
						}))}
					/>
				)}
			</Loaded>
		</SectionCard>
	);
}
