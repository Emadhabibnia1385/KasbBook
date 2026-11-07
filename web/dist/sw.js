const CACHE = "kasbbook-63c5cfcc64";
const FILES = ["/assets/AttachmentsField-B3O29QJu.js","/assets/BookRequired-BLQsQ6Vh.js","/assets/BottomSheet-C9JXy9Fi.js","/assets/Capital-C-yo1OAs.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-CGd5ZH02.js","/assets/Collapsible-DuUtS1SF.js","/assets/ConfirmDialog-DfCBz9w4.js","/assets/CurrencyPicker-DI9wjj2e.js","/assets/DataTable-1SsSCeyT.js","/assets/DayField-CGThcrZu.js","/assets/DeveloperFooter-DygJCtPy.js","/assets/ErrorState-ChqrCIWB.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-mbV0sbGw.js","/assets/ManageTabs-BR3BLsPF.js","/assets/Modal-D227RRdA.js","/assets/Notice-CzWrqDHO.js","/assets/PayrollPage-qLtWKdLo.js","/assets/ProfileForm-WnhuczIl.js","/assets/SearchBox-B4J_8AF3.js","/assets/SectionCard-BU5rd_DV.js","/assets/SelectField-gHApQ9qv.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-XrmOvK2W.js","/assets/SwitchField-BtfzPj7i.js","/assets/Tabs-DuSqbyhl.js","/assets/TextField-C2meP_9M.js","/assets/_app-NGkljdZw.js","/assets/_app.account-BrxJ2MIs.js","/assets/_app.books-DOs_55tM.js","/assets/_app.index-DBhz6fyW.js","/assets/_app.manage-Ba4AaYPc.js","/assets/_app.planning-v0LdT85M.js","/assets/_app.portfolio-Bqi1vfEg.js","/assets/_app.reports-Cx1ikLwe.js","/assets/_app.team-C5sRyXZX.js","/assets/_app.team.funds-Dnj6kgpZ.js","/assets/_app.team.index-DZSuwMkm.js","/assets/_app.team.periods._periodId-CFDZfzRk.js","/assets/_app.team.periods.index-D2CPFd0q.js","/assets/_app.team.shares--255m-zc.js","/assets/_app.transactions-DOJ5rY8V.js","/assets/_app.wallet-BUlNVIES.js","/assets/accent-DlW72cxg.js","/assets/auth-BE5UZ18z.js","/assets/books-BcwKQWvu.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-kjWOsY_J.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index--6J_GcW3.css","/assets/index-B78magJA.js","/assets/index.esm-Bltpo00k.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-BcZ6dfn_.js","/assets/market-TXYmrJx_.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-C0t-HOS-.js","/assets/payroll-CaKtyAzL.js","/assets/portfolio-DVsDjY-B.js","/assets/queryDefaults-B7wgHRaR.js","/assets/reports-cJzN5eWl.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-D-G-Oks7.js","/assets/schemas-CL_9v8ki.js","/assets/shared-B5cc_iZE.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DNylo3JA.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-COS3wori.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-CxhNewOq.js","/assets/useCatalog-bPbXkFtK.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BuG5QNE8.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-4HYbX4Uy.js","/assets/useTickerRows-4cxRdf5z.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
