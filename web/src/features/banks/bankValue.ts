/** What the form's value means to the server: left empty it chooses the book's default itself. */
export function bankValue(value: string): string | null | undefined {
	if (value === "") return undefined;
	return value === "none" ? null : value;
}
