import { useAuthMe } from "@/api/generated/auth/auth";
import { useNowSeconds } from "@/shared/clock";
import { clockTime, jalaliDate } from "@/features/market/format";
import { t } from "@/strings";

// Today's Jalali date and a ticking clock, in the account's own time zone. A screen reader hears the
// date once, not the seconds: the ticking part is hidden from it and the date carries the label.
export function LiveClock({ withDate = true }: { withDate?: boolean }) {
	const now = useNowSeconds();
	const zone = useAuthMe().data?.timezone;
	return (
		<div className="flex min-w-0 flex-col items-end leading-tight">
			<span aria-hidden className="text-sm font-semibold tabular-nums" dir="ltr">
				{clockTime(now, zone)}
			</span>
			{withDate ? (
				<span className="truncate text-xs text-muted">{jalaliDate(now, zone)}</span>
			) : null}
			<span className="sr-only">
				{t.clock.label}: {jalaliDate(now, zone)}
			</span>
		</div>
	);
}
