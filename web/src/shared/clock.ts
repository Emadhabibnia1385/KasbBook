import { useSyncExternalStore } from "react";

// One timer for the whole page. Every ticking thing (the clock, «۱۲ ثانیه پیش») reads the same second, so
// ten of them cost one interval and one wake-up, not ten. It runs only while someone is subscribed and the
// tab is visible: a hidden tab does no work, and shows the right time the instant it comes back.

type Listener = () => void;

const listeners = new Set<Listener>();
let second = Math.floor(Date.now() / 1000);
let timer: ReturnType<typeof setInterval> | undefined;

function tick() {
	second = Math.floor(Date.now() / 1000);
	for (const listener of listeners) listener();
}

function sync() {
	const wanted = listeners.size > 0 && !document.hidden;
	if (wanted && timer === undefined) {
		tick();
		timer = setInterval(tick, 1000);
	} else if (!wanted && timer !== undefined) {
		clearInterval(timer);
		timer = undefined;
	}
}

function subscribe(listener: Listener) {
	if (listeners.size === 0) document.addEventListener("visibilitychange", sync);
	listeners.add(listener);
	sync();
	return () => {
		listeners.delete(listener);
		if (listeners.size === 0) document.removeEventListener("visibilitychange", sync);
		sync();
	};
}

/** Unix seconds, re-read every second while the tab is visible. */
export function useNowSeconds(): number {
	return useSyncExternalStore(
		subscribe,
		() => second,
		() => second,
	);
}

/** Whether the shared timer is running; for tests. */
export const isClockRunning = () => timer !== undefined;
