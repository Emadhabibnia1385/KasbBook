import { createFileRoute } from "@tanstack/react-router";
import { Books } from "@/features/books/Books";

type Search = { new?: string | undefined };

export const Route = createFileRoute("/_app/books")({
	validateSearch: (search): Search => ({
		new:
			typeof search.new === "string" && /^[A-Za-z0-9]{2,8}$/.test(search.new)
				? search.new.toUpperCase()
				: undefined,
	}),
	component: BooksRoute,
});

function BooksRoute() {
	const { new: preset } = Route.useSearch();
	return <Books presetCurrency={preset} />;
}
