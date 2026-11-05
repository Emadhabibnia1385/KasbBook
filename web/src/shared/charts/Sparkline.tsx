type SparklineProps = {
	/** Oldest first; a gap is a month with nothing to say and is skipped. */
	values: readonly (number | null)[];
	color: string;
	/** What it shows, in words: the line alone says nothing to a screen reader. */
	label: string;
};

const WIDTH = 100;
const HEIGHT = 32;
const PAD = 3;

/** A line with no axes, for a card: the trend's shape, nothing else. The card's text carries the figure. */
export function Sparkline({ values, color, label }: SparklineProps) {
	const present = values
		.map((value, index) => ({ value, index }))
		.filter((point): point is { value: number; index: number } => point.value !== null);
	if (present.length < 2) return null;
	const low = Math.min(...present.map((point) => point.value));
	const high = Math.max(...present.map((point) => point.value));
	const x = (index: number) => (index / (values.length - 1)) * WIDTH;
	// A flat series sits in the middle rather than on the floor, which would read as «zero».
	const y = (value: number) =>
		high === low ? HEIGHT / 2 : PAD + (1 - (value - low) / (high - low)) * (HEIGHT - 2 * PAD);
	const line = present
		.map(
			(point, order) =>
				`${order === 0 ? "M" : "L"}${x(point.index).toFixed(2)} ${y(point.value).toFixed(2)}`,
		)
		.join(" ");
	const first = present[0];
	const last = present[present.length - 1];
	const area =
		first && last
			? `${line} L${x(last.index).toFixed(2)} ${HEIGHT} L${x(first.index).toFixed(2)} ${HEIGHT} Z`
			: "";
	return (
		<div dir="ltr">
			<svg
				// oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
				role="img"
				aria-label={label}
				viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
				preserveAspectRatio="none"
				className="block h-8 w-full"
			>
				<path d={area} fill={color} fillOpacity={0.14} />
				<path
					d={line}
					fill="none"
					stroke={color}
					strokeWidth={2}
					strokeLinejoin="round"
					strokeLinecap="round"
					vectorEffect="non-scaling-stroke"
				/>
			</svg>
		</div>
	);
}
