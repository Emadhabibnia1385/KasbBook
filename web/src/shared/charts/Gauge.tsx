import { StatusChip } from "@nyxon/nasim";
import { formatAmount } from "@/shared/format";
import { t } from "@/strings";

const SIZE = 120;
const RADIUS = 46;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

type Tone = "success" | "warning" | "danger";

const STROKE: Record<Tone, string> = {
	success: "var(--success)",
	warning: "var(--warning)",
	danger: "var(--danger)",
};
const WORDS: Record<Tone, string> = {
	success: t.analytics.budget.safe,
	warning: t.analytics.budget.near,
	danger: t.analytics.budget.over,
};

/** How a share of a ceiling reads: comfortable, close to it, or past it. */
function budgetTone(percent: number): Tone {
	return percent > 100 ? "danger" : percent >= 80 ? "warning" : "success";
}

type GaugeProps = {
	/** What the ring is of, e.g. the category. */
	label: string;
	/** How much of the ceiling is used; may pass 100. */
	percent: number;
	/** How much of the month has passed; drawn as a tick on the ring so use can be read against pace. */
	elapsedPercent?: number;
	/** The exact amounts, as text under the ring. */
	detail: string;
};

/** A progress ring with its status in words: the ring is the picture, the chip and the text are the facts. */
export function Gauge({ label, percent, elapsedPercent, detail }: GaugeProps) {
	const tone = budgetTone(percent);
	const filled = Math.min(100, Math.max(0, percent));
	const centre = SIZE / 2;
	const angle =
		elapsedPercent === undefined
			? null
			: ((Math.min(100, Math.max(0, elapsedPercent)) / 100) * 360 - 90) * (Math.PI / 180);
	const summary = `${t.analytics.budget.summaryPrefix} ${label}: ${formatAmount(percent)}٪ ${t.analytics.budget.used}، ${WORDS[tone]}`;
	return (
		<figure className="flex min-w-0 flex-col items-center gap-2 text-center">
			{/* oxlint-disable-next-line jsx-a11y/prefer-tag-over-role */}
			<div dir="ltr" role="img" aria-label={summary} className="relative size-28">
				<svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="size-full">
					<circle
						cx={centre}
						cy={centre}
						r={RADIUS}
						fill="none"
						stroke="var(--surface-tertiary)"
						strokeWidth={10}
					/>
					{/* Nothing used draws nothing: a round cap on a zero-length arc would still print a dot. */}
					{filled > 0 ? (
						<circle
							cx={centre}
							cy={centre}
							r={RADIUS}
							fill="none"
							stroke={STROKE[tone]}
							strokeWidth={10}
							strokeLinecap="round"
							strokeDasharray={`${(filled / 100) * CIRCUMFERENCE} ${CIRCUMFERENCE}`}
							transform={`rotate(-90 ${centre} ${centre})`}
						/>
					) : null}
					{angle === null ? null : (
						<line
							x1={centre + (RADIUS - 9) * Math.cos(angle)}
							y1={centre + (RADIUS - 9) * Math.sin(angle)}
							x2={centre + (RADIUS + 9) * Math.cos(angle)}
							y2={centre + (RADIUS + 9) * Math.sin(angle)}
							stroke="var(--foreground)"
							strokeWidth={3}
							strokeLinecap="round"
						/>
					)}
				</svg>
				<span
					dir="rtl"
					className="absolute inset-0 flex items-center justify-center text-lg font-bold tabular-nums"
				>
					{formatAmount(percent)}٪
				</span>
			</div>
			<figcaption className="flex min-w-0 flex-col items-center gap-1">
				<span className="max-w-full truncate text-sm font-semibold">{label}</span>
				<StatusChip size="sm" tone={tone} label={WORDS[tone]} />
				<span className="text-xs text-muted">{detail}</span>
			</figcaption>
		</figure>
	);
}
