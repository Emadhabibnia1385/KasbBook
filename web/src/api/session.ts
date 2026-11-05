// The saved sign-in. The refresh token is what keeps a person signed in across visits: the server
// rotates it on every use and slides its expiry, so a device in regular use never asks again.
const KEY = "kasbbook.session";

type Stored = { access: string; refresh: string; expiresAt: number };
type Pair = { access_token: string; refresh_token: string; expires_in: number };

// A token this close to its end is treated as ended, so a request never leaves with one that dies in flight.
const SKEW_MS = 15_000;

function read(): Stored | null {
	try {
		const raw = localStorage.getItem(KEY);
		return raw ? (JSON.parse(raw) as Stored) : null;
	} catch {
		return null;
	}
}

export function saveSession(pair: Pair) {
	const value: Stored = {
		access: pair.access_token,
		refresh: pair.refresh_token,
		expiresAt: Date.now() + pair.expires_in * 1000,
	};
	try {
		localStorage.setItem(KEY, JSON.stringify(value));
	} catch {
		// storage blocked: the session lasts until the tab closes, which is all we can offer
		memory = value;
	}
	listeners.forEach((listener) => listener());
}

let memory: Stored | null = null;
const listeners = new Set<() => void>();

const current = () => read() ?? memory;

export const refreshToken = (): string | null => current()?.refresh ?? null;

export function hasSession(): boolean {
	return current() !== null;
}

export function clearSession() {
	memory = null;
	try {
		localStorage.removeItem(KEY);
	} catch {
		// nothing to remove
	}
	listeners.forEach((listener) => listener());
}

/** Tell the shell when the session appears or disappears, in this tab or another. */
export function onSessionChange(listener: () => void): () => void {
	listeners.add(listener);
	const onStorage = (event: StorageEvent) => {
		if (event.key === KEY) listener();
	};
	window.addEventListener("storage", onStorage);
	return () => {
		listeners.delete(listener);
		window.removeEventListener("storage", onStorage);
	};
}

let renewing: Promise<string | null> | null = null;

async function renew(): Promise<string | null> {
	const before = current();
	if (!before) return null;
	const response = await fetch("/api/v1/auth/refresh", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ refresh_token: before.refresh }),
	});
	if (response.ok) {
		const pair = (await response.json()) as Pair;
		saveSession(pair);
		return pair.access_token;
	}
	// The server refused the token: it was revoked, spent or has aged out. Only then is the person signed out;
	// a dropped connection throws before here and leaves the session alone.
	if (response.status === 401 || response.status === 422) clearSession();
	return null;
}

/**
 * A usable access token, renewed if it is about to end. A rotating refresh token may be spent once,
 * so tabs take a lock: the second tab finds the first tab's fresh pair instead of replaying a spent one.
 */
export async function accessToken(force = false): Promise<string | null> {
	const stored = current();
	if (!stored) return null;
	if (!force && stored.expiresAt - Date.now() > SKEW_MS) return stored.access;
	renewing ??= (async () => {
		try {
			const run = async () => {
				const latest = current();
				// Another tab already renewed while this one waited for the lock.
				if (latest && !force && latest.expiresAt - Date.now() > SKEW_MS) return latest.access;
				if (latest && force && latest.access !== stored.access) return latest.access;
				return renew();
			};
			return navigator.locks ? await navigator.locks.request("kasbbook-refresh", run) : await run();
		} finally {
			renewing = null;
		}
	})();
	return renewing;
}
