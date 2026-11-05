import { useSyncExternalStore } from "react";

// The browser offers its install prompt once, possibly before any screen is open, so it is caught at
// startup and kept until someone presses the button.
type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

let deferred: InstallEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

export function watchInstallPrompt() {
	window.addEventListener("beforeinstallprompt", (event) => {
		event.preventDefault();
		deferred = event as InstallEvent;
		notify();
	});
	window.addEventListener("appinstalled", () => {
		deferred = null;
		notify();
	});
}

const standalone = () =>
	matchMedia("(display-mode: standalone)").matches ||
	(navigator as Navigator & { standalone?: boolean }).standalone === true;

const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

export type InstallState = "installed" | "prompt" | "ios" | "none";

function snapshot(): InstallState {
	if (standalone()) return "installed";
	if (deferred) return "prompt";
	return isIos() ? "ios" : "none";
}

export function useInstallState(): InstallState {
	return useSyncExternalStore(
		(listener) => {
			listeners.add(listener);
			return () => listeners.delete(listener);
		},
		snapshot,
		() => "none",
	);
}

export async function promptInstall() {
	if (!deferred) return;
	const event = deferred;
	deferred = null;
	notify();
	await event.prompt();
	await event.userChoice;
}
