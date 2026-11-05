import { useSyncExternalStore } from "react";
import { useBooksListBooks } from "@/api/generated/books/books";

const KEY = "kasbbook.book";
const listeners = new Set<() => void>();

function read(): string | null {
	try {
		return localStorage.getItem(KEY);
	} catch {
		return null;
	}
}

function subscribe(listener: () => void) {
	listeners.add(listener);
	window.addEventListener("storage", listener);
	return () => {
		listeners.delete(listener);
		window.removeEventListener("storage", listener);
	};
}

export function selectBook(id: string) {
	try {
		localStorage.setItem(KEY, id);
	} catch {
		// the choice lasts until the page is closed
	}
	listeners.forEach((listener) => listener());
}

/** The books the person can reach, and the one every screen is currently about. */
export function useActiveBook() {
	const query = useBooksListBooks();
	const saved = useSyncExternalStore(subscribe, read, () => null);
	const books = query.data ?? [];
	// A saved id for a book that is gone (left, deleted) falls back to the first one.
	const book = books.find((candidate) => candidate.id === saved) ?? books[0];
	return {
		books,
		book,
		isLoading: query.isLoading,
		isError: query.isError,
		refetch: query.refetch,
	};
}
