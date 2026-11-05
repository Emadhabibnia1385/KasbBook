import { useState } from "react";
import { tv } from "tailwind-variants";
import {
	BottomSheet,
	Button,
	EmptyState,
	ErrorState,
	KeyValueList,
	Pager,
	TableSkeleton,
} from "@nyxon/nasim";
import type { BookResponse, TransactionResponse } from "@/api/generated/model";
import { DownIcon, UpIcon } from "@/shared/icons";
import { formatDay, formatFullDate, formatMoney } from "@/shared/format";
import { t } from "@/strings";

const row = tv({
	slots: {
		button:
			"flex min-h-16 w-full items-center gap-3 px-3 py-2 text-start transition-colors hover:bg-surface-secondary",
		badge: "grid size-9 shrink-0 place-items-center rounded-full",
	},
	variants: {
		income: {
			true: { badge: "bg-success-soft text-success" },
			false: { badge: "bg-default text-muted" },
		},
	},
});

// A phone's list: two lines per transaction instead of a card of five labelled fields, so a page of
// twenty fits in a few screens. The details and the actions open on a tap.
export function CompactRows({
	book,
	rows,
	status,
	onRetry,
	emptyTitle,
	empty,
	page,
	pageCount,
	onPageChange,
	onEdit,
	onRemove,
}: {
	book: BookResponse;
	rows: readonly TransactionResponse[] | undefined;
	status: "loading" | "error" | "ready";
	onRetry: () => void;
	emptyTitle: string;
	empty: string;
	page: number;
	pageCount: number;
	onPageChange: (page: number) => void;
	onEdit: (row: TransactionResponse) => void;
	onRemove: (row: TransactionResponse) => void;
}) {
	const [open, setOpen] = useState<TransactionResponse | null>(null);
	if (status === "loading") return <TableSkeleton />;
	if (status === "error") return <ErrorState onRetry={onRetry} />;
	if (!rows?.length) return <EmptyState title={emptyTitle} description={empty} />;
	return (
		<div className="flex flex-col gap-3">
			<ul
				aria-label={t.nav.transactions}
				className="overflow-hidden rounded-2xl border border-border bg-surface"
			>
				{rows.map((item) => {
					const income = item.flow === "income";
					const slots = row({ income });
					const Arrow = income ? UpIcon : DownIcon;
					return (
						<li key={item.id} className="border-b border-separator last:border-b-0">
							<button type="button" className={slots.button()} onClick={() => setOpen(item)}>
								<span className={slots.badge()}>
									<Arrow aria-hidden className="size-5" />
								</span>
								<span className="flex min-w-0 flex-1 flex-col">
									<span className="truncate font-medium">{item.category}</span>
									<span className="truncate text-xs text-muted">
										{formatDay(item.occurred_on)}
										{item.description ? ` · ${item.description}` : ""}
									</span>
								</span>
								<span dir="ltr" className={`shrink-0 text-sm font-semibold ${income ? "text-success" : ""}`}>
									<span className="sr-only">{income ? t.common.income : t.common.expense}</span>
									{income ? "+" : "−"}
									{formatMoney(item.converted_amount, book.currency)}
								</span>
							</button>
						</li>
					);
				})}
			</ul>
			{pageCount > 1 ? (
				<Pager
					page={page}
					pageCount={pageCount}
					onPrevious={() => onPageChange(page - 1)}
					onNext={() => onPageChange(page + 1)}
				/>
			) : null}
			<BottomSheet
				isOpen={open !== null}
				onOpenChange={(value) => !value && setOpen(null)}
				title={open?.category ?? ""}
				footer={
					open ? (
						<>
							<Button
								variant="danger-soft"
								onPress={() => {
									onRemove(open);
									setOpen(null);
								}}
							>
								{t.common.delete}
							</Button>
							<Button
								onPress={() => {
									onEdit(open);
									setOpen(null);
								}}
							>
								{t.common.edit}
							</Button>
						</>
					) : null
				}
			>
				{open ? (
					<KeyValueList
						items={[
							{
								label: t.transactions.amount,
								value: `${open.flow === "income" ? "+" : "−"}${formatMoney(open.converted_amount, book.currency)}`,
							},
							{
								label: t.transactions.kind,
								value: open.flow === "income" ? t.common.income : t.common.expense,
							},
							{ label: t.transactions.date, value: formatFullDate(open.occurred_on) },
							open.description ? { label: t.transactions.note, value: open.description } : null,
						]}
					/>
				) : null}
			</BottomSheet>
		</div>
	);
}
