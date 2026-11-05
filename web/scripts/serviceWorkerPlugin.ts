import { createHash } from "node:crypto";
import type { Plugin } from "vite";

// A file the build names after its content: JS, CSS and fonts under assets/.
const HASHED = /^assets\/.+-[\w-]{8}\.(?:js|css|woff2?)$/;

/** The worker's text: it answers only the files it kept, never a page, the API or another site. */
function workerSource(files: string[], version: string): string {
	return `const CACHE = "kasbbook-${version}";
const FILES = ${JSON.stringify(files)};
self.addEventListener("install", (event) => {
	event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
	const old = (keys) => keys.filter((key) => key.startsWith("kasbbook-") && key !== CACHE);
	event.waitUntil(
		caches.keys()
			.then((keys) => Promise.all(old(keys).map((key) => caches.delete(key))))
			.then(() => self.clients.claim()),
	);
});
self.addEventListener("fetch", (event) => {
	const { request } = event;
	const { origin, pathname } = new URL(request.url);
	if (request.method !== "GET" || request.mode === "navigate") return;
	if (origin !== location.origin || !FILES.includes(pathname)) return;
	event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
});
`;
}

/** Emits /sw.js at build time: it keeps the hashed assets, and never touches /api or a page. */
export function serviceWorker(): Plugin {
	return {
		name: "kasbbook:service-worker",
		apply: "build",
		generateBundle(_, bundle) {
			const files = Object.keys(bundle)
				.filter((name) => HASHED.test(name))
				.sort()
				.map((name) => `/${name}`);
			// The files carry their own hashes, so a new set of them is a new worker.
			const version = createHash("sha256").update(files.join("\n")).digest("hex").slice(0, 10);
			this.emitFile({ type: "asset", fileName: "sw.js", source: workerSource(files, version) });
		},
	};
}
