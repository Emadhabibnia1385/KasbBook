import { createFileRoute, redirect } from "@tanstack/react-router";

// Repeating transactions live inside the transactions page now; an old link lands there.
export const Route = createFileRoute("/_app/recurring")({
	beforeLoad: () => {
		throw redirect({ to: "/transactions" });
	},
});
