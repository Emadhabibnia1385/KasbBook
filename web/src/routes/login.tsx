import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { hasSession } from "@/api/session";
import { LoginScreen } from "@/features/auth/LoginScreen";

type Search = { next?: string | undefined };

export const Route = createFileRoute("/login")({
	validateSearch: (search): Search => ({
		next: typeof search.next === "string" && search.next.startsWith("/") ? search.next : undefined,
	}),
	// Already signed in on this device: nothing to ask.
	beforeLoad: () => {
		if (hasSession()) throw redirect({ to: "/" });
	},
	component: LoginRoute,
});

function LoginRoute() {
	const navigate = useNavigate();
	const { next } = Route.useSearch();
	return <LoginScreen onDone={() => void navigate({ to: next ?? "/", replace: true })} />;
}
