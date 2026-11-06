import { useAuthMe } from "@/api/generated/auth/auth";
import { t } from "@/strings";

/** A strip above every page while signed in as a guest, so nobody forgets that nothing is being kept. */
export function GuestBar() {
	const me = useAuthMe();
	if (!me.data?.is_guest) return null;
	return (
		<output className="block shrink-0 bg-warning/15 px-page py-1.5 text-center text-xs font-medium text-foreground">
			{me.data.is_demo ? t.acct.demoBar : t.acct.guestBar}
		</output>
	);
}
