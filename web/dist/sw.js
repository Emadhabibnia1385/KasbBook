const CACHE = "kasbbook-828501658b";
const FILES = ["/assets/CollectionBuilder-BFROzV1V.js","/assets/ConfirmDialog-wRm74SRL.js","/assets/ErrorState-0fHS-5BE.js","/assets/FocusScope-km1t2cU3.js","/assets/InstallButton-DYL-dsCw.js","/assets/Modal-DU4shzMX.js","/assets/PageHeader-C0wbHy9F.js","/assets/SectionCard-Didbs-LF.js","/assets/SelectField-CPWSytzW.js","/assets/SelectionIndicator-Cz9-1Rm0.js","/assets/StatusChip-CoxKLIFY.js","/assets/ThemeToggle-8Mp7d2AN.js","/assets/_app-Bg94nUso.js","/assets/_app.account-DIIm3YHq.js","/assets/_app.books-DYHVnP0Y.js","/assets/_app.index-D6xW2M4I.js","/assets/_app.more-BSw5vbf2.js","/assets/_app.planning-CxoiayA4.js","/assets/_app.reports-C-7OBd_q.js","/assets/_app.team-B1Sr6EMb.js","/assets/_app.transactions-ZNTkT60l.js","/assets/accent-DQ1OQVuX.js","/assets/collection-prop-injection-BffXlYXT.js","/assets/format-lNGD2Wyp.js","/assets/icons-ByZvPOUP.js","/assets/index-CVA-Fl70.js","/assets/index-oVc6OKLI.css","/assets/login-qPWxgHb8.js","/assets/queryDefaults-DdS9dHdz.js","/assets/schemas-Djd_DJYs.js","/assets/signOut-Dv0DvGRz.js","/assets/strings-BaAtxfCu.js","/assets/surface-CJtqd2Z-.js","/assets/table.styles-ozcLC7ob.js","/assets/tables-BBimJHxE.js","/assets/transport-BIz5W4Qm.js","/assets/useActiveBook-YosQTtqF.js","/assets/useHasTabbableChild-C2RL-YHD.js","/assets/useListState-DuAscHCS.js"];
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
