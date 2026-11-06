import type { ComponentType, SVGProps } from "react";
import {
	AccountIcon,
	BookIcon,
	ChartActiveIcon,
	ChartIcon,
	HomeActiveIcon,
	HomeIcon,
	ListActiveIcon,
	ListIcon,
} from "@/shared/icons";
import { t } from "@/strings";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;
export type NavItem = {
	to: string;
	label: string;
	icon: Icon;
	activeIcon?: Icon;
	/** Other pages that belong to this entry: it stays lit on them. */
	also?: string[];
};

const DASHBOARD: NavItem = {
	to: "/",
	label: t.nav.dashboard,
	icon: HomeIcon,
	activeIcon: HomeActiveIcon,
};
const TRANSACTIONS: NavItem = {
	to: "/transactions",
	label: t.nav.transactions,
	icon: ListIcon,
	activeIcon: ListActiveIcon,
};
const REPORTS: NavItem = {
	to: "/reports",
	label: t.nav.reports,
	icon: ChartIcon,
	activeIcon: ChartActiveIcon,
};
// Planning, books, wallet and team are all pages of «مدیریت»: one entry that stays lit on each.
const MANAGE: NavItem = {
	to: "/manage",
	label: t.nav.manage,
	icon: BookIcon,
	also: ["/books", "/wallet", "/team", "/planning", "/capital", "/portfolio"],
};
const ACCOUNT: NavItem = { to: "/account", label: t.nav.account, icon: AccountIcon };

// What a phone keeps one tap away, with the dashboard in the middle: it is home, so it sits where the
// thumb rests and is drawn raised above the rest (see PhoneTabBar).
export const TAB_NAV: NavItem[] = [TRANSACTIONS, REPORTS, DASHBOARD, MANAGE, ACCOUNT];

// Everything, for the sidebar and the quick menu: the same five.
export const SIDE_NAV: NavItem[] = [DASHBOARD, TRANSACTIONS, REPORTS, MANAGE, ACCOUNT];
