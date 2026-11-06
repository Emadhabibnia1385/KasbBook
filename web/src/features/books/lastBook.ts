// The book an entry was last recorded in, so the next one opens on it when no single book is in view.
const KEY = "kasbbook.lastBook";

export function lastBook(): string | null {
	try {
		return localStorage.getItem(KEY);
	} catch {
		return null;
	}
}

export function rememberBook(id: string) {
	try {
		localStorage.setItem(KEY, id);
	} catch {
		// the next entry simply opens on the first book
	}
}
