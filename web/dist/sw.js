const CACHE = "kasbbook-f028bd2dc6";
const FILES = ["/assets/Charts-BPgsq1uT.js","/assets/ChoiceFields-DSyJ0bbW.js","/assets/CollectionBuilder-BseNmv2Z.js","/assets/ConfirmDialog-CNtXGcz_.js","/assets/DataTable-Cp9Scd-h.js","/assets/DateTimeField-TiPbBXFO.js","/assets/DayField-S3__Mgnm.js","/assets/DragAndDrop-lk-ImFds.js","/assets/ErrorState-Xd8idb-x.js","/assets/FocusScope-DwLYF0po.js","/assets/InstallButton-Dxv1eBo2.js","/assets/KeyValueList-CrQqxIVM.js","/assets/Link-ByClUwVB.js","/assets/Modal-BcDhim7K.js","/assets/Notice-CJyH2TPn.js","/assets/PageHeader-BvoOvM37.js","/assets/PayrollPage-BZRhpbwM.js","/assets/SectionCard-owYyCB1g.js","/assets/SelectField-iLy0q8cz.js","/assets/SelectionIndicator-CvXDF5rQ.js","/assets/StatusChip-GVmG77rf.js","/assets/SwitchField-BmWtq8lG.js","/assets/TextField-CZefrAlg.js","/assets/ThemeToggle-oS6jBa2b.js","/assets/_app-Ci_J9Hs6.js","/assets/_app.account-Dy0vK6u3.js","/assets/_app.books-xIZc2cMz.js","/assets/_app.index-BtkSpgD2.js","/assets/_app.more-DPXaOtaP.js","/assets/_app.planning-B7tuVPiA.js","/assets/_app.recurring-CuyGhAs8.js","/assets/_app.reports-BX1sj_I3.js","/assets/_app.search-B3S2NI3f.js","/assets/_app.team-BxORiDJs.js","/assets/_app.team.funds-D-XX1V1c.js","/assets/_app.team.index-DgzBP6hb.js","/assets/_app.team.periods._periodId-CExcL2OP.js","/assets/_app.team.periods.index-HQOXXorJ.js","/assets/_app.team.shares-BLj6rj5J.js","/assets/_app.transactions-45ZW3w1q.js","/assets/_app.wallet-C9z9_SLu.js","/assets/accent-CvDLZUfP.js","/assets/calendar-C35FAti_.js","/assets/format-DupWuRm2.js","/assets/icons-_UWj8688.js","/assets/index-4tc4e3jF.css","/assets/index-D1ux19-A.js","/assets/lazyRouteComponent-D8H4T9oA.js","/assets/link-BOmgi0kY.js","/assets/login-DJsTFZK_.js","/assets/matchContext-DkkQk4I5.js","/assets/mutations-Br9vd76d.js","/assets/queryDefaults-ge5aH2b-.js","/assets/reports-DlNj-tdd.js","/assets/schemas-D6d5pHI1.js","/assets/shared-CcjeajkC.js","/assets/signOut-DyumGygk.js","/assets/status-C7SjyUYO.js","/assets/strings-CEBNpIHf.js","/assets/strings-Djc9GRnk.js","/assets/surface-m5gsIUuj.js","/assets/table.styles-CZultnra.js","/assets/tables-Dfh0Adom.js","/assets/transport-BZN2SIDq.js","/assets/ui-KjsA8kyI.js","/assets/useActiveBook-dPwnSdga.js","/assets/useFormValidation-CeemgI4m.js","/assets/useHasTabbableChild-CumBUoNl.js","/assets/useMatch-C144qAo9.js","/assets/useNavigate-CuOrRP7f.js","/assets/useSelector-B0S5vBJV.js","/assets/useSlot-DAqef0RE.js","/assets/useSpinButton-HCyoqKXA.js","/assets/useTextField-Czq3Ypk_.js","/assets/useToggleState-Bsg96S9x.js","/assets/useUpdateEffect-CHZoPcJt.js","/assets/with-selector-iB3vPiKp.js"];
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
