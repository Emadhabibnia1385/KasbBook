import { Outlet, useLocation } from "@tanstack/react-router";
import { NavTabs } from "@nyxon/nasim";
import { useActiveBook } from "@/features/books/useActiveBook";
import { t } from "@/strings";
import { isPayrollBook } from "./shared";

// «تیم و حقوق» is one menu entry with sibling pages: members for every book, payroll where profit is shared.
export function TeamLayout() {
	const { book } = useActiveBook();
	const path = useLocation({ select: (location) => location.pathname.replace(/\/$/, "") });
	const payroll = book !== undefined && isPayrollBook(book);
	const tab = (href: string, label: string) => ({
		href,
		label,
		isCurrent: href === "/team" ? path === href : path === href || path.startsWith(`${href}/`),
	});
	return (
		<div className="flex flex-col gap-5">
			<NavTabs
				label={t.payroll.tabs.label}
				items={[
					tab("/team", t.payroll.tabs.members),
					...(payroll
						? [
								tab("/team/shares", t.payroll.tabs.shares),
								tab("/team/periods", t.payroll.tabs.periods),
								tab("/team/funds", t.payroll.tabs.funds),
							]
						: []),
				]}
			/>
			<Outlet />
		</div>
	);
}
