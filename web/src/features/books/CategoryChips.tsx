import { Button } from "@nyxon/nasim";
import { useBooksListCategories } from "@/api/generated/books/books";
import { t } from "@/strings";

const MAX_CHIPS = 12;

/** The book's own categories for one flow, as buttons that fill a category field with a tap. */
export function CategoryChips({ bookId, flow, onPick }: { bookId: string; flow: "income" | "expense"; onPick: (name: string) => void }) {
	const { data = [] } = useBooksListCategories(bookId, { flow });
	if (data.length === 0) return null;
	return (
		<fieldset className="flex flex-wrap gap-2">
			<legend className="sr-only">{t.txExtra.suggestions}</legend>
			{data.slice(0, MAX_CHIPS).map((category) => (
				<Button key={category.id} size="sm" variant="outline" onPress={() => onPick(category.name)}>
					{category.name}
				</Button>
			))}
		</fieldset>
	);
}
