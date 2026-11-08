const CACHE = "kasbbook-081f241b98";
const FILES = ["/assets/AttachmentsField-GJioiBDy.js","/assets/BookRequired-DtSL2C3t.js","/assets/BottomSheet-Cf3_iUMu.js","/assets/BrandMark-Nw2-Q7U4.js","/assets/Capital-Bg14hq_6.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BH_lJsRY.js","/assets/Collapsible-CWOfN12A.js","/assets/ConfirmDialog-B6RTLYSf.js","/assets/CurrencyPicker-Bq-SWgZ6.js","/assets/DataTable-UWEdQJAY.js","/assets/DayField-EoqrNQbw.js","/assets/DayPair-DqNYr3Ep.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-B-_zZdoZ.js","/assets/ManageTabs-8k0eBk8a.js","/assets/Modal-DlxRSeFz.js","/assets/Notice-L2KEzlRW.js","/assets/PageHeader-Bvk6bM43.js","/assets/PayrollPage-Bcli0vKM.js","/assets/ProfileForm-BqE8YbGK.js","/assets/SearchBox-Eln_zmYD.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-CaD3jeIW.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-Ca6YlH88.js","/assets/SwitchField-dtg0D-g2.js","/assets/Tabs-kiuWFs5I.js","/assets/TextField-BMRDOH5z.js","/assets/_app-Z0FqHj3V.js","/assets/_app.account-D0Z_rWUd.js","/assets/_app.books-CezK1bwz.js","/assets/_app.index-BmNd0v7j.js","/assets/_app.manage-eO9_cHLu.js","/assets/_app.planning-D-OKn84u.js","/assets/_app.portfolio-CVTwMK2R.js","/assets/_app.reports-CcE8mNkm.js","/assets/_app.team-BitBAEDJ.js","/assets/_app.team.funds-BbGCFnk_.js","/assets/_app.team.index-5hxJTQSt.js","/assets/_app.team.periods._periodId-CJEWbbSl.js","/assets/_app.team.periods.index-BrszvqqE.js","/assets/_app.transactions-BFB88f5p.js","/assets/_app.wallet-C4IrpHgo.js","/assets/accent-t1KHBB6N.js","/assets/auth-CumEBUXm.js","/assets/books-CM5UAWdk.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-CpX0Q6t3.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/format-BOlHpKmW.js","/assets/icons-B7FYk1y3.js","/assets/index-BY4pb1Op.css","/assets/index-BuYdOHF4.js","/assets/index.esm-DduHZGmw.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-DHzkyWsO.js","/assets/market-DK3LHUYB.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CmrduP_e.js","/assets/payroll-BFRvFyv5.js","/assets/portfolio-BFdEdm3R.js","/assets/reports-ClK4TyMe.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-YqnYtlxh.js","/assets/schemas-s-D9YejZ.js","/assets/shared-COGp79vk.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DwARxPH3.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-D1Ugw7G9.js","/assets/ui-BrLfvb3M.js","/assets/useActiveBook-BCQhHDvA.js","/assets/useCatalog-C4d_21ue.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-DpwrQ6CL.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-CzzSOcEr.js","/assets/useTickerRows-Dmmcj8v5.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
