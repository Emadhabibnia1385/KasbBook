import { Outlet, useLocation } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { EmptyState, NavTabs } from "@nyxon/nasim";
import { useActiveBook } from "@/features/books/useActiveBook";
import { ManageTabs } from "@/features/manage/ManageTabs";
import { t } from "@/strings";
import { isPayrollBook } from "./shared";

// «تیم و حقوق» is one menu entry with sibling pages: members for every book, payroll where profit is shared.
export function TeamLayout() {
	const { book } = useActiveBook();
	const path = useLocation({ select: (location) => location.pathname.replace(/\/$/, "") });
	const payroll = book !== undefined && isPayrollBook(book);
	// A personal book has no colleagues and no payroll, so there is nothing here to manage.
	if (book?.type === "personal") {
		return (
			<div className="flex flex-col gap-5">
				<ManageTabs />
				<EmptyState title={t.manage.personalTitle} description={t.manage.personalBody} />
				<Link to="/books" className="text-center text-sm text-accent">
					{t.manage.goBooks}
				</Link>
			</div>
		);
	}
	const tab = (href: string, label: string) => ({
		href,
		label,
		isCurrent: href === "/team" ? path === href : path === href || path.startsWith(`${href}/`),
	});
	return (
		<div className="flex flex-col gap-5">
			<ManageTabs />
			<NavTabs
				quiet
				scrollable
				label={t.payroll.tabs.label}
				items={[
					tab("/team", t.payroll.tabs.members),
					...(payroll
						? [
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
