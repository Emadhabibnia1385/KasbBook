const CACHE = "kasbbook-0da6610d54";
const FILES = ["/assets/BottomSheet-BvDhyKim.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-DjaTD3YH.js","/assets/ConfirmDialog-YQFUr6xQ.js","/assets/CurrencyPicker-CMcC4gZt.js","/assets/DataTable-D7tfCqgi.js","/assets/DateTimeField-DjyHFp0E.js","/assets/DayField-BOU8mcn4.js","/assets/ErrorState-1Ex1AIBg.js","/assets/FilterChips-DKCsB0uO.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-D_RqN0ji.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Link-lYQXONkh.js","/assets/Modal-WfLn5IKV.js","/assets/Notice-plznjikj.js","/assets/PageHeader-6e1y2AHn.js","/assets/PayrollPage-BwnwS4U4.js","/assets/SearchBox-B0eKXlAu.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-DtM1TeeU.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-DIYC6Huv.js","/assets/SwitchField-CkVKFCOB.js","/assets/TextField-DDZt2IFn.js","/assets/ThemeToggle-B1MZn61J.js","/assets/_app-CZGjCYbB.js","/assets/_app.account-C5WDWQvc.js","/assets/_app.books-BDpjXXtf.js","/assets/_app.index-AG9HaExl.js","/assets/_app.more-DoTAmG7i.js","/assets/_app.planning-D8jOAn4T.js","/assets/_app.recurring-DH_KUitd.js","/assets/_app.reports-V9KRGxYE.js","/assets/_app.team-BWTHzB5U.js","/assets/_app.team.funds-CTAHbVCW.js","/assets/_app.team.index-Dri_OG9e.js","/assets/_app.team.periods._periodId-R-7rAFI_.js","/assets/_app.team.periods.index-jromb_JF.js","/assets/_app.team.shares-BetNnrkY.js","/assets/_app.transactions-CI7aQEY8.js","/assets/_app.wallet-WUuHkYzo.js","/assets/accent-KLJ_bmlu.js","/assets/calendar-C35FAti_.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/icons-BUBVvA8p.js","/assets/index-BISact4E.css","/assets/index-DIChMsDH.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-B9JuBmHa.js","/assets/market-CXClvsKU.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-C5_NRmb0.js","/assets/queryDefaults-D3P-1ZGs.js","/assets/schemas-BgOV9mN0.js","/assets/shared-sfGRDSqP.js","/assets/signOut-7l5ppRlm.js","/assets/status-C7SjyUYO.js","/assets/strings-DnSs5-Dl.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-Cv-OXPbN.js","/assets/transport-GZ-DDpYf.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-Dwf9MA2p.js","/assets/useCatalog-Ce2Bp2dm.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-CxY5enm_.js","/assets/useRates-bLrlKmRA.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-BnhlgkMq.js","/assets/useTextField-BDFBFRes.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
