import { StatusChip } from "@nyxon/nasim";
import { formatAmount } from "@/shared/format";
import { DownIcon, UpIcon } from "@/shared/icons";
import { t } from "@/strings";

type DeltaChipProps = {
	/** The API's percent string; null when the earlier figure was zero. */
	percent: string | null | undefined;
	/** The API's absolute change, to tell «new» from «unchanged» when there is no percent. */
	absolute: string;
	/** Whether a rise is good news (income) or bad (spending); decides the colour, never the words. */
	goodWhen: "up" | "down";
};

/** A change since the last period, as an arrow and words on a tint: «۱۲٪ افزایش». */
export function DeltaChip({ percent, absolute, goodWhen }: DeltaChipProps) {
	const direction = Number(absolute) > 0 ? "up" : Number(absolute) < 0 ? "down" : "flat";
	if (direction === "flat")
		return <StatusChip size="sm" tone="neutral" label={t.analytics.delta.flat} />;
	const tone = direction === goodWhen ? "success" : "danger";
	const words = direction === "up" ? t.analytics.delta.up : t.analytics.delta.down;
	const icon = direction === "up" ? <UpIcon /> : <DownIcon />;
	if (percent === null || percent === undefined) {
		return (
			<StatusChip
				size="sm"
				tone={tone}
				icon={icon}
				label={`${words} ${t.analytics.delta.fromZero}`}
			/>
		);
	}
	return (
		<StatusChip
			size="sm"
			tone={tone}
			icon={icon}
			label={`${formatAmount(percent.replace("-", ""))}٪ ${words}`}
		/>
	);
}
