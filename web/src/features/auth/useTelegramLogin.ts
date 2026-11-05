import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { saveSession } from "@/api/session";
import { t } from "@/strings";
import { loginWithMiniApp, pollTelegramLogin, startTelegramLogin } from "./api";
import { miniAppInitData } from "./miniApp";

const POLL_MS = 2000;
// The same page reload should not lose a login in progress.
const PENDING_KEY = "kasbbook.pending-login";

type Pending = { pollSecret: string; deepLink: string; expiresAt: number };
export type LoginState =
	| { phase: "idle" }
	| { phase: "starting" }
	| { phase: "waiting"; deepLink: string }
	| { phase: "failed"; message: string };

function readPending(): Pending | null {
	try {
		const raw = sessionStorage.getItem(PENDING_KEY);
		const pending = raw ? (JSON.parse(raw) as Pending) : null;
		return pending && pending.expiresAt > Date.now() ? pending : null;
	} catch {
		return null;
	}
}

function writePending(pending: Pending | null) {
	try {
		if (pending) sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending));
		else sessionStorage.removeItem(PENDING_KEY);
	} catch {
		// a reload during sign-in just starts again
	}
}

/** Sign in through the bot: ask for a link, wait for the person to approve it, keep the session. */
export function useTelegramLogin(onDone: () => void) {
	const [state, setState] = useState<LoginState>({ phase: "idle" });
	const queryClient = useQueryClient();
	const alive = useRef(true);
	const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

	useEffect(() => {
		alive.current = true;
		return () => {
			alive.current = false;
			clearTimeout(timer.current);
		};
	}, []);

	const finish = (tokens: Parameters<typeof saveSession>[0]) => {
		writePending(null);
		saveSession(tokens);
		queryClient.clear();
		onDone();
	};

	const fail = (message: string) => {
		writePending(null);
		if (alive.current) setState({ phase: "failed", message });
	};

	const poll = (pending: Pending) => {
		timer.current = setTimeout(async () => {
			if (!alive.current) return;
			try {
				const answer = await pollTelegramLogin(pending.pollSecret);
				if (!alive.current) return;
				if (answer.status === "approved" && answer.tokens) return finish(answer.tokens);
				if (answer.status === "denied") return fail(t.login.denied);
				if (answer.status === "expired") return fail(t.login.expired);
			} catch {
				// a dropped request is not a refusal: ask again until the link's own deadline
			}
			if (Date.now() > pending.expiresAt) return fail(t.login.expired);
			poll(pending);
		}, POLL_MS);
	};

	const begin = async () => {
		clearTimeout(timer.current);
		setState({ phase: "starting" });
		try {
			const issued = await startTelegramLogin();
			const pending = {
				pollSecret: issued.poll_secret,
				deepLink: issued.deep_link,
				expiresAt: Date.parse(issued.expires_at),
			};
			writePending(pending);
			setState({ phase: "waiting", deepLink: pending.deepLink });
			poll(pending);
			return pending.deepLink;
		} catch (error) {
			fail(error instanceof Error && error.message ? error.message : t.login.failed);
			return null;
		}
	};

	const cancel = () => {
		clearTimeout(timer.current);
		writePending(null);
		setState({ phase: "idle" });
	};

	// Resume a login that was waiting when the page reloaded, or sign in at once from inside Telegram.
	useEffect(() => {
		const initData = miniAppInitData();
		if (initData) {
			setState({ phase: "starting" });
			loginWithMiniApp(initData).then(finish, () => fail(t.login.failed));
			return;
		}
		const pending = readPending();
		if (pending) {
			setState({ phase: "waiting", deepLink: pending.deepLink });
			poll(pending);
		}
		// runs once on mount
		// oxlint-disable-next-line react/exhaustive-deps
	}, []);

	return { state, begin, cancel };
}
