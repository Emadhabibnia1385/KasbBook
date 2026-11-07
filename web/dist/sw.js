const CACHE = "kasbbook-60dd2132fc";
const FILES = ["/assets/AttachmentsField-BfpkCQLK.js","/assets/BookRequired-WlniZKBt.js","/assets/BottomSheet-D3aGlD58.js","/assets/Capital-Cv_TfSLj.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-DSgftq5q.js","/assets/Collapsible-DNZtrYq3.js","/assets/ConfirmDialog-DYwg8p21.js","/assets/CurrencyPicker-9zx4xbAQ.js","/assets/DataTable-0ABAiv7b.js","/assets/DayField-BQBJfHdI.js","/assets/DayPair-DCcvq9L6.js","/assets/DeveloperFooter-ZKdVbjIp.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-C3M1WcJD.js","/assets/ManageTabs-CA1qsncJ.js","/assets/Modal-D6HpT3wp.js","/assets/Notice-CZdR9oMz.js","/assets/PageHeader-tMcIhqGQ.js","/assets/PayrollPage-psZYaoTL.js","/assets/ProfileForm-Co0i0qex.js","/assets/SearchBox-CIiT1RFr.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-DY-Nf2fU.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-CU6iUmDo.js","/assets/SwitchField-5B4HIIGO.js","/assets/Tabs-GqZ8WsT7.js","/assets/TextField-BjzXqTUd.js","/assets/_app-CD_4Mh0y.js","/assets/_app.account-kp7Pi8VI.js","/assets/_app.books-DaNkExxz.js","/assets/_app.index-BoNDZKfL.js","/assets/_app.manage-D7EimErJ.js","/assets/_app.planning-tdg8II5Q.js","/assets/_app.portfolio-W30GWbuz.js","/assets/_app.reports-BidWPSSR.js","/assets/_app.team-OicNSYGZ.js","/assets/_app.team.funds-BoEXdfM5.js","/assets/_app.team.index-qPcXui1x.js","/assets/_app.team.periods._periodId-CAe4jPSj.js","/assets/_app.team.periods.index-CFNfy_rK.js","/assets/_app.transactions-CCe-IOoR.js","/assets/_app.wallet-BrVa6QRw.js","/assets/accent-BcqBEwlH.js","/assets/auth-4brTEGxA.js","/assets/books-Czjy6fRs.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-B4ySKhYR.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/icons-B7FYk1y3.js","/assets/index-2RWPcnyC.js","/assets/index-DqQQLFie.css","/assets/index.esm-7Yym7uXT.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-Bg_PEUEb.js","/assets/market-BnKv7CCa.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-DsYiJAyH.js","/assets/payroll-CCNhFNh6.js","/assets/portfolio-CyLA2CZp.js","/assets/queryDefaults-vRP5vsmQ.js","/assets/reports-CydmyS83.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-CC_Thce9.js","/assets/schemas-iA3_bGCq.js","/assets/shared-CTT9mC6v.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-B18Fb_VY.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-CTZlL8fg.js","/assets/ui-CO-FmDcN.js","/assets/useActiveBook-X-h0cduS.js","/assets/useCatalog-6QcRMRmM.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-DuyS_h8-.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-B5xRosYp.js","/assets/useTickerRows-Dxs6YdbI.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
