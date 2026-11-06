import { formatAmount } from "@/shared/format";
import { t } from "@/strings";

const DAY = 86_400_000;

const dayNumber = (iso: string) => Math.round(new Date(`${iso}T12:00:00`).getTime() / DAY);
const todayIso = () => {
	const now = new Date();
	const pad = (n: number) => String(n).padStart(2, "0");
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

/** Whole days from today to `iso`: negative once it has passed. */
export const daysUntil = (iso: string): number => dayNumber(iso) - dayNumber(todayIso());

/** «۳ روز دیگر», «سررسید امروز» or «۲ روز گذشته». */
export function dueText(iso: string): string {
	const days = daysUntil(iso);
	if (days === 0) return t.plan.dueToday;
	return days > 0
		? `${formatAmount(days)} ${t.plan.dueIn}`
		: `${formatAmount(-days)} ${t.plan.overdueBy}`;
}
