const CACHE = "kasbbook-154281ec30";
const FILES = ["/assets/BookRequired-Cl62Pwyv.js","/assets/BottomSheet-BojHxwiY.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BBKqy6zt.js","/assets/Collapsible-BY81w3fy.js","/assets/ConfirmDialog-DUQp-roY.js","/assets/CurrencyPicker-dQ36MHf4.js","/assets/DataTable-DZopOI-p.js","/assets/DayField-DhdTy_JV.js","/assets/DeveloperFooter-BZocbQzP.js","/assets/ErrorState-InFi_Nh2.js","/assets/FilterChips-CLk90K_b.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-B4FbuPxx.js","/assets/InstallButton-Do089PWH.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-B4X1xwYT.js","/assets/ManageTabs-Ct2lWjwZ.js","/assets/Modal-JgtPkEDc.js","/assets/Notice-vkAO-Np_.js","/assets/PageHeader-DeXGV7x3.js","/assets/PayrollPage-_SKUwFEI.js","/assets/ProfileForm-D215eRs8.js","/assets/SearchBox-GPgUbtjF.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-C3ePyR3T.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-q2f627gR.js","/assets/SwitchField-CWKhZSOL.js","/assets/Tabs-CsbveKbv.js","/assets/TextField-DrTl-99h.js","/assets/_app-Cdl_lJPR.js","/assets/_app.account-R-PFkfj5.js","/assets/_app.books-C-skRybC.js","/assets/_app.index-CyCsyE1e.js","/assets/_app.manage-BZk1p1vQ.js","/assets/_app.more-CbmCsWvb.js","/assets/_app.planning-DL0P4JRY.js","/assets/_app.reports-D9yysPbm.js","/assets/_app.team-Bhie8cny.js","/assets/_app.team.funds-D_5bhnYk.js","/assets/_app.team.index-BPHlXAgO.js","/assets/_app.team.periods._periodId-OlXEgjwn.js","/assets/_app.team.periods.index-BGUZMhQ8.js","/assets/_app.team.shares-BmpT0WXb.js","/assets/_app.transactions-BArwv2bP.js","/assets/_app.wallet-CZ7hoQbG.js","/assets/accent-DoSFsMt1.js","/assets/auth-C5qSkRSE.js","/assets/books-ywu6gtoZ.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-DzmmmnkB.js","/assets/format-yhtkESqM.js","/assets/icons-DXTTqhFB.js","/assets/index-B3WeNaQY.js","/assets/index-CrIo1sSw.css","/assets/index.esm-C3LN_dba.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-x8geYEmG.js","/assets/market-DzfqvZ9O.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-BmCNq2by.js","/assets/overlays-NLGcG7db.js","/assets/payroll-BlnD2SA4.js","/assets/queryDefaults-BXiCC3bJ.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-Rd8lY3UV.js","/assets/schemas-BfQL4PRm.js","/assets/shared-ngYd7rNM.js","/assets/status-C7SjyUYO.js","/assets/strings-CdubY5B9.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-B-rrqsGF.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-CWEog5Xu.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-xnHrasIb.js","/assets/useCatalog-CX9RRrT2.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-aJMvtg0M.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-CX6MCQ7-.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
