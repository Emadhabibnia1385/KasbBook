const CACHE = "kasbbook-79cbd8c5b2";
const FILES = ["/assets/CollectionBuilder-B7seGwSr.js","/assets/ConfirmDialog-B7_KAa6V.js","/assets/ErrorState-lIuhNFiF.js","/assets/InstallButton-ayZ9_k7W.js","/assets/Modal-B4yx5nsN.js","/assets/PageHeader-LOCI8KsH.js","/assets/SectionCard-DgCe646K.js","/assets/SelectField-CViVrV8P.js","/assets/StatusChip-BQM0h-kL.js","/assets/ThemeToggle-hrpuo3oL.js","/assets/_app-BrW4G7FU.js","/assets/_app.account-DW7-nrk0.js","/assets/_app.books-C-3xBM6f.js","/assets/_app.index-CAkb5mta.js","/assets/_app.more-CLlImzxc.js","/assets/_app.planning-BHK2EWtV.js","/assets/_app.reports-DZUjd5sF.js","/assets/_app.team-BptLleoo.js","/assets/_app.transactions-CXUTvwH-.js","/assets/accent-BL58STKE.js","/assets/fa-BmyU83BZ.js","/assets/format-BPk_mNU9.js","/assets/icons-Cf1-RkGg.js","/assets/index-B3h8Cgs3.js","/assets/index-Bs1W68Aq.css","/assets/login-CMyKSP5C.js","/assets/queryDefaults-C6JGvyzl.js","/assets/reports-D3YElNRP.js","/assets/schemas-CJykiMyd.js","/assets/signOut-COIqBEZr.js","/assets/surface-vaUGvurF.js","/assets/table.styles-KMoHb0NC.js","/assets/transport-BkP3VNYH.js","/assets/useActiveBook-MsBTfhW0.js","/assets/useHasTabbableChild-c4UKF5JW.js","/assets/useListState-0eEf-Dkh.js"];
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
