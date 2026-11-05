import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, ConfirmDialog, KeyValueList, PageHeader, PageSkeleton, SectionCard, ThemeToggle } from "@nyxon/nasim";
import { authLogoutEverywhere, useAuthMe, useAuthSessions } from "@/api/generated/auth/auth";
import { useIdentitiesListIdentities } from "@/api/generated/identities/identities";
import { clearSession } from "@/api/session";
import { InstallButton } from "@/features/pwa/InstallButton";
import { formatFullDate } from "@/shared/format";
import { t } from "@/strings";

const PROVIDERS: Record<string, string> = { telegram: "تلگرام", bale: "بله", rubika: "روبیکا", eitaa: "ایتا", web: "وب" };

export function Account() {
	const queryClient = useQueryClient();
	const me = useAuthMe();
	const sessions = useAuthSessions();
	const identities = useIdentitiesListIdentities();
	const [confirming, setConfirming] = useState(false);
	if (me.isLoading) return <PageSkeleton />;
	const user = me.data;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.account} description={user?.display_name} />
			<div className="grid gap-5 lg:grid-cols-2">
				<SectionCard title={t.account.profile}>
					<KeyValueList
						items={[
							{ label: t.account.name, value: user?.display_name ?? "—" },
							{ label: t.account.timezone, value: user?.timezone ?? "—" },
							{ label: t.account.email, value: user?.email ?? "—" },
						]}
					/>
				</SectionCard>
				<SectionCard title={t.account.messengers}>
					<ul className="flex flex-col gap-2">
						{(identities.data ?? []).map((identity) => (
							<li key={identity.id} className="flex items-center justify-between rounded-xl border border-border p-3">
								<span className="font-medium">{PROVIDERS[identity.provider] ?? identity.provider}</span>
								<span dir="ltr" className="text-sm text-muted">
									{identity.external_username ? `@${identity.external_username}` : identity.external_id}
								</span>
							</li>
						))}
					</ul>
				</SectionCard>
				<SectionCard title={t.account.sessions}>
					<ul className="flex flex-col gap-2">
						{(sessions.data ?? []).map((session) => (
							<li key={session.id} className="flex flex-col gap-1 rounded-xl border border-border p-3 text-sm">
								<span className="truncate" dir="ltr">
									{session.user_agent ?? "—"}
								</span>
								<span className="text-muted">
									{t.account.since} {formatFullDate(session.created_at.slice(0, 10))}
								</span>
							</li>
						))}
					</ul>
					<Button variant="danger-soft" className="mt-3" onPress={() => setConfirming(true)}>
						{t.account.logoutEverywhere}
					</Button>
				</SectionCard>
				<SectionCard title={t.account.appearance}>
					<div className="flex flex-col items-start gap-3">
						<ThemeToggle lightLabel={t.theme.light} darkLabel={t.theme.dark} />
						<InstallButton />
					</div>
				</SectionCard>
			</div>
			<ConfirmDialog
				isOpen={confirming}
				onOpenChange={setConfirming}
				title={t.account.logoutEverywhere}
				description={t.account.logoutEverywhereBody}
				confirmLabel={t.account.logoutEverywhere}
				tone="danger"
				onConfirm={async () => {
					await authLogoutEverywhere();
					clearSession();
					queryClient.clear();
				}}
			/>
		</div>
	);
}
