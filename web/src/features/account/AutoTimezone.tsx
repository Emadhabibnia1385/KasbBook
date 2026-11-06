import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { getAuthMeQueryKey, useAuthMe, useAuthUpdateProfile } from "@/api/generated/auth/auth";
import { ZONE_KEY } from "./ProfileForm";
import { browserZone } from "./timezones";

// What a new account starts with. Only this is replaced by the browser's guess; a zone chosen on purpose is kept.
const DEFAULT_ZONE = "Asia/Tehran";

/** Takes the time zone from the browser once, for an account that still has the starting one. Renders nothing. */
export function AutoTimezone() {
	const queryClient = useQueryClient();
	const me = useAuthMe();
	const update = useAuthUpdateProfile();
	const user = me.data;
	useEffect(() => {
		if (!user || user.timezone !== DEFAULT_ZONE) return;
		let seen: string | null = null;
		try {
			seen = localStorage.getItem(ZONE_KEY);
		} catch {
			return;
		}
		if (seen) return;
		const zone = browserZone();
		try {
			localStorage.setItem(ZONE_KEY, "auto");
		} catch {
			return;
		}
		if (!zone || zone === DEFAULT_ZONE) return;
		update
			.mutateAsync({ data: { timezone: zone } })
			.then((saved) => queryClient.setQueryData(getAuthMeQueryKey(), saved))
			.catch(() => undefined);
	}, [user, update, queryClient]);
	return null;
}
