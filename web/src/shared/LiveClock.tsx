import { useAuthMe } from "@/api/generated/auth/auth";
import { clockTime, jalaliDate, numericDates, weekdayName } from "@/features/market/format";
import { useNowSeconds } from "@/shared/clock";
import { t } from "@/strings";

// The clock, and today in both calendars as plain numbers: «۱۴۰۵/۰۸/۱۵ · 2026/11/06». A screen reader hears
// the date once, in words, not the seconds: the ticking part is hidden from it.
export function LiveClock({ withDate = true }: { withDate?: boolean }) {
	const now = useNowSeconds();
	const zone = useAuthMe().data?.timezone;
	const dates = numericDates(now, zone);
	return (
		<div className="flex min-w-0 flex-col items-end leading-tight">
			<span aria-hidden className="flex items-center gap-2 text-sm font-semibold">
				<span>{weekdayName(now, zone)}</span>
				<span className="tabular-nums" dir="ltr">
					{clockTime(now, zone)}
				</span>
			</span>
			{withDate ? (
				<span aria-hidden className="flex items-center gap-1.5 text-xs text-muted tabular-nums">
					<span>{dates.jalali}</span>
					<span>·</span>
					<span dir="ltr">{dates.gregorian}</span>
				</span>
			) : null}
			<span className="sr-only">
				{t.clock.label}: {jalaliDate(now, zone)}
			</span>
		</div>
	);
}
