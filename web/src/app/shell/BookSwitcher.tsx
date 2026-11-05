import { useState } from "react";
import { tv } from "tailwind-variants";
import { BottomSheet, Modal, useMediaQuery } from "@nyxon/nasim";
import { selectBook, useActiveBook } from "@/features/books/useActiveBook";
import { BookIcon, CheckIcon, ChevronDownIcon } from "@/shared/icons";
import { t } from "@/strings";

const trigger = tv({
	base: "flex h-10 max-w-48 min-w-0 items-center gap-2 rounded-full border border-border bg-surface ps-3 pe-2 text-sm font-medium transition-colors hover:bg-surface-secondary",
});

const option = tv({
	base: "flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-start text-base transition-colors hover:bg-surface-secondary",
	variants: { active: { true: "bg-accent-soft text-accent-soft-foreground font-semibold" } },
});

// Every screen is about one book; this is where the person changes which. A pill that opens a sheet on
// a phone and a dialog on a desktop: the platform's own picker looked foreign next to the rest of the bar.
export function BookSwitcher() {
	const { books, book } = useActiveBook();
	const [open, setOpen] = useState(false);
	const wide = useMediaQuery("(min-width: 768px)");
	if (books.length < 2 || !book) return null;

	const list = (
		<ul className="flex flex-col gap-1" aria-label={t.book.switcher}>
			{books.map((item) => (
				<li key={item.id}>
					<button
						type="button"
						aria-current={item.id === book.id}
						className={option({ active: item.id === book.id })}
						onClick={() => {
							selectBook(item.id);
							setOpen(false);
						}}
					>
						<BookIcon aria-hidden className="size-5 shrink-0" />
						<span className="min-w-0 flex-1 truncate">{item.name}</span>
						{item.id === book.id ? <CheckIcon aria-hidden className="size-5 shrink-0" /> : null}
					</button>
				</li>
			))}
		</ul>
	);

	return (
		<>
			<button
				type="button"
				className={trigger()}
				aria-haspopup="dialog"
				onClick={() => setOpen(true)}
			>
				<BookIcon aria-hidden className="size-5 shrink-0 text-muted" />
				<span className="truncate">{book.name}</span>
				<ChevronDownIcon aria-hidden className="size-4 shrink-0 text-muted" />
			</button>
			{wide ? (
				<Modal isOpen={open} onOpenChange={setOpen} title={t.book.switcher} size="xs">
					{list}
				</Modal>
			) : (
				<BottomSheet isOpen={open} onOpenChange={setOpen} title={t.book.switcher}>
					{list}
				</BottomSheet>
			)}
		</>
	);
}
