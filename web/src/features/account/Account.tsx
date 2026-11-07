import { useQueryClient } from "@tanstack/react-query";
import { Button, Notice, PageHeader, PageSkeleton, SectionCard, Tabs } from "@nyxon/nasim";
import { useAuthMe } from "@/api/generated/auth/auth";
import { signOut } from "@/app/shell/signOut";
import { InstallButton } from "@/features/pwa/InstallButton";
import { useInstallState } from "@/features/pwa/install";
import { LogoutIcon } from "@/shared/icons";
import { t } from "@/strings";
import { ActivityTab } from "./ActivityTab";
import { ApiTab } from "./ApiTab";
import { Customize } from "./Customize";
import { DigestForm } from "./DigestForm";
import { LoginDetails } from "./LoginDetails";
import { Messengers } from "./Messengers";
import { ProfileForm } from "./ProfileForm";
import { Sessions } from "./Sessions";

/** Putting the app on the home screen: why, how, and the button where the browser allows one. */
function InstallCard() {
	const state = useInstallState();
	return (
		<SectionCard title={t.acct.installTitle}>
			<div className="flex flex-col items-start gap-3">
				<p className="text-sm text-muted">{t.acct.installLead}</p>
				{state === "installed" ? <p className="text-sm font-medium">{t.acct.installDone}</p> : null}
				{state === "none" ? <p className="text-sm text-muted">{t.acct.installNone}</p> : null}
				<InstallButton />
			</div>
		</SectionCard>
	);
}

export function Account() {
	const queryClient = useQueryClient();
	const me = useAuthMe();
	if (me.isLoading) return <PageSkeleton />;
	const user = me.data;
	const guest = user?.is_guest === true;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.account} description={user?.display_name} />
			<Tabs
				label={t.nav.account}
				defaultSelectedKey="profile"
				items={[
					{
						id: "profile",
						label: t.acct.tabProfile,
						content: (
							<div className="grid gap-5 pt-4 lg:grid-cols-2">
								{guest ? (
									<div className="lg:col-span-2">
										<Notice
											tone="warning"
											title={user?.is_demo ? t.acct.demoTitle : t.acct.guestTitle}
										>
											{user?.is_demo ? t.acct.demoBody : t.acct.guestBody}
										</Notice>
									</div>
								) : null}
								{user ? (
									<SectionCard title={t.acct.profile}>
										<ProfileForm key={`${user.display_name}-${user.timezone}`} user={user} />
									</SectionCard>
								) : null}
								{user && !guest ? (
									<SectionCard title={t.acct.loginTitle}>
										<LoginDetails key={`${user.username}-${user.web_login_ready}`} user={user} />
									</SectionCard>
								) : null}
								{user ? (
									<SectionCard title={t.digest.title}>
										<DigestForm
											key={`${user.digest_enabled}-${user.digest_hour}-${user.reminder_days}`}
											user={user}
										/>
									</SectionCard>
								) : null}
								{guest ? null : (
									<SectionCard title={t.acct.messengers}>
										<Messengers />
									</SectionCard>
								)}
								<SectionCard title={t.acct.sessions}>
									<Sessions />
								</SectionCard>
								<InstallCard />
								<SectionCard title={t.acct.signOutTitle}>
									<div className="flex flex-col items-start gap-3">
										<p className="text-sm text-muted">
											{user?.is_demo
												? t.acct.signOutDemo
												: guest
													? t.acct.signOutGuest
													: t.acct.signOutLead}
										</p>
										<Button variant="outline" onPress={() => void signOut(queryClient)}>
											<LogoutIcon aria-hidden />
											{t.common.logout}
										</Button>
									</div>
								</SectionCard>
							</div>
						),
					},
					{
						id: "api",
						label: t.acct.tabApi,
						content: (
							<div className="pt-4">
								<ApiTab />
							</div>
						),
					},
					{
						id: "events",
						label: t.events.tab,
						content: (
							<div className="pt-4">
								<ActivityTab />
							</div>
						),
					},
					{
						id: "custom",
						label: t.acct.tabCustom,
						content: (
							<div className="pt-4">
								<Customize />
							</div>
						),
					},
				]}
			/>
		</div>
	);
}
