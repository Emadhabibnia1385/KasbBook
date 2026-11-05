const CACHE = "kasbbook-5e78d072f2";
const FILES = ["/assets/InstallButton-5EA3E4Ed.js","/assets/PageHeader-BsD0MNYb.js","/assets/_app-BIPgZZR5.js","/assets/_app.account-DEVLGk2g.js","/assets/_app.books-Bxibkc70.js","/assets/_app.index-CC_GSHJ7.js","/assets/_app.more-B2q1g9aO.js","/assets/_app.planning-rEhlIASn.js","/assets/_app.reports-nZvizu21.js","/assets/_app.team-BHET2AnM.js","/assets/_app.transactions-BqBR462N.js","/assets/accent-NhR4JLn5.js","/assets/fa-ZHlw5fbC.js","/assets/icons-DqKCsM4Q.js","/assets/index-CiHbke5M.js","/assets/index-TUFbLnny.css","/assets/login-BemNLOXO.js","/assets/queryDefaults-D5SviT6B.js","/assets/rolldown-runtime-WkwZ5CU-.js","/assets/session-lKgk86N-.js","/assets/transport-DWSjY-kM.js","/assets/useActiveBook-DFmURuAh.js"];
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
