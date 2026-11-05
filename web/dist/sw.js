const CACHE = "kasbbook-03b06a8fe9";
const FILES = ["/assets/BottomSheet-CVlCMTz2.js","/assets/Charts-CI3oy8p4.js","/assets/ChoiceFields-DHOpJVnM.js","/assets/Collapsible-Dpwhxqji.js","/assets/CollectionBuilder-Dhmn1dbV.js","/assets/ConfirmDialog-Dj1I7fse.js","/assets/CurrencyPicker-B7wsNRAG.js","/assets/DataTable-BfIUxZdY.js","/assets/DateTimeField-v7GWHTDa.js","/assets/DayField-CrvXUGR2.js","/assets/DragAndDrop-DQ_6zma4.js","/assets/ErrorState-rjN6YCkz.js","/assets/FilterChips-DEWTRw0L.js","/assets/FocusScope-DhpQS_-l.js","/assets/InstallButton-D5wQxkmY.js","/assets/KeyValueList-D1onqNxS.js","/assets/Link-BYL9pYCf.js","/assets/Modal-Df2vM7UD.js","/assets/Notice-CgDyq7_R.js","/assets/PageHeader-UZT0cbnh.js","/assets/PayrollPage-B-ZMha9Y.js","/assets/SearchBox-Cyuw9ToA.js","/assets/SectionCard-M0gPWOg6.js","/assets/SelectField-DDaUNeyP.js","/assets/SelectionIndicator-BOpo7VTd.js","/assets/StatusChip-BviaqHQm.js","/assets/SwitchField-PPfq7HqN.js","/assets/TextField-LM8FDFPC.js","/assets/ThemeToggle-BejOtduX.js","/assets/_app-DjFYbZtN.js","/assets/_app.account-BfB8rhCz.js","/assets/_app.books-FB-SKPj5.js","/assets/_app.index-_3k5Esy7.js","/assets/_app.more-Dj-wSisa.js","/assets/_app.planning-BFx1oofc.js","/assets/_app.recurring-CPD7jj90.js","/assets/_app.reports-DvyyQ4xI.js","/assets/_app.search-B--tyx0C.js","/assets/_app.team-CsH5mmuv.js","/assets/_app.team.funds-CugJeEVg.js","/assets/_app.team.index-C0aby60m.js","/assets/_app.team.periods._periodId-CGwQ1Jtt.js","/assets/_app.team.periods.index-CEnQrtqm.js","/assets/_app.team.shares-qdJbiKt3.js","/assets/_app.transactions-BPiM0uM5.js","/assets/_app.wallet-Ck2QP4Ec.js","/assets/accent-DiXtivpE.js","/assets/calendar-C35FAti_.js","/assets/format-P-qd1Sc3.js","/assets/icons-OnFU8E6f.js","/assets/index-DBmYXQPX.css","/assets/index-e-9-BswM.js","/assets/lazyRouteComponent-DGj4Z5Z9.js","/assets/link-9u5RgHUX.js","/assets/login-D6dofgQ6.js","/assets/matchContext-cc3Ayemd.js","/assets/mutations-BKC907QN.js","/assets/queryDefaults-DgdY8eee.js","/assets/reports-BiqCRuNh.js","/assets/schemas-Cxwu9gpj.js","/assets/shared-u3UUIFyZ.js","/assets/signOut-EJucPQ6e.js","/assets/status-C7SjyUYO.js","/assets/strings-CTwhDYF-.js","/assets/strings-apYYuTuH.js","/assets/surface-CzXJ4rMC.js","/assets/table.styles-CGHRRP-G.js","/assets/tables-Dfkx871O.js","/assets/transport-D_beH6wm.js","/assets/ui-DHXZnhlv.js","/assets/useActiveBook-o9Y0Wgm6.js","/assets/useCatalog-RmWXKvik.js","/assets/useFormValidation-DwJNZFKf.js","/assets/useHasTabbableChild-aGbBmjwL.js","/assets/useIsNarrow-9O_PBOJL.js","/assets/useMatch-DhBqsGQN.js","/assets/useNavigate-ZaR3xKjb.js","/assets/useRates-BXXm6yKO.js","/assets/useRouter-CKJ-ESiG.js","/assets/useSelector-CKhK6VXD.js","/assets/useSlot-DKyGHhzW.js","/assets/useSpinButton-Cxj37Ymj.js","/assets/useTextField-B2zSOAnQ.js","/assets/useToggleState-2Uo_lOLb.js","/assets/useUpdateEffect-DljWPYsC.js","/assets/with-selector-DG9Jayx5.js"];
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
