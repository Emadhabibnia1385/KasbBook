import { tv } from "tailwind-variants";
import { EmptyState, ErrorState, Pager, TableSkeleton } from "@nyxon/nasim";
import type { BookResponse, TransactionResponse } from "@/api/generated/model";
import { DownIcon, UpIcon } from "@/shared/icons";
import { formatDay } from "@/shared/format";
import { Amount } from "./Amount";
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
	onOpen,
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
	onOpen: (row: TransactionResponse) => void;
}) {
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
							<button type="button" className={slots.button()} onClick={() => onOpen(item)}>
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
								<Amount row={item} book={book} />
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
		</div>
	);
}
