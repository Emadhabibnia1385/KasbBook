// Chart colours are Nasim's tokens, never a hex: they follow the theme (light, dark, a tenant's accent)
// without a `dark:` branch, and a chart repaints with the page.
export const color = {
	income: "var(--success)",
	expense: "var(--danger)",
	net: "var(--accent)",
	previous: "var(--muted)",
	warning: "var(--warning)",
	axis: "var(--muted)",
	grid: "var(--separator)",
	surface: "var(--surface)",
} as const;

// Six hues that stay apart from each other; the legend always names them, so colour is never the only cue.
export const CATEGORY_COLORS = [
	"var(--accent)",
	"var(--success)",
	"var(--warning)",
	"var(--danger)",
	"color-mix(in oklab, var(--accent) 50%, var(--danger))",
	"color-mix(in oklab, var(--success) 50%, var(--info))",
] as const;

export const OTHER_COLOR = "var(--muted)";

/** The colour of the nth slice; the one after the palette is «سایر». */
export function categoryColor(index: number): string {
	return CATEGORY_COLORS[index] ?? OTHER_COLOR;
}
