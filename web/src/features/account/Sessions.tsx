import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, ConfirmDialog, toast } from "@nyxon/nasim";
import {
	authLogoutEverywhere,
	useAuthMe,
	authSignOutSession,
	getAuthSessionsQueryKey,
	useAuthSessions,
} from "@/api/generated/auth/auth";
import { clearSession } from "@/api/session";
import { formatStamp } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { describeAgent } from "./userAgent";

/** Where the account is signed in: the browser's name, when, and a way out for each. */
export function Sessions() {
	const queryClient = useQueryClient();
	const sessions = useAuthSessions();
	const zone = useAuthMe().data?.timezone;
	const [confirming, setConfirming] = useState(false);
	const [busy, setBusy] = useState<string | null>(null);

	const signOutOne = async (id: string) => {
		setBusy(id);
		try {
			await authSignOutSession(id);
			await queryClient.invalidateQueries({ queryKey: getAuthSessionsQueryKey() });
			toast.success(t.acct.signedOut);
		} catch (error) {
			reportFailure(error);
		} finally {
			setBusy(null);
		}
	};

	return (
		<div className="flex flex-col gap-3">
			<ul className="flex flex-col gap-2">
				{(sessions.data ?? []).map((session) => (
					<li
						key={session.id}
						className="flex items-center justify-between gap-3 rounded-xl border border-border p-3"
					>
						<span className="flex min-w-0 flex-col">
							<span dir="ltr" className="truncate text-start font-medium">
								{describeAgent(session.user_agent, t.acct.unknownBrowser)}
							</span>
							<span className="text-sm text-muted">
								{t.acct.lastActive}: <bdi dir="ltr">{formatStamp(session.created_at, zone)}</bdi>
							</span>
						</span>
						<Button
							size="sm"
							variant="danger-soft"
							isPending={busy === session.id}
							onPress={() => void signOutOne(session.id)}
						>
							{t.acct.signOutOne}
						</Button>
					</li>
				))}
			</ul>
			<Button variant="danger-soft" className="self-start" onPress={() => setConfirming(true)}>
				{t.account.logoutEverywhere}
			</Button>
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
