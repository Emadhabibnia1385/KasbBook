const CACHE = "kasbbook-c5712d27d1";
const FILES = ["/assets/BottomSheet-DMFU4t0n.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-BuuboI90.js","/assets/ConfirmDialog-BJf4x-Pd.js","/assets/CurrencyPicker-r9OHwUEV.js","/assets/DataTable-AWlra1gG.js","/assets/DateTimeField-D4Zvf8AG.js","/assets/DayField-DY_zgrxK.js","/assets/ErrorState-BepOMH3Z.js","/assets/FilterChips-rC1wH1oV.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubStar-C-XTKlSq.js","/assets/InstallButton-DFCYEU5K.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-ByvoWw9o.js","/assets/Notice-RWrFVlyf.js","/assets/PageHeader-hr0KNjdz.js","/assets/PayrollPage-gC6nrOxC.js","/assets/SearchBox-CIAoTgTZ.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-BGy4isyd.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-DY5TbBhv.js","/assets/SwitchField-BSWZSQJ6.js","/assets/TextField-efQCGvmj.js","/assets/_app-DVBeNQ0j.js","/assets/_app.account-D7PHUXcU.js","/assets/_app.books-BHvy5iPS.js","/assets/_app.index-DwNJruz5.js","/assets/_app.more-MNOIHnnp.js","/assets/_app.planning-YiAaaYG-.js","/assets/_app.recurring-CC_xNfoa.js","/assets/_app.reports-DVZ-XFnA.js","/assets/_app.team-RnfReSY6.js","/assets/_app.team.funds-9afHB-bD.js","/assets/_app.team.index-sauavD4I.js","/assets/_app.team.periods._periodId-Dzc2eZDI.js","/assets/_app.team.periods.index-CZcyT7Qe.js","/assets/_app.team.shares-BOmyK4mN.js","/assets/_app.transactions-CRGJRv-1.js","/assets/_app.wallet-5zTGxa3R.js","/assets/accent-fM2KmZIu.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-Cad5hDgO.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-BqxgMkKH.js","/assets/icons-JcburOYw.js","/assets/index-2zx63RyV.css","/assets/index-BwcKlNtK.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-wh4U3fFN.js","/assets/market-OH4LSfBN.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-DC641xVI.js","/assets/queryDefaults-BnDBXwIi.js","/assets/schemas-BQLYgh1C.js","/assets/shared-DuK2_Si-.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-06telppX.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-B5OZaHSk.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-BmToIKZ6.js","/assets/useCatalog-DvthSNob.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-BPL5Avay.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-C0IYsGP8.js","/assets/useTextField-Eg4C4s05.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
