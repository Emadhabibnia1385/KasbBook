import { selectBook, useActiveBook } from "@/features/books/useActiveBook";
import { t } from "@/strings";

// Every screen is about one book; this is where the person changes which. A native select is the
// best phone control there is: the platform draws the picker.
export function BookSwitcher() {
	const { books, book } = useActiveBook();
	if (books.length < 2 || !book) return null;
	return (
		<select
			aria-label={t.book.switcher}
			value={book.id}
			onChange={(event) => selectBook(event.target.value)}
			className="h-10 max-w-44 truncate rounded-field border border-border bg-surface px-3 text-sm"
		>
			{books.map((item) => (
				<option key={item.id} value={item.id}>
					{item.name}
				</option>
			))}
		</select>
	);
}
