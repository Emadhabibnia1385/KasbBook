import { EmptyState } from "@nyxon/nasim";
import { BookIcon } from "@/shared/icons";
import { t } from "@/strings";
import { selectBook, useActiveBook } from "./useActiveBook";

// Reports, the wallet, the team and the rest are about one book at a time. With all of them in view
// there is nothing to show yet, so the page asks which, right here, instead of guessing.
export function BookRequired() {
	const { books } = useActiveBook();
	if (books.length === 0)
		return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return (
		<section className="mx-auto flex max-w-md flex-col gap-4 py-6 text-center">
			<h1 className="text-lg font-bold">{t.scope.needsBookTitle}</h1>
			<p className="text-sm text-muted">{t.scope.needsBook}</p>
			<ul className="flex flex-col gap-2 text-start">
				{books.map((book) => (
					<li key={book.id}>
						<button
							type="button"
							className="flex min-h-12 w-full items-center gap-3 rounded-xl border border-border bg-surface px-4 transition-colors hover:bg-surface-secondary"
							onClick={() => selectBook(book.id)}
						>
							<BookIcon aria-hidden className="size-5 shrink-0 text-muted" />
							<span className="min-w-0 flex-1 truncate font-medium">{book.name}</span>
						</button>
					</li>
				))}
			</ul>
		</section>
	);
}
