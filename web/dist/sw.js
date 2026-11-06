const CACHE = "kasbbook-405d85f7d4";
const FILES = ["/assets/BottomSheet-9O0Hxyyk.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-D4-o41uT.js","/assets/ConfirmDialog-DsPD8Xfr.js","/assets/CurrencyPicker-DP1iKLxy.js","/assets/DataTable-DGlaA74P.js","/assets/DateTimeField-BZfdgICy.js","/assets/DayField-D2fOtsMt.js","/assets/ErrorState-Dq_vYE26.js","/assets/FilterChips-DEudOaVP.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-4eTfi2jO.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-D3KUhe3V.js","/assets/Notice-DWJBVI7o.js","/assets/PageHeader-DkovYuuH.js","/assets/PayrollPage-B4RX21ar.js","/assets/SearchBox-DfqY8ou1.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-Cbqb0_Bh.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-DylmoSHE.js","/assets/SwitchField-D6La6w2V.js","/assets/TextField-KG19RkBy.js","/assets/_app-C3l-aSwB.js","/assets/_app.account-Dy8MA7B_.js","/assets/_app.books-CINYtRyZ.js","/assets/_app.index-BUewA1Ob.js","/assets/_app.more-DGwFC-iC.js","/assets/_app.planning-CEIqNhyN.js","/assets/_app.recurring-CCReKUVo.js","/assets/_app.reports-sTp4LDf0.js","/assets/_app.team-B2uWthW1.js","/assets/_app.team.funds-r2hBO4-k.js","/assets/_app.team.index-DJ3uJh7Z.js","/assets/_app.team.periods._periodId-Baz-0xFt.js","/assets/_app.team.periods.index-Cxyy_D8E.js","/assets/_app.team.shares-C2-_1X2f.js","/assets/_app.transactions-C6cl62zr.js","/assets/_app.wallet-n0i_psTY.js","/assets/accent-DiNhhSK9.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-Byv8MDfe.js","/assets/icons-JcburOYw.js","/assets/index--1_2mC8l.js","/assets/index-JJOJE6qi.css","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-CaUogBjN.js","/assets/market-BxvB-qnv.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-Y3sEEZL8.js","/assets/queryDefaults-BppeTlr4.js","/assets/schemas-kufO9taC.js","/assets/shared-CgYR9xZV.js","/assets/signOut-BfW27gnf.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-CrvZ4fMt.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-C2506pnd.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-Dmq6z6ld.js","/assets/useCatalog-CHCuYfSe.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-CNdm4Ucc.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-Cp443e6O.js","/assets/useTextField-CMwXXYag.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
