import { useSyncExternalStore } from "react";
import { useBooksListBooks } from "@/api/generated/books/books";
import { calendarOf, registerBookCalendars, setActiveCalendar } from "@/shared/format";

// «scope»: a book id, or "all" (the default). The old key held only a book, and everyone began on it.
const KEY = "kasbbook.scope";
export const ALL = "all";
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

/**
 * The books the person can reach, and which of them every screen is about: one chosen book, or all of
 * them (`all`, the default once there are two or more). With a single book, that book is always it.
 */
export function useActiveBook() {
	const query = useBooksListBooks();
	const saved = useSyncExternalStore(subscribe, read, () => null);
	const books = query.data ?? [];
	const chosen = books.find((candidate) => candidate.id === saved);
	// A saved id for a book that is gone (left, deleted) falls back to all of them.
	const book = chosen ?? (books.length === 1 ? books[0] : undefined);
	// Every date drawn from here on follows the book's calendar (see formatDay).
	registerBookCalendars(books);
	setActiveCalendar(calendarOf(book?.calendar));
	return {
		books,
		book,
		/** True when no single book is chosen and there is more than one to span. */
		all: book === undefined && books.length > 1,
		isLoading: query.isLoading,
		isError: query.isError,
		refetch: query.refetch,
	};
}
