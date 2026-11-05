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
	MoreIcon,
	PlanIcon,
	RepeatIcon,
	TeamIcon,
	WalletIcon,
} from "@/shared/icons";
import { t } from "@/strings";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;
export type NavItem = { to: string; label: string; icon: Icon; activeIcon?: Icon };

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
const PLANNING: NavItem = { to: "/planning", label: t.nav.planning, icon: PlanIcon };

// What a phone keeps one tap away, with the dashboard in the middle: it is home, so it sits where the
// thumb rests and is drawn raised above the rest (see PhoneTabBar).
export const TAB_NAV: NavItem[] = [
	TRANSACTIONS,
	REPORTS,
	DASHBOARD,
	PLANNING,
	{ to: "/more", label: t.nav.more, icon: MoreIcon },
];

// Everything, for the sidebar and the «بیشتر» page. The first four are the daily ones, home first;
// the «بیشتر» page lists what comes after them.
export const SIDE_NAV: NavItem[] = [
	DASHBOARD,
	TRANSACTIONS,
	REPORTS,
	PLANNING,
	{ to: "/team", label: t.nav.team, icon: TeamIcon },
	{ to: "/books", label: t.nav.books, icon: BookIcon },
	{ to: "/wallet", label: t.nav3.wallet, icon: WalletIcon },
	{ to: "/recurring", label: t.nav3.recurring, icon: RepeatIcon },
	{ to: "/account", label: t.nav.account, icon: AccountIcon },
];
