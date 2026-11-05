const CACHE = "kasbbook-f114841091";
const FILES = ["/assets/Charts-BPgsq1uT.js","/assets/ChoiceFields-BuelGnb4.js","/assets/CollectionBuilder-BseNmv2Z.js","/assets/ConfirmDialog-DW8DxcWy.js","/assets/DataTable-CaI7me_G.js","/assets/DateTimeField-CHEesuaV.js","/assets/DayField-ChW0TNJ_.js","/assets/DragAndDrop-BSAnTZH7.js","/assets/ErrorState-BoKdaGzz.js","/assets/FocusScope-DwLYF0po.js","/assets/InstallButton-BW3Soz9-.js","/assets/KeyValueList-CrQqxIVM.js","/assets/Link-ByClUwVB.js","/assets/Modal-BT6ldtZx.js","/assets/Notice-D-qkfw4A.js","/assets/PageHeader-CFo7_Dhw.js","/assets/PayrollPage-BB_0MvZ4.js","/assets/SectionCard-owYyCB1g.js","/assets/SelectField-DomXa8-j.js","/assets/SelectionIndicator-CvXDF5rQ.js","/assets/StatusChip-DsZVT4IQ.js","/assets/SwitchField-BG-FhV__.js","/assets/TextField-DzJ5HuiV.js","/assets/ThemeToggle-KPY-kRgp.js","/assets/_app-D746jiGJ.js","/assets/_app.account-CN9wFbm4.js","/assets/_app.books-Dnmfx0ca.js","/assets/_app.index-Bxa2vNY8.js","/assets/_app.more-DtYbQkdU.js","/assets/_app.planning-DPxKs4ye.js","/assets/_app.recurring-UOkUpHGi.js","/assets/_app.reports-CJyOqJVi.js","/assets/_app.search-CTcQkmFu.js","/assets/_app.team-B_kBKo6D.js","/assets/_app.team.funds-DIbih0Op.js","/assets/_app.team.index-F_qPUIr0.js","/assets/_app.team.periods._periodId-EzhaawoI.js","/assets/_app.team.periods.index-DKc0rMlf.js","/assets/_app.team.shares-TgZkweVW.js","/assets/_app.transactions-CZNk_L1z.js","/assets/_app.wallet-MvSAXCHg.js","/assets/accent-Bp_qY2r5.js","/assets/calendar-C35FAti_.js","/assets/format-lNGD2Wyp.js","/assets/icons-CTCBPHCb.js","/assets/index-CXRN4TtA.css","/assets/index-DjAbiu8P.js","/assets/lazyRouteComponent-D8H4T9oA.js","/assets/link-BOmgi0kY.js","/assets/login-Ne9xPzRR.js","/assets/matchContext-DkkQk4I5.js","/assets/mutations-BvpdXvaE.js","/assets/queryDefaults-CnFsFUf0.js","/assets/reports-BqJPC-gC.js","/assets/schemas-6bun4tz_.js","/assets/shared-BAfaiAVt.js","/assets/signOut-DW2FluWP.js","/assets/status-C7SjyUYO.js","/assets/strings-CEBNpIHf.js","/assets/strings-Djc9GRnk.js","/assets/surface-m5gsIUuj.js","/assets/table.styles-CZultnra.js","/assets/tables-C-afejiJ.js","/assets/transport-BZN2SIDq.js","/assets/ui-KjsA8kyI.js","/assets/useActiveBook-BHwoiCrS.js","/assets/useFormValidation-C2JVQlID.js","/assets/useHasTabbableChild-CumBUoNl.js","/assets/useMatch-C144qAo9.js","/assets/useNavigate-CuOrRP7f.js","/assets/useSelector-B0S5vBJV.js","/assets/useSlot-DAqef0RE.js","/assets/useSpinButton-C9U2io5B.js","/assets/useTextField-C2IUWAtM.js","/assets/useToggleState-Bsg96S9x.js","/assets/useUpdateEffect-CHZoPcJt.js","/assets/with-selector-iB3vPiKp.js"];
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
