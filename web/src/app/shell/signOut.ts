import type { QueryClient } from "@tanstack/react-query";
import { authLogout } from "@/api/generated/auth/auth";
import { clearSession, refreshToken } from "@/api/session";

/** Ends this device's session on the server, then forgets it here whatever the server said. */
export async function signOut(queryClient: QueryClient) {
	try {
		const token = refreshToken();
		if (token) await authLogout({ refresh_token: token });
	} catch {
		// offline: the token expires on its own, and this device must still be signed out
	}
	clearSession();
	queryClient.clear();
}
