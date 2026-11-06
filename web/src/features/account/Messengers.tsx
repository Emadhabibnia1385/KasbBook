import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button, toast } from "@nyxon/nasim";
import {
	getIdentitiesListIdentitiesQueryKey,
	identitiesListIdentities,
	useIdentitiesListIdentities,
	useIdentitiesStartLink,
} from "@/api/generated/identities/identities";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const PROVIDERS = [
	{ id: "telegram", label: "تلگرام" },
	{ id: "bale", label: "بله" },
	{ id: "rubika", label: "روبیکا" },
] as const;

// After the bot is opened, the list is read again every few seconds until the new messenger shows up.
const POLL_MS = 3000;
const GIVE_UP_MS = 3 * 60_000;

/** Every messenger that can be linked: the ones already linked, and a button for each that is not. */
export function Messengers() {
	const queryClient = useQueryClient();
	const identities = useIdentitiesListIdentities();
	const start = useIdentitiesStartLink();
	const [waiting, setWaiting] = useState<string | null>(null);
	const linked = identities.data ?? [];

	useEffect(() => {
		if (!waiting) return;
		const timer = setInterval(async () => {
			try {
				const rows = await identitiesListIdentities();
				queryClient.setQueryData(getIdentitiesListIdentitiesQueryKey(), rows);
				if (rows.some((row) => row.provider === waiting)) {
					setWaiting(null);
					toast.success(t.acct.linked);
				}
			} catch {
				// the next round tries again
			}
		}, POLL_MS);
		const stop = setTimeout(() => setWaiting(null), GIVE_UP_MS);
		return () => {
			clearInterval(timer);
			clearTimeout(stop);
		};
	}, [waiting, queryClient]);

	const connect = async (provider: string) => {
		try {
			const made = await start.mutateAsync({ data: { provider } });
			if (!made.deep_link) {
				toast.danger(t.acct.notAvailable);
				return;
			}
			window.open(made.deep_link, "_blank", "noopener");
			setWaiting(provider);
		} catch (error) {
			reportFailure(error);
		}
	};

	return (
		<div className="flex flex-col gap-3">
			<p className="text-sm text-muted">{t.acct.messengersLead}</p>
			<ul className="flex flex-col gap-2">
				{PROVIDERS.map(({ id, label }) => {
					const identity = linked.find((entry) => entry.provider === id);
					return (
						<li
							key={id}
							className="flex items-center justify-between gap-3 rounded-xl border border-border p-3"
						>
							<span className="flex flex-col">
								<span className="font-medium">{label}</span>
								{identity ? (
									<span dir="ltr" className="text-start text-sm text-muted">
										{identity.external_username
											? `@${identity.external_username}`
											: identity.external_id}
									</span>
								) : waiting === id ? (
									<span className="text-sm text-muted">{t.acct.waiting}</span>
								) : null}
							</span>
							{identity ? (
								<span className="text-sm font-medium text-success">{t.acct.connected}</span>
							) : (
								<Button
									size="sm"
									variant="secondary"
									isPending={start.isPending && waiting !== id}
									onPress={() => void connect(id)}
								>
									{t.acct.connect}
								</Button>
							)}
						</li>
					);
				})}
			</ul>
		</div>
	);
}
