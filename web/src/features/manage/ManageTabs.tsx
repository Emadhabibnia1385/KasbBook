import { useLocation } from "@tanstack/react-router";
import { NavTabs } from "@nyxon/nasim";
import { useActiveBook } from "@/features/books/useActiveBook";
import { t } from "@/strings";

/**
 * The tabs shared by everything under «مدیریت»: an overview, the books, the wallet and, where there are
 * people to pay, the team. A personal book has none, so it never offers the team.
 */
export function ManageTabs() {
	const { book } = useActiveBook();
	const path = useLocation({ select: (location) => location.pathname.replace(/\/$/, "") || "/" });
	const tab = (href: string, label: string) => ({
		href,
		label,
		isCurrent: path === href || path.startsWith(`${href}/`),
	});
	return (
		<NavTabs
			label={t.manage.label}
			items={[
				tab("/manage", t.manage.overview),
				tab("/wallet", t.manage.wallet),
				tab("/planning", t.nav.planning),
				// A person's own: a team's or a business's books have no holdings, assets or funds.
				...(book && book.type !== "personal"
					? []
					: [tab("/portfolio", t.portfolio.tab), tab("/capital", t.capital.tab)]),
				...(book?.type === "personal" ? [] : [tab("/team", t.manage.team)]),
				tab("/books", t.manage.books),
			]}
		/>
	);
}
