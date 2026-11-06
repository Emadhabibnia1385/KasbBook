import { Link, useLocation } from "@tanstack/react-router";
import { tv } from "tailwind-variants";
import type { NavItem } from "./nav";

const navLink = tv({
	base: "group relative flex items-center rounded-xl text-muted transition-colors hover:text-foreground focus-visible:-outline-offset-2 data-[active]:text-accent-soft-foreground",
	variants: {
		layout: {
			tab: "min-h-14 flex-1 flex-col justify-center gap-0.5 px-1 py-1.5 text-xs font-medium",
			// The raised middle tab: its circle rises above the bar, so the label sits under it.
			center:
				"min-h-14 flex-1 flex-col justify-end gap-0.5 px-1 pb-1.5 text-xs font-semibold text-foreground",
			side: "min-h-11 w-full gap-3 px-3 text-sm font-medium data-[active]:bg-accent-soft",
		},
	},
});

// The middle tab's circle: lifted out of the bar, ringed in the page colour so it reads as cut into it.
const raised = tv({
	base: "-mt-7 grid size-14 place-items-center rounded-full bg-accent text-accent-foreground shadow-lg ring-4 ring-background transition-transform",
	variants: { active: { true: "scale-110 shadow-accent/40", false: "" } },
});

// The pill behind the active tab's icon.
const pill =
	"grid h-8 w-14 place-items-center rounded-full transition-colors group-data-[active]:bg-accent-soft";

/** Whether the page on screen is this entry's own or one of the pages that belong to it. */
function isCurrent(item: NavItem, path: string): boolean {
	if (item.to === "/") return path === "/";
	return [item.to, ...(item.also ?? [])].some(
		(base) => path === base || path.startsWith(`${base}/`),
	);
}

export function NavLink({ item, layout }: { item: NavItem; layout: "tab" | "side" | "center" }) {
	const path = useLocation({ select: (location) => location.pathname.replace(/\/$/, "") || "/" });
	const active = isCurrent(item, path);
	return (
		<Link
			to={item.to}
			activeOptions={{ exact: item.to === "/" }}
			className={navLink({ layout })}
			data-active={active ? "" : undefined}
		>
			{() => {
				const isActive = active;
				const Icon = (isActive && item.activeIcon) || item.icon;
				if (layout === "center") {
					return (
						<>
							<span className={raised({ active: isActive })}>
								<Icon aria-hidden className="size-7" />
							</span>
							<span className={isActive ? "text-accent-soft-foreground" : "text-muted"}>
								{item.label}
							</span>
						</>
					);
				}
				return (
					<>
						{layout === "tab" ? (
							<span className={pill}>
								<Icon aria-hidden className="size-6" />
							</span>
						) : (
							<Icon aria-hidden className="size-6" />
						)}
						<span>{item.label}</span>
					</>
				);
			}}
		</Link>
	);
}
