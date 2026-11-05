import type { StatusTone } from "@nyxon/nasim";

export function periodTone(status: string): StatusTone {
	if (status === "locked") return "neutral";
	if (status === "paid") return "success";
	if (status === "awaiting_approval") return "warning";
	return "info";
}

/** Closed or paid out: the bot stops offering edits here, and so does the panel. */
export const isEditable = (status: string) => status !== "locked" && status !== "paid";
