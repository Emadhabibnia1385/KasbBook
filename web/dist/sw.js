const CACHE = "kasbbook-cbc34964ad";
const FILES = ["/assets/BookRequired-QMgJi61w.js","/assets/BottomSheet-BYrs6X3o.js","/assets/Capital-DfE3dgIi.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-Bb3RK3Gn.js","/assets/Collapsible-NgP4fPj9.js","/assets/ConfirmDialog-92J7zsQH.js","/assets/CurrencyPicker-4uHBUnTV.js","/assets/DataTable-BijMa0NM.js","/assets/DayField-CTrDSqbw.js","/assets/DeveloperFooter-BbR7SYit.js","/assets/ErrorState-Cep_Rvgu.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-C53WdKUP.js","/assets/ManageTabs-Dfyvv5zP.js","/assets/Modal-D8aIiNDY.js","/assets/Notice-B2SwHTlE.js","/assets/PayrollPage-BFdlW7VU.js","/assets/ProfileForm-C4THtOwb.js","/assets/SearchBox-Nms0jrrv.js","/assets/SectionCard-421iXCrN.js","/assets/SelectField-BA4tu9J-.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-x7gvKFsV.js","/assets/SwitchField-DUbVYkiz.js","/assets/Tabs-D1gBUJvG.js","/assets/TextField-B2O1uCFO.js","/assets/_app-CU9t97_Q.js","/assets/_app.account-Dv9p9U5r.js","/assets/_app.books-uFfknP0X.js","/assets/_app.index-8sUtigV5.js","/assets/_app.manage-BidzcdRY.js","/assets/_app.planning-BCyA9836.js","/assets/_app.portfolio-CVDJvPm7.js","/assets/_app.reports-DRYaM4ic.js","/assets/_app.team-4pckdRKi.js","/assets/_app.team.funds-Djml3lj2.js","/assets/_app.team.index-DSPJ1a_j.js","/assets/_app.team.periods._periodId-yhR0Ha6-.js","/assets/_app.team.periods.index-NPPFw2wk.js","/assets/_app.team.shares-BiZYuQIf.js","/assets/_app.transactions-B-WZW4WZ.js","/assets/_app.wallet-BSFvANQ6.js","/assets/accent-BE5EOlj-.js","/assets/auth-lRSl4OdR.js","/assets/books-CPBOGcVa.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-CymVeTGa.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/icons-B7FYk1y3.js","/assets/index-BtF-Yirt.css","/assets/index-CQhXP8Tu.js","/assets/index.esm-BCCxXNKF.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-CoBkHF_l.js","/assets/market-BmX1sg02.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-GyaGF5xl.js","/assets/payroll-ZWsoXw6T.js","/assets/portfolio-QEVBo_e6.js","/assets/queryDefaults-DICsa1n1.js","/assets/reports-BLhvrV9S.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-LyYrC_HE.js","/assets/schemas-CD3DIXmt.js","/assets/shared-D2SCmhe5.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-Dv9QmTxg.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-D5woUwGE.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-DNY2P2if.js","/assets/useCatalog-DdcMklv_.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-Do8QYOvA.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-GtZ01xZE.js","/assets/useTickerRows-DMHcbgEX.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
