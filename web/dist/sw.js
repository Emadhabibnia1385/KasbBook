const CACHE = "kasbbook-fc527e71e8";
const FILES = ["/assets/AttachmentsField-BOW8c72E.js","/assets/BookRequired-X_RY_TuD.js","/assets/BottomSheet-pi0hYNko.js","/assets/Capital-BO2qMv4N.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-1qcLZEND.js","/assets/Collapsible-CGnBZjMI.js","/assets/ConfirmDialog-BKTdnNMj.js","/assets/CurrencyPicker-FsmOCVbb.js","/assets/DataTable-BXwHrnrF.js","/assets/DayField-olLnouK8.js","/assets/DeveloperFooter-BpT38gQe.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-Copq4p8v.js","/assets/ManageTabs-Qjyq6OlM.js","/assets/Modal-DSATTpNi.js","/assets/Notice-CvhyEyUw.js","/assets/PageHeader-Bv7ZPhro.js","/assets/PayrollPage-DzcPL57z.js","/assets/ProfileForm-CBPgsgAk.js","/assets/SearchBox-BAJlUIl2.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-2wGEuEGL.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-DvobWd9I.js","/assets/SwitchField-B1TOzzO4.js","/assets/Tabs-BoKfIw3I.js","/assets/TextField-DeeqRs18.js","/assets/_app-BYkzNhIO.js","/assets/_app.account-CUpfS4ES.js","/assets/_app.books-B1VgeLks.js","/assets/_app.index-BrDBVWG7.js","/assets/_app.manage-FAFBDUdK.js","/assets/_app.planning-BO3rtu6N.js","/assets/_app.portfolio-COhXxSKH.js","/assets/_app.reports-B3RzhDx9.js","/assets/_app.team-C1kF3x_G.js","/assets/_app.team.funds-CLBoyIB9.js","/assets/_app.team.index-B1V1Et85.js","/assets/_app.team.periods._periodId-DKYvMf4G.js","/assets/_app.team.periods.index-oK_hxcRZ.js","/assets/_app.transactions-BHdNXxPi.js","/assets/_app.wallet-BuxnCKOP.js","/assets/accent-BEhblUac.js","/assets/auth-Cuq5ghUi.js","/assets/books-CtJ3hUCi.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-BYU6CeD8.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-C6t7qI0_.js","/assets/index-DqQQLFie.css","/assets/index.esm-DecY0ffU.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-B_ur5GD7.js","/assets/market-B2syMhh-.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CIh9YqQ5.js","/assets/payroll-Bj9UibEE.js","/assets/portfolio-DSJQa0xV.js","/assets/queryDefaults-D6MWcH6O.js","/assets/reports-BvMt36Vt.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-BDB-zSQP.js","/assets/schemas-n4jwqWHl.js","/assets/shared-BeQdl5Ty.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DVY3caBf.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-BkAV5rvI.js","/assets/ui-DYYeGpHk.js","/assets/useActiveBook-DzmHipw5.js","/assets/useCatalog-C-ZmnuB3.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BAiFDEjn.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-CTscPN4T.js","/assets/useTickerRows-7ysPoDdZ.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
