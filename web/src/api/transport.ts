// Every request goes through apiFetch: bearer token, one renewal on a 401, ApiError on a refusal.
import { t } from "@/strings";
import { accessToken, clearSession } from "./session";

export const REQUEST_TIMEOUT_MS = 20_000;

/** A refused request: FastAPI's `{detail}` (a sentence, or a list of field problems), or status 0 offline. */
export class ApiError extends Error {
	readonly status: number;
	readonly detail: unknown;

	constructor(status: number, message: string, detail?: unknown) {
		super(message);
		this.name = "ApiError";
		this.status = status;
		this.detail = detail;
	}
}

/** What react-query's `error` is for generated hooks. */
export type ErrorType<_Body = unknown> = ApiError;

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

function messageFor(status: number, body: unknown): string {
	const detail = isRecord(body) ? body.detail : undefined;
	// Domain errors are Persian sentences from the service; validation errors are a list we do not read aloud.
	if (typeof detail === "string" && detail) return detail;
	return status === 429 ? "تعداد درخواست‌ها زیاد است؛ کمی بعد دوباره امتحان کن." : t.errors.unknown;
}

async function once(url: string, init: RequestInit, token: string | null): Promise<Response> {
	const headers = new Headers(init.headers);
	if (token) headers.set("Authorization", `Bearer ${token}`);
	if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
		headers.set("Content-Type", "application/json");
	}
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
	try {
		return await fetch(url, { ...init, headers, signal: init.signal ?? controller.signal });
	} catch {
		throw new ApiError(0, t.errors.offline);
	} finally {
		clearTimeout(timer);
	}
}

export async function apiFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
	let response = await once(url, init, await accessToken());
	if (response.status === 401) {
		// The token may have been revoked a moment ago: renew once, and only then give up.
		const fresh = await accessToken(true);
		if (fresh) response = await once(url, init, fresh);
		if (response.status === 401) clearSession();
	}
	const type = response.headers.get("content-type") ?? "";
	const body: unknown =
		response.status === 204
			? undefined
			: /\bjson\b/i.test(type)
				? await response.json()
				: await response.blob();
	if (!response.ok) throw new ApiError(response.status, messageFor(response.status, body), body);
	return body as T;
}
