const CACHE = "kasbbook-3b3d465889";
const FILES = ["/assets/BottomSheet-C8U4pMU1.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-DOB79vTs.js","/assets/ConfirmDialog-lUsUgQVP.js","/assets/CurrencyPicker-CXJBD6UK.js","/assets/DataTable-C5_rhVl_.js","/assets/DateTimeField-CwTgLFBq.js","/assets/DayField-45Go10sc.js","/assets/ErrorState-BJF0MMaU.js","/assets/FilterChips-B52t_f1_.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-Dk2qXL5D.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-CCUwZa8l.js","/assets/Notice-DC9P6mCe.js","/assets/PageHeader-25zPNz_v.js","/assets/PayrollPage-0OAOtlO_.js","/assets/SearchBox-DtkEucKA.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-CMpb8ld1.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-DeluugjW.js","/assets/SwitchField-DNIlHm7V.js","/assets/TextField-BLorHArt.js","/assets/ThemeToggle-DpZAoI1F.js","/assets/_app-ClvbhbR1.js","/assets/_app.account-BVyrRrGV.js","/assets/_app.books-BYPSaKVH.js","/assets/_app.index-qfBsaxY2.js","/assets/_app.more-B7EgCCWQ.js","/assets/_app.planning-uDSAhk9u.js","/assets/_app.recurring-ClLb8zt8.js","/assets/_app.reports-DpAYlBxc.js","/assets/_app.team-C-qec6Ou.js","/assets/_app.team.funds-CdxW7XTh.js","/assets/_app.team.index-nAU5aT7X.js","/assets/_app.team.periods._periodId-BmnmM9hg.js","/assets/_app.team.periods.index-DlBgTl9w.js","/assets/_app.team.shares-Fz3FvK6P.js","/assets/_app.transactions-DKmpI20f.js","/assets/_app.wallet-Dqgk1aMF.js","/assets/accent-Kx9vCMCm.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/icons-JcburOYw.js","/assets/index-BJH0uYWh.css","/assets/index-r57K7vMP.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-CaWhQDmT.js","/assets/market-C3_xTF3I.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-BHZ9gQOa.js","/assets/queryDefaults-C6qRotiw.js","/assets/schemas-C1blTTYh.js","/assets/shared-DuVxMV0u.js","/assets/signOut-DSE_znD2.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-BmVqUVwW.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-BwNTB6EE.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-Bo33wKjp.js","/assets/useCatalog-4n6Lrc9p.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-CfuNngEH.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-CIZzOxpW.js","/assets/useTextField-Cetz8HGw.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
