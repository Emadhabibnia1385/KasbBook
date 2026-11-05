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
	TeamIcon,
} from "@/shared/icons";
import { t } from "@/strings";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;
export type NavItem = { to: string; label: string; icon: Icon; activeIcon?: Icon };

// What a phone keeps one tap away: the four things done daily, and a door to the rest.
export const TAB_NAV: NavItem[] = [
	{ to: "/", label: t.nav.dashboard, icon: HomeIcon, activeIcon: HomeActiveIcon },
	{ to: "/transactions", label: t.nav.transactions, icon: ListIcon, activeIcon: ListActiveIcon },
	{ to: "/reports", label: t.nav.reports, icon: ChartIcon, activeIcon: ChartActiveIcon },
	{ to: "/planning", label: t.nav.planning, icon: PlanIcon },
	{ to: "/more", label: t.nav.more, icon: MoreIcon },
];

// Everything, for the sidebar and the «بیشتر» page; the first four are the phone's tabs.
export const SIDE_NAV: NavItem[] = [
	...TAB_NAV.slice(0, 4),
	{ to: "/team", label: t.nav.team, icon: TeamIcon },
	{ to: "/books", label: t.nav.books, icon: BookIcon },
	{ to: "/account", label: t.nav.account, icon: AccountIcon },
];
