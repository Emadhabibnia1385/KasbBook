// The Telegram sign-in calls. They are hand-written, not generated, because the polling loop and the
// Mini App shortcut need the raw answer rather than a cached query.
import { apiFetch } from "@/api/transport";

export type LoginTokens = { access_token: string; refresh_token: string; expires_in: number };
type StartResponse = { poll_secret: string; deep_link: string; expires_at: string };
export type PollStatus = "pending" | "approved" | "denied" | "expired";
type PollResponse = { status: PollStatus; tokens: LoginTokens | null };

export const startTelegramLogin = () =>
	apiFetch<StartResponse>("/api/v1/auth/telegram/start", { method: "POST" });

export const pollTelegramLogin = (pollSecret: string) =>
	apiFetch<PollResponse>("/api/v1/auth/telegram/poll", {
		method: "POST",
		body: JSON.stringify({ poll_secret: pollSecret }),
	});

export const loginWithMiniApp = (initData: string) =>
	apiFetch<LoginTokens>("/api/v1/auth/telegram/webapp", {
		method: "POST",
		body: JSON.stringify({ init_data: initData }),
	});
