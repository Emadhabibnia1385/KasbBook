import { useQueryClient } from "@tanstack/react-query";
import { tv } from "tailwind-variants";
import { Button, ThemeToggle } from "@nyxon/nasim";
import { useAuthMe } from "@/api/generated/auth/auth";
import { GithubLink } from "@/features/shell/GithubLink";
import { InstallButton } from "@/features/pwa/InstallButton";
import { LogoutIcon } from "@/shared/icons";
import { t } from "@/strings";
import { Brand } from "./Brand";
import { NavLink } from "./NavLink";
import { SIDE_NAV } from "./nav";
import { signOut } from "./signOut";

const sidebar = tv({
	slots: {
		root: "flex w-64 shrink-0 flex-col gap-6 border-e border-separator bg-surface px-3 py-4",
		list: "flex flex-col gap-1",
		account: "mt-auto flex flex-col gap-3 px-2",
	},
});

// The desktop and landscape-tablet navigation (1024px and wider), on the RTL start edge.
export function DesktopSidebar() {
	const { data: me } = useAuthMe();
	const queryClient = useQueryClient();
	const slots = sidebar();
	return (
		<aside aria-label={t.shell.sidebar} className={slots.root()}>
			<div className="flex items-start justify-between gap-2 px-2">
				<Brand full />
				<GithubLink />
			</div>
			<nav aria-label={t.nav.label} className="min-h-0 overflow-y-auto">
				<ul className={slots.list()}>
					{SIDE_NAV.map((item) => (
						<li key={item.to} className="flex">
							<NavLink item={item} layout="side" />
						</li>
					))}
				</ul>
			</nav>
			<div className={slots.account()}>
				<div className="flex justify-center">
					<InstallButton />
				</div>
				<div className="flex items-center justify-between gap-2">
					<ThemeToggle lightLabel={t.theme.light} darkLabel={t.theme.dark} />
					<p className="min-w-0 flex-1 truncate text-center text-sm font-medium">
						{me?.display_name ?? ""}
					</p>
					<Button
						isIconOnly
						variant="ghost"
						aria-label={t.common.logout}
						onPress={() => void signOut(queryClient)}
					>
						<LogoutIcon aria-hidden />
					</Button>
				</div>
			</div>
		</aside>
	);
}
