import type { BookResponse } from "@/api/generated/model";

/**
 * A book other people work in. There, an account shows only this book's own share: never the account's
 * total, never what its other books hold, never an opening balance. Those belong to the account's owner
 * and to the books they keep for themselves; a team book is read by the whole team.
 */
export const isSharedBook = (book: BookResponse): boolean =>
	book.type === "team" || book.type === "organization";
