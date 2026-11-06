const CACHE = "kasbbook-14cda499af";
const FILES = ["/assets/BottomSheet-2MjSg8Hf.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-Cv19xJdA.js","/assets/ConfirmDialog-DuA6hW8J.js","/assets/CurrencyPicker-DPjmb4_n.js","/assets/DataTable-Dc36zaOg.js","/assets/DateTimeField-BlPRTdnh.js","/assets/DayField-ese-WQFG.js","/assets/ErrorState-BJpBtXsx.js","/assets/FilterChips-BgPRS4qi.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-VbZ0ATHO.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-8VXIpMvS.js","/assets/Notice-D2dvxlPB.js","/assets/PageHeader-CA7TgqD5.js","/assets/PayrollPage-BAQokbUR.js","/assets/SearchBox-CsVeFJuz.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-CncyVFY8.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-Z1Gi4S8r.js","/assets/SwitchField-QdMuGISP.js","/assets/TextField-CFU422SY.js","/assets/_app-COoChTLd.js","/assets/_app.account-9VmytHq7.js","/assets/_app.books-CD3k3y1s.js","/assets/_app.index-BKE7Ir3T.js","/assets/_app.more-tORN-ibC.js","/assets/_app.planning-Zgwd8Fo5.js","/assets/_app.recurring-AswkLl_r.js","/assets/_app.reports-D4m3NKXj.js","/assets/_app.team-Dz03uGdR.js","/assets/_app.team.funds-DiEA1eYX.js","/assets/_app.team.index-BlhcFeH-.js","/assets/_app.team.periods._periodId-DExu6Vwy.js","/assets/_app.team.periods.index-DLtyP-0x.js","/assets/_app.team.shares-eibieiIq.js","/assets/_app.transactions-Ct6kWYxu.js","/assets/_app.wallet-ona_NkJK.js","/assets/accent-DFLrCj3u.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-CmcWOgaM.js","/assets/icons-JcburOYw.js","/assets/index-C-9zwz1p.css","/assets/index-dhxgNiu6.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-DWeHw4G4.js","/assets/market-C8voa1gF.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-Dzr2b82i.js","/assets/queryDefaults-CCk0vuur.js","/assets/schemas-BJxel5Xb.js","/assets/shared-Xxo1kY57.js","/assets/signOut-ZEcA5-T6.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-X4kj30mo.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-DE6bozw0.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-BN6nbpQY.js","/assets/useCatalog-Bl_v2ips.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-D03OXe8b.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-DProRy6a.js","/assets/useTextField-x8Bg0VS3.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
