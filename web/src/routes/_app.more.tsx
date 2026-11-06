import { createFileRoute, redirect } from "@tanstack/react-router";

// The phone no longer has a «بیشتر» page: what it held is in the bar, in «مدیریت» and in the account.
export const Route = createFileRoute("/_app/more")({
	beforeLoad: () => {
		throw redirect({ to: "/account" });
	},
});
