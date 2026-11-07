import { calendarOfBook, formatDay, formatOtherCalendar } from "@/shared/format";

/**
 * A day in its book's calendar with the same day in the other calendar under it, so a list never makes
 * anyone convert dates in their head.
 */
export function DayPair({
	iso,
	bookId,
	inline,
}: {
	iso: string;
	bookId: string;
	inline?: boolean;
}) {
	const cal = calendarOfBook(bookId);
	const other = (
		<bdi dir="ltr" className="tabular-nums text-muted">
			{formatOtherCalendar(iso, cal)}
		</bdi>
	);
	if (inline)
		return (
			<>
				{formatDay(iso, cal)}
				{" · "}
				{other}
			</>
		);
	return (
		<span className="flex flex-col items-center leading-tight">
			<span>{formatDay(iso, cal)}</span>
			<span className="text-xs">{other}</span>
		</span>
	);
}
