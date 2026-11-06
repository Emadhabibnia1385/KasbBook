import { useAuthMe } from "@/api/generated/auth/auth";
import { clockTime, jalaliDate, numericDates, weekdayName } from "@/features/market/format";
import { useHeaderPrefs } from "@/features/market/headerPrefs";
import { useNowSeconds } from "@/shared/clock";
import { t } from "@/strings";

// The clock, the weekday and today in both calendars as plain numbers: «جمعه ۰۹:۱۸:۲۰» over
// «۱۴۰۵/۰۸/۱۵ · 2026/11/06». Each part follows the choice made in the settings. A screen reader hears the
// date once, in words, not the seconds: the ticking part is hidden from it.
export function LiveClock({
	withDate = true,
	align = "end",
}: {
	withDate?: boolean;
	align?: "end" | "center";
}) {
	const now = useNowSeconds();
	const zone = useAuthMe().data?.timezone;
	const prefs = useHeaderPrefs();
	const dates = numericDates(now, zone);
	const showDates = withDate && (prefs.jalali || prefs.gregorian);
	const showTop = prefs.time || prefs.weekday;
	if (!showTop && !showDates) return null;
	return (
		<div
			className={`flex min-w-0 flex-col leading-tight ${align === "center" ? "items-center" : "items-end"}`}
		>
			{showTop ? (
				<span aria-hidden className="flex items-center gap-2 text-sm font-semibold">
					{prefs.weekday ? <span>{weekdayName(now, zone)}</span> : null}
					{prefs.time ? (
						<span className="tabular-nums" dir="ltr">
							{clockTime(now, zone)}
						</span>
					) : null}
				</span>
			) : null}
			{showDates ? (
				<span aria-hidden className="flex items-center gap-1.5 text-xs text-muted tabular-nums">
					{prefs.jalali ? <span>{dates.jalali}</span> : null}
					{prefs.jalali && prefs.gregorian ? <span>·</span> : null}
					{prefs.gregorian ? <span dir="ltr">{dates.gregorian}</span> : null}
				</span>
			) : null}
			<span className="sr-only">
				{t.clock.label}: {jalaliDate(now, zone)}
			</span>
		</div>
	);
}
