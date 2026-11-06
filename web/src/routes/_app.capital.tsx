import { createFileRoute, redirect } from "@tanstack/react-router";

// Assets went in with «سرمایه», and funds with the instalments in «برنامه‌ریزی».
export const Route = createFileRoute("/_app/capital")({
	beforeLoad: () => {
		throw redirect({ to: "/portfolio" });
	},
});
