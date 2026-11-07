const CACHE = "kasbbook-1fefb9feb5";
const FILES = ["/assets/AttachmentsField-F4x6_fQd.js","/assets/BookRequired-C0iFtS-5.js","/assets/BottomSheet-Bl6LR-dY.js","/assets/Capital-DrEZ9vTL.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BOt6hGFh.js","/assets/Collapsible-C7xKAZSP.js","/assets/ConfirmDialog-B7ukzq7m.js","/assets/CurrencyPicker-CYe2oZBj.js","/assets/DataTable-CVlzxeLE.js","/assets/DayField-BEppsJmo.js","/assets/DayPair-B4RtlFVP.js","/assets/DeveloperFooter-zwR-R6ig.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-DJeXqDhV.js","/assets/ManageTabs-Cy-FSCyF.js","/assets/Modal-B6W81yWb.js","/assets/Notice-BbF9x8jp.js","/assets/PageHeader-BAwtC1Zc.js","/assets/PayrollPage-CQUFzZNW.js","/assets/ProfileForm-BUS2xSGA.js","/assets/SearchBox-DIrb9GQu.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-C6XXfWm2.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-wtVfyo2T.js","/assets/SwitchField-BqnAAML2.js","/assets/Tabs-Cthg5tVk.js","/assets/TextField-B-JYtTlQ.js","/assets/_app-BbomJkDD.js","/assets/_app.account-C7VPP3d9.js","/assets/_app.books-W-26nlI-.js","/assets/_app.index-BTvGlIxe.js","/assets/_app.manage-D6NOEDEu.js","/assets/_app.planning-Dx7jr7EU.js","/assets/_app.portfolio-ZtghVGhy.js","/assets/_app.reports-BoECzllo.js","/assets/_app.team-Bl8olFNt.js","/assets/_app.team.funds-C2AjI653.js","/assets/_app.team.index-vSjb3cr_.js","/assets/_app.team.periods._periodId-f92w_wFd.js","/assets/_app.team.periods.index-UI8DZvtx.js","/assets/_app.transactions-C1zVA5YQ.js","/assets/_app.wallet-CCNUMBOT.js","/assets/accent-CuJO3Imx.js","/assets/auth-CH5PMId1.js","/assets/books-DKBcHoXF.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-CTVlTdJq.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-CSs7BWOW.js","/assets/index-DqQQLFie.css","/assets/index.esm-BgXS5bvs.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-CtlhKDpX.js","/assets/market-DfeVqKgh.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-DSfgbBw0.js","/assets/payroll-w4j5M3YV.js","/assets/portfolio-BYibabX2.js","/assets/queryDefaults-CDrR-OIS.js","/assets/reports-BlW6BzS7.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-Dfp4AfO1.js","/assets/schemas-BTxHZt_n.js","/assets/shared-tE52EgQc.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-B39DFGo3.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-B0KrsubD.js","/assets/ui-BpGBXluy.js","/assets/useActiveBook-DNV0IO-e.js","/assets/useCatalog-DUh6Wjx_.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-C9HNHWFL.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-B9I4rDOz.js","/assets/useTickerRows-DeIrqOVf.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
