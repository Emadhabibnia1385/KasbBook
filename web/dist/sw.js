const CACHE = "kasbbook-3b8ef0cbf0";
const FILES = ["/assets/BottomSheet-CHpHOHfi.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-hs_B0xbz.js","/assets/ConfirmDialog-DK6rXFYO.js","/assets/CurrencyPicker-DnUzX4pp.js","/assets/DataTable-CbIbvPLj.js","/assets/DateTimeField-ickWrHKO.js","/assets/DayField-DWHC0hMK.js","/assets/ErrorState-DIPbzhTo.js","/assets/FilterChips-CKUR_4hi.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubStar-CDO6tbvU.js","/assets/InstallButton-C0tRvudY.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-xOKfBbCA.js","/assets/Notice-Ci8PWNLf.js","/assets/PageHeader-DqVK_UBE.js","/assets/PayrollPage-BGXoNSXY.js","/assets/SearchBox-Dps05W4U.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-ybcNlVtt.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-CkO1WNGL.js","/assets/SwitchField-nOIlhCrW.js","/assets/TextField-CqPsQVnX.js","/assets/_app-CKkO8GsF.js","/assets/_app.account-D1ZT-rnh.js","/assets/_app.books-CrKsE0zM.js","/assets/_app.index-BFxRWcj7.js","/assets/_app.more-BKuis29j.js","/assets/_app.planning-DlHxuFpc.js","/assets/_app.recurring-CXTIml35.js","/assets/_app.reports-DEbjTDse.js","/assets/_app.team-nh0k893Z.js","/assets/_app.team.funds-D8JRoZei.js","/assets/_app.team.index-D-rru1NJ.js","/assets/_app.team.periods._periodId-CVxbUhpN.js","/assets/_app.team.periods.index-C0yoaqoY.js","/assets/_app.team.shares-DsVmyVnq.js","/assets/_app.transactions-C8pktLDz.js","/assets/_app.wallet-Jti9Fu6I.js","/assets/accent-CwiYmYUb.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/format-qCbjsuG1.js","/assets/headerPrefs-C6XjuMMC.js","/assets/icons-BK6FpNJ1.js","/assets/index-B7WT0ZsB.js","/assets/index-D0gfnePA.css","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-CnaLgEYy.js","/assets/market-v83IS3vZ.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-DPV7gyLa.js","/assets/queryDefaults-BYx0QKR5.js","/assets/schemas-Dd0z5weO.js","/assets/shared-CGauBIOw.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-qJtTolEK.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-BYKZuvK-.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-BurDLhMT.js","/assets/useCatalog-CSwUaCVg.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-D3aOr2OV.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-B-NSIsfr.js","/assets/useTextField-CuEEWuWT.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
