const CACHE = "kasbbook-b7046af68b";
const FILES = ["/assets/BookRequired-1R4NjIqb.js","/assets/BottomSheet-SPuikLSD.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-3kRKdcmh.js","/assets/Collapsible-CeinjpQk.js","/assets/ConfirmDialog-KWPhgemh.js","/assets/CurrencyPicker-BP5qPEyW.js","/assets/DataTable-CC4vA98j.js","/assets/DayField-BCM4NoP4.js","/assets/DeveloperFooter-BqyhV-FR.js","/assets/ErrorState-B7DTODUQ.js","/assets/FilterChips-B6Tm_z1M.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-DnwH64JR.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-CaFkeny8.js","/assets/ManageTabs-uO9aOLQ7.js","/assets/Modal-BIE72NS7.js","/assets/Notice-grX4ZJLB.js","/assets/PayrollPage-Bjq4UitC.js","/assets/ProfileForm-BYz5BHZ8.js","/assets/SearchBox-D3MlJi7Y.js","/assets/SectionCard-PqGcTcyJ.js","/assets/SelectField-Btyf33NI.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-vHv0xOhu.js","/assets/SwitchField-B8lU7iCb.js","/assets/Tabs-BhMfal4d.js","/assets/TextField-U1yNK7ir.js","/assets/_app-euBr08QJ.js","/assets/_app.account-Dnyz9-Cl.js","/assets/_app.books-DbI5e6LF.js","/assets/_app.capital-0ntozvr7.js","/assets/_app.index-CDQjdsJF.js","/assets/_app.manage-CmcmsUcF.js","/assets/_app.planning-ChXjHYb-.js","/assets/_app.portfolio-Dy4yPlba.js","/assets/_app.reports-BFSxzdHm.js","/assets/_app.team-gsXhz-2G.js","/assets/_app.team.funds-1XEcty2G.js","/assets/_app.team.index-BeJgsAAm.js","/assets/_app.team.periods._periodId-DHg68u4m.js","/assets/_app.team.periods.index-BkOMnF7q.js","/assets/_app.team.shares-CHvdQhzx.js","/assets/_app.transactions-BGGVhvbW.js","/assets/_app.wallet-QdrtaCiP.js","/assets/accent-BBu6nrC3.js","/assets/auth-CV3XxXX6.js","/assets/books-Dh11w4Tl.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-_DJZuIdK.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-BGrlrLal.js","/assets/icons-B7FYk1y3.js","/assets/index-BvraoJ74.css","/assets/index-lnnFWJo4.js","/assets/index.esm-DGOOlnlE.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-DVv604-W.js","/assets/market-G5J0PRCD.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-Hf2VxJMz.js","/assets/payroll-l-4kL67V.js","/assets/progress-bar-DDdVo9fe.js","/assets/queryDefaults-DirOwv6y.js","/assets/reports-DiNmtLc7.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-BqOKw8YC.js","/assets/schemas-B4Gk06R-.js","/assets/shared-BzUCoe1-.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-W_G9c9rn.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-BeDRCKoj.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-C6bb4Vwd.js","/assets/useCatalog-CgyUHuHF.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-CjpCumvo.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-Bja_GM1e.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
