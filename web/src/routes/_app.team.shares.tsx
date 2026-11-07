import { createFileRoute, redirect } from "@tanstack/react-router";

// Members and their shares are one page now; an old link or bookmark lands there.
export const Route = createFileRoute("/_app/team/shares")({
	beforeLoad: () => {
		throw redirect({ to: "/team", replace: true });
	},
});
