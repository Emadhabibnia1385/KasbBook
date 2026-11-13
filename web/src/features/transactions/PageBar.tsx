import { useState } from "react";
import { Pager } from "@nyxon/nasim";
import { toAscii } from "@/shared/format";
import { MAX_PER_PAGE, PER_PAGE_CHOICES, rememberPerPage } from "./perPage";
import { t } from "@/strings";

const digits = new Intl.NumberFormat("fa-IR", { useGrouping: false });

// Keyed by its value, so a size that changes from outside starts the box over on the new number.
function PerPageBox({ value, onChange }: { value: number; onChange: (value: number) => void }) {
	const [text, setText] = useState(digits.format(value));
	const choose = (next: number) => {
		setText(digits.format(next));
		if (next !== value) {
			rememberPerPage(next);
			onChange(next);
		}
	};
	const commit = () => {
		const wanted = Number(toAscii(text).replace(/\D/g, ""));
		// Nothing typed, or zero, puts the old number back rather than guessing.
		if (!Number.isFinite(wanted) || wanted < 1) return setText(digits.format(value));
		choose(Math.min(MAX_PER_PAGE, Math.trunc(wanted)));
	};
	return (
		<span
			className="inline-flex items-center gap-1.5 text-sm text-muted"
			title={t.txFilter.perPageHint}
		>
			{t.txFilter.perPage}
			<input
				type="text"
				inputMode="numeric"
				dir="ltr"
				aria-label={t.txFilter.perPage}
				value={text}
				onChange={(event) => setText(event.target.value)}
				onFocus={(event) => event.target.select()}
				onBlur={commit}
				onKeyDown={(event) => {
					if (event.key === "Enter") {
						event.preventDefault();
						commit();
					}
				}}
				className="h-8 w-16 rounded-lg border border-separator bg-surface px-1 text-center text-sm text-foreground outline-none focus:border-accent"
			/>
			{/* The usual sizes in one tap; a size typed in the box that is not among them shows as blank. */}
			<select
				aria-label={t.txFilter.perPageQuick}
				value={PER_PAGE_CHOICES.includes(value) ? String(value) : ""}
				onChange={(event) => choose(Number(event.target.value))}
				className="h-8 rounded-lg border border-separator bg-surface px-1 text-sm text-foreground outline-none focus:border-accent"
			>
				<option value="" disabled hidden>
					—
				</option>
				{PER_PAGE_CHOICES.map((choice) => (
					<option key={choice} value={choice}>
						{digits.format(choice)}
					</option>
				))}
			</select>
		</span>
	);
}

// Under the list: the page and previous/next at the start (the right in Persian), how many entries a
// page holds at the end. The size box stays even when everything fits on one page, or a person who
// asked for a thousand could never get back to twenty.
export function PageBar({
	page,
	pageCount,
	onPageChange,
	perPage,
	onPerPageChange,
}: {
	page: number;
	pageCount: number;
	onPageChange: (page: number) => void;
	perPage: number;
	onPerPageChange: (value: number) => void;
}) {
	return (
		<div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
			{pageCount > 1 ? (
				<Pager
					className="gap-x-4"
					page={page}
					pageCount={pageCount}
					onPrevious={() => onPageChange(page - 1)}
					onNext={() => onPageChange(page + 1)}
					onPage={onPageChange}
				/>
			) : (
				<span />
			)}
			<PerPageBox key={perPage} value={perPage} onChange={onPerPageChange} />
		</div>
	);
}
