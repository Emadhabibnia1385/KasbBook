import { tv } from "tailwind-variants";
import { useBottomBar } from "@nyxon/nasim";
import { t } from "@/strings";
import { NavLink } from "./NavLink";
import { TAB_NAV } from "./nav";

const tabBar = tv({
	slots: {
		root: "z-30 shrink-0 border-t border-separator bg-surface px-safe pb-(--nasim-safe-bottom)",
		list: "mx-auto flex max-w-xl items-stretch justify-around gap-1 px-2",
	},
});

// The bottom bar of a phone and a tablet held upright, clear of the home indicator.
export function PhoneTabBar() {
	const bar = useBottomBar<HTMLElement>();
	const slots = tabBar();
	return (
		<nav ref={bar} aria-label={t.nav.label} className={slots.root()}>
			<ul className={slots.list()}>
				{TAB_NAV.map((item) => (
					<li key={item.to} className="flex flex-1">
						<NavLink item={item} layout="tab" />
					</li>
				))}
			</ul>
		</nav>
	);
}
