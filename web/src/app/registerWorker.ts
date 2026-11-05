// The worker keeps the built files so the panel opens instantly and installs as an app. It never answers
// a page or the API: a stale page or a cached balance would be worse than a slow one.
export function registerWorker() {
	if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
	window.addEventListener("load", () => {
		navigator.serviceWorker.register("/sw.js").catch(() => {
			// without a worker the panel still works online
		});
	});
}
