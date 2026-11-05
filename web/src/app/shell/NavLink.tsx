import { Link } from "@tanstack/react-router";
import { tv } from "tailwind-variants";
import type { NavItem } from "./nav";

const navLink = tv({
	base: "group relative flex items-center rounded-xl text-muted transition-colors hover:text-foreground focus-visible:-outline-offset-2 data-[status=active]:text-accent-soft-foreground",
	variants: {
		layout: {
			tab: "min-h-14 flex-1 flex-col justify-center gap-0.5 px-1 py-1.5 text-xs font-medium",
			side: "min-h-11 w-full gap-3 px-3 text-sm font-medium data-[status=active]:bg-accent-soft",
		},
	},
});

// The pill behind the active tab's icon.
const pill =
	"grid h-8 w-14 place-items-center rounded-full transition-colors group-data-[status=active]:bg-accent-soft";

export function NavLink({ item, layout }: { item: NavItem; layout: "tab" | "side" }) {
	return (
		<Link to={item.to} activeOptions={{ exact: item.to === "/" }} className={navLink({ layout })}>
			{({ isActive }) => {
				const Icon = (isActive && item.activeIcon) || item.icon;
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
