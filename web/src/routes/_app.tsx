import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { hasSession, onSessionChange } from "@/api/session";
import { AppShell } from "@/app/shell/AppShell";
import { Outlet } from "@tanstack/react-router";

// The pathless layout every signed-in screen lives in: the gate, then the shell.
export const Route = createFileRoute("/_app")({
	beforeLoad: ({ location }) => {
		if (!hasSession()) throw redirect({ to: "/login", search: { next: location.pathname } });
	},
	component: AppLayout,
});

function AppLayout() {
	const navigate = useNavigate();
	// Signed out here (server refused the session) or in another tab: back to the door.
	useEffect(
		() =>
			onSessionChange(() => {
				if (!hasSession()) void navigate({ to: "/login", search: { next: undefined } });
			}),
		[navigate],
	);
	return (
		<AppShell>
			<Outlet />
		</AppShell>
	);
}
