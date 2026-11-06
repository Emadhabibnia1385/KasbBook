import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button, PageHeader } from "@nyxon/nasim";
import { SIDE_NAV } from "@/app/shell/nav";
import { signOut } from "@/app/shell/signOut";
import { GithubStar } from "@/features/shell/GithubStar";
import { InstallButton } from "@/features/pwa/InstallButton";
import { LogoutIcon } from "@/shared/icons";
import { t } from "@/strings";

export const Route = createFileRoute("/_app/more")({ component: More });

// The phone's door to everything the bottom bar has no room for.
function More() {
	const queryClient = useQueryClient();
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.more} />
			<ul className="flex flex-col overflow-hidden rounded-2xl border border-border bg-surface">
				{SIDE_NAV.slice(4).map((item) => (
					<li key={item.to} className="border-b border-separator last:border-b-0">
						<Link to={item.to} className="flex min-h-14 items-center gap-3 px-4">
							<item.icon aria-hidden className="size-6 text-muted" />
							{item.label}
						</Link>
					</li>
				))}
			</ul>
			<InstallButton />
			<div className="flex justify-center">
				<GithubStar />
			</div>
			<Button variant="outline" onPress={() => void signOut(queryClient)}>
				<LogoutIcon aria-hidden />
				{t.common.logout}
			</Button>
		</div>
	);
}
