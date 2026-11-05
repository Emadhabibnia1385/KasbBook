const CACHE = "kasbbook-a5ae920462";
const FILES = ["/assets/BottomSheet-FC4520Qm.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-DprhePxE.js","/assets/ConfirmDialog-Cs7KZsjv.js","/assets/CurrencyPicker-CGv292JB.js","/assets/DataTable-FLxEe-ca.js","/assets/DateTimeField-D5vH2oqu.js","/assets/DayField-C2t9OpPL.js","/assets/ErrorState-DPdVMmT3.js","/assets/FilterChips-DKCsB0uO.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-B8u1kD0o.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Link-lYQXONkh.js","/assets/Modal-BX5k2Q2K.js","/assets/Notice-CbjhtRLg.js","/assets/PageHeader-BRumXp0p.js","/assets/PayrollPage-ByLKK3X1.js","/assets/SearchBox-CppJVlkE.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-_wwcHUEf.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-DrWfccsA.js","/assets/SwitchField-CjtMRKA5.js","/assets/TextField-BSWByuEC.js","/assets/ThemeToggle-BVOv1cnv.js","/assets/_app-CfC2XEQ7.js","/assets/_app.account-Bbs2qHld.js","/assets/_app.books-DKF4KCAO.js","/assets/_app.index-DYha1mW8.js","/assets/_app.more-Dq-A0P0y.js","/assets/_app.planning-H6j79uim.js","/assets/_app.recurring-DEGVudMe.js","/assets/_app.reports-D9Uj0O1d.js","/assets/_app.team-Ca8JpsEW.js","/assets/_app.team.funds-Nr-52I6Q.js","/assets/_app.team.index-L8dHu5rK.js","/assets/_app.team.periods._periodId-DT2WYpH6.js","/assets/_app.team.periods.index-CT5pVmQi.js","/assets/_app.team.shares-ByNnq8lH.js","/assets/_app.transactions-B8F8ehMU.js","/assets/_app.wallet-5zQrGSqv.js","/assets/accent-A03GnLmI.js","/assets/calendar-C35FAti_.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/icons-BUBVvA8p.js","/assets/index-BISact4E.css","/assets/index-DZbrEiSo.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-D4_zrLR0.js","/assets/market-Bn614_5X.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-D8ZX8MRV.js","/assets/queryDefaults-BoSMuuTs.js","/assets/schemas-CYG_VIh2.js","/assets/shared-DEbg_rII.js","/assets/signOut-Dw7iJv8B.js","/assets/status-C7SjyUYO.js","/assets/strings-DnSs5-Dl.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-NeVGhGdU.js","/assets/transport-Dw8T4PI4.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-DlTb28WK.js","/assets/useCatalog-Bbihdew3.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-DxaNIuMK.js","/assets/useRates-DP6NL_N3.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-D_5rG_je.js","/assets/useTextField-DFvr5jjQ.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
