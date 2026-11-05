import type { ReactNode } from "react";
import { tv } from "tailwind-variants";

const card = tv({
	slots: {
		root: "flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4",
		head: "flex flex-wrap items-center justify-between gap-x-3 gap-y-2",
		title: "min-w-0 font-medium",
		actions: "flex flex-wrap gap-2",
	},
	variants: {
		tone: {
			plain: {},
			warning: { root: "border-warning" },
			danger: { root: "border-danger" },
		},
	},
	defaultVariants: { tone: "plain" },
});

/** One record of a list (a member, a fund, a payslip): a title, something at its far end, a body, buttons. */
export function ItemCard({
	title,
	aside,
	tone,
	actions,
	children,
}: {
	title: ReactNode;
	aside?: ReactNode;
	tone?: "plain" | "warning" | "danger";
	actions?: ReactNode;
	children?: ReactNode;
}) {
	const slots = card({ tone });
	return (
		<li className={slots.root()}>
			<div className={slots.head()}>
				<span className={slots.title()}>{title}</span>
				{aside}
			</div>
			{children}
			{actions ? <div className={slots.actions()}>{actions}</div> : null}
		</li>
	);
}

const figure = tv({
	base: "tabular-nums",
	variants: { tone: { plain: "", good: "text-success", bad: "text-danger", muted: "text-muted" } },
	defaultVariants: { tone: "plain" },
});

/** A figure that keeps its digits aligned and takes its colour from what it means. */
export function Figure({
	tone,
	children,
}: {
	tone?: "plain" | "good" | "bad" | "muted";
	children: ReactNode;
}) {
	return <span className={figure({ tone })}>{children}</span>;
}
