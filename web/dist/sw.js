const CACHE = "kasbbook-b00df69518";
const FILES = ["/assets/BookRequired-xPT0YAbQ.js","/assets/BottomSheet-WDeZFeQb.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-rzLkVrDA.js","/assets/Collapsible-RODfRoQI.js","/assets/ConfirmDialog-CrHlWOe5.js","/assets/CurrencyPicker-BoPdhZLA.js","/assets/DataTable-BJk6zIxN.js","/assets/DayField-kwySa6wK.js","/assets/DeveloperFooter-DBaZHyMt.js","/assets/ErrorState-BKmGqSK0.js","/assets/FilterChips-B6Tm_z1M.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-BE0sSv2e.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-Cl4RrKng.js","/assets/ManageTabs-BR1KcbJa.js","/assets/Modal-C_Ad_kuu.js","/assets/Notice-FcxZFj45.js","/assets/PayrollPage-D24vH4bg.js","/assets/ProfileForm-Bq-t36GW.js","/assets/SearchBox-DIlK3awU.js","/assets/SectionCard-DpiAsmh3.js","/assets/SelectField-0qM4pGZ2.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-yNFg24ug.js","/assets/SwitchField-Dvy9Iy22.js","/assets/Tabs-DPIoiv0C.js","/assets/TextField-eKqIxQPE.js","/assets/_app-CHLFXTRD.js","/assets/_app.account-1BGZq7Un.js","/assets/_app.books-DnEvsOxv.js","/assets/_app.capital-CB4wXRBV.js","/assets/_app.index-CPJwktPJ.js","/assets/_app.manage-hy6bXsAW.js","/assets/_app.planning-C5urc7MI.js","/assets/_app.portfolio--B6NHGqV.js","/assets/_app.reports-CD1aeAeD.js","/assets/_app.team-Pk1mEoPF.js","/assets/_app.team.funds-COPCU1Vr.js","/assets/_app.team.index-UHfRAKfZ.js","/assets/_app.team.periods._periodId-B4QcKsx0.js","/assets/_app.team.periods.index-CHRrpimU.js","/assets/_app.team.shares-C79t1Uz0.js","/assets/_app.transactions-D2t1TKlF.js","/assets/_app.wallet-D44Bvi_K.js","/assets/accent-k1XXrX-e.js","/assets/auth-6QltI12j.js","/assets/books-B47t4YyG.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-DIYnkUsx.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-AeUpnzTS.js","/assets/icons-B7FYk1y3.js","/assets/index-BaxnuT4W.js","/assets/index-BvraoJ74.css","/assets/index.esm-Xq5oNYgy.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-HNowipva.js","/assets/market-CL3w7YCi.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-B-tH7kx5.js","/assets/payroll-CRjYTtn5.js","/assets/progress-bar-DDdVo9fe.js","/assets/queryDefaults-CkXmH6Na.js","/assets/reports-DybgFOmH.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-D4s176V1.js","/assets/schemas-wsdD-7x8.js","/assets/shared-HFaOvYYH.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-C548m2-0.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-O6QcN8Yj.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-BkySjFQ9.js","/assets/useCatalog-DGr4PUNj.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-CDkla66o.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-CCiKXqEr.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
