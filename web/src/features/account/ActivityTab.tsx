import { useState } from "react";
import {
	Button,
	DataTable,
	SearchBox,
	SectionCard,
	SelectField,
	StatCard,
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

/** The filters as the API takes them: nothing sent for «all». */
function toParams(f: Filter) {
	return {
		category: f.category === ALL ? null : f.category,
		via: f.via === ALL ? null : f.via,
		who: f.who === ALL ? null : f.who,
		book_id: f.book === ALL ? null : f.book,
		q: f.q.trim() || null,
		start: pickedDay(f.start) || null,
		end: pickedDay(f.end) || null,
	};
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

/** One bar per day of the last month: a glance at when things happen. */
function Days({ days }: { days: readonly { day: string; count: number }[] }) {
	const top = Math.max(1, ...days.map((d) => d.count));
	return (
		<div className="flex h-16 items-end gap-0.5" dir="ltr" aria-hidden>
			{days.map((d) => (
				<span
					key={d.day}
					title={`${d.day}: ${formatAmount(d.count, 0)} ${t.events.perDay}`}
					className="min-w-0 flex-1 rounded-t bg-accent/70"
					style={{ height: `${Math.max(d.count ? 8 : 2, (d.count / top) * 100)}%` }}
				/>
			))}
		</div>
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
			<SectionCard title={t.events.title} description={t.events.lead}>
				<div className="flex flex-col gap-4">
					<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
						<StatCard label={t.events.total} value={formatAmount(summary.data?.total ?? 0, 0)} />
						{(summary.data?.by_via ?? []).slice(0, 3).map((row) => (
							<StatCard key={row.key} label={row.label} value={formatAmount(row.count, 0)} />
						))}
					</div>
					<span className="sr-only">{t.events.byDay}</span>
					{summary.data ? <Days days={summary.data.by_day} /> : null}
					<fieldset className="m-0 flex min-w-0 flex-wrap gap-2 border-0 p-0">
						<legend className="sr-only">{t.events.byCategory}</legend>
						<Button
							size="sm"
							variant={filter.category === ALL ? "primary" : "secondary"}
							onPress={() => set({ category: ALL })}
						>
							{t.events.allCategories}
						</Button>
						{(summary.data?.by_category ?? []).map((row) => (
							<Button
								key={row.key}
								size="sm"
								variant={filter.category === row.key ? "primary" : "secondary"}
								onPress={() => set({ category: row.key })}
							>
								{row.label} · {formatAmount(row.count, 0)}
							</Button>
						))}
					</fieldset>
				</div>
			</SectionCard>

			<SectionCard title={t.events.filters}>
				<div className="flex flex-col gap-3">
					<SearchBox
						label={t.events.search}
						placeholder={t.events.searchHint}
						value={filter.q}
						onChange={(q) => set({ q })}
					/>
					<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
						<div className="grid gap-3 sm:col-span-2 lg:col-span-1">
							<DayField
								label={t.events.from}
								value={filter.start}
								onChange={(start) => set({ start })}
							/>
							<DayField label={t.events.to} value={filter.end} onChange={(end) => set({ end })} />
						</div>
					</div>
					<div className="flex flex-wrap gap-2">
						<Button variant="secondary" isPending={exporting} onPress={() => void download()}>
							{exporting ? t.events.exporting : t.events.export}
						</Button>
						{filtered ? (
							<Button variant="ghost" onPress={() => (setFilter(NONE), setPage(1))}>
								{t.events.clear}
							</Button>
						) : null}
					</div>
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
