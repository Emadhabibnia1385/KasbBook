import { useState } from "react";
import {
	Button,
	DataTable,
	SearchBox,
	SectionCard,
	SelectField,
	StatusChip,
	toast,
} from "@nyxon/nasim";
import {
	useActivityListActivity,
	useActivityOptions,
	useActivitySummary,
} from "@/api/generated/activity/activity";
import type { ActivityItem } from "@/api/generated/model";
import { apiFetch } from "@/api/transport";
import { DayField } from "@/shared/DayField";
import { pickedDay } from "@/shared/dates";
import { formatAmount, formatStamp } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const PER_PAGE = 25;
const ALL = "all";

type Filter = {
	category: string;
	via: string;
	who: string;
	book: string;
	q: string;
	start: string;
	end: string;
};
const NONE: Filter = { category: ALL, via: ALL, who: ALL, book: ALL, q: "", start: "", end: "" };

/**
 * The filters as the API takes them. A filter that is not set is left out altogether: the generated client
 * writes a `null` as the word "null", which the server would read as a category called that.
 */
function toParams(f: Filter) {
	const params: Record<string, string> = {};
	if (f.category !== ALL) params.category = f.category;
	if (f.via !== ALL) params.via = f.via;
	if (f.who !== ALL) params.who = f.who;
	if (f.book !== ALL) params.book_id = f.book;
	if (f.q.trim()) params.q = f.q.trim();
	if (pickedDay(f.start)) params.start = pickedDay(f.start);
	if (pickedDay(f.end)) params.end = pickedDay(f.end);
	return params;
}

const viaTone = (via: string) => (via === "api" ? "info" : via === "bot" ? "success" : "neutral");

function Who({ row }: { row: ActivityItem }) {
	const name = row.is_me ? t.events.you : (row.user_name ?? t.events.system);
	return (
		<span className="inline-flex flex-wrap items-center justify-center gap-1.5">
			<bdi className="font-medium">{row.via === "api" ? t.events.viaApi : name}</bdi>
			{row.via === "api" ? (
				<span className="text-xs text-muted">
					<bdi>{name}</bdi>
				</span>
			) : (
				<StatusChip tone={viaTone(row.via)} label={row.via_label} />
			)}
		</span>
	);
}

export function ActivityTab() {
	const [filter, setFilter] = useState<Filter>(NONE);
	const [page, setPage] = useState(1);
	const [exporting, setExporting] = useState(false);
	const params = toParams(filter);
	const options = useActivityOptions();
	const summary = useActivitySummary(params);
	const list = useActivityListActivity({
		...params,
		limit: PER_PAGE,
		offset: (page - 1) * PER_PAGE,
	});
	const set = (patch: Partial<Filter>) => {
		setFilter((current) => ({ ...current, ...patch }));
		setPage(1);
	};
	const filtered = JSON.stringify(filter) !== JSON.stringify(NONE);
	const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PER_PAGE));
	const pick = (
		rows: readonly { key?: string; id?: string; name?: string; label?: string }[],
		all: string,
	) => [
		{ value: ALL, label: all },
		...rows.map((row) => ({ value: row.key ?? row.id ?? "", label: row.label ?? row.name ?? "" })),
	];

	const download = async () => {
		setExporting(true);
		try {
			const query = new URLSearchParams();
			for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
			const blob = await apiFetch<Blob>(`/api/v1/activity/export.csv?${query.toString()}`);
			const link = document.createElement("a");
			link.href = URL.createObjectURL(blob);
			link.download = "kasbbook-activity.csv";
			link.click();
			URL.revokeObjectURL(link.href);
			toast.success(t.events.exported);
		} catch (error) {
			reportFailure(error);
		} finally {
			setExporting(false);
		}
	};

	return (
		<div className="flex flex-col gap-5">
			<SectionCard
				title={t.events.filters}
				actions={
					<Button variant="secondary" isPending={exporting} onPress={() => void download()}>
						{exporting ? t.events.exporting : t.events.export}
					</Button>
				}
			>
				<div className="flex flex-col gap-4">
					<SearchBox
						label={t.events.search}
						placeholder={t.events.searchHint}
						value={filter.q}
						onChange={(q) => set({ q })}
					/>
					<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
						<SelectField
							label={t.events.category}
							value={filter.category}
							onChange={(category) => set({ category: category ?? ALL })}
							options={[
								{ value: ALL, label: t.events.allCategories },
								...(summary.data?.by_category ?? []).map((row) => ({
									value: row.key,
									label: `${row.label} (${formatAmount(row.count, 0)})`,
								})),
							]}
						/>
						<SelectField
							label={t.events.via}
							value={filter.via}
							onChange={(via) => set({ via: via ?? ALL })}
							options={pick(options.data?.vias ?? [], t.events.allVias)}
						/>
						<SelectField
							label={t.events.person}
							value={filter.who}
							onChange={(who) => set({ who: who ?? ALL })}
							options={pick(options.data?.people ?? [], t.events.allPeople)}
						/>
						<SelectField
							label={t.events.book}
							value={filter.book}
							onChange={(book) => set({ book: book ?? ALL })}
							options={pick(options.data?.books ?? [], t.events.allBooks)}
						/>
					</div>
					<div className="grid gap-3 sm:grid-cols-2">
						<DayField
							label={t.events.from}
							value={filter.start}
							onChange={(start) => set({ start })}
						/>
						<DayField label={t.events.to} value={filter.end} onChange={(end) => set({ end })} />
					</div>
					{filtered ? (
						<Button
							className="self-start"
							variant="ghost"
							onPress={() => (setFilter(NONE), setPage(1))}
						>
							{t.events.clear}
						</Button>
					) : null}
				</div>
			</SectionCard>

			<DataTable<ActivityItem>
				ariaLabel={t.events.title}
				cards="md"
				status={list.isLoading ? "loading" : list.isError ? "error" : "ready"}
				onRetry={() => void list.refetch()}
				rows={list.data?.items}
				getRowId={(row) => row.id}
				emptyTitle={filtered ? t.events.emptyFiltered : t.events.empty}
				pagination={{ page, pageCount: pages, onPageChange: setPage }}
				columns={[
					{
						id: "who",
						header: t.events.colWho,
						isRowHeader: true,
						align: "center",
						className: "w-44",
						cell: (row) => <Who row={row} />,
					},
					{
						id: "when",
						header: t.events.colWhen,
						align: "center",
						className: "w-52 whitespace-nowrap",
						cell: (row) => <span dir="ltr">{formatStamp(row.at)}</span>,
					},
					{
						id: "what",
						header: t.events.colWhat,
						align: "start",
						cell: (row) => (
							<span className="flex flex-col gap-0.5">
								<bdi>{row.summary}</bdi>
								<span className="text-xs text-muted">
									{row.category_label}
									{row.book_name ? ` · ${row.book_name}` : ""}
								</span>
							</span>
						),
					},
				]}
			/>
		</div>
	);
}
