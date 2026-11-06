const CACHE = "kasbbook-90f4eb443f";
const FILES = ["/assets/BookRequired-BXluhxU2.js","/assets/BottomSheet-zhsTvyY3.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-LZXFI4vQ.js","/assets/Collapsible-B8OePdCJ.js","/assets/ConfirmDialog-BzBzdhi2.js","/assets/CurrencyPicker-B9RjIFz6.js","/assets/DataTable-CGv6AIPp.js","/assets/DayField-6bUQHOU-.js","/assets/DeveloperFooter-RzRY64jS.js","/assets/ErrorState-qQw6CUKh.js","/assets/FilterChips-D5JC-zf0.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-DMVgRN-c.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-Cn7_6-6C.js","/assets/ManageTabs-C5nvAe8i.js","/assets/Modal-CVcaycyt.js","/assets/Notice-G7DJxbbL.js","/assets/PayrollPage-MaELvHrB.js","/assets/ProfileForm-DLjQ5hMI.js","/assets/SearchBox-B5h_dmjm.js","/assets/SectionCard-DOoQIBGI.js","/assets/SelectField-DsRwrlTO.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-BMF0u9Xh.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-JaZ9jXIh.js","/assets/SwitchField-DGex6cR6.js","/assets/Tabs-CmOUZroo.js","/assets/TextField-CkIgPnpe.js","/assets/_app-BGo2Yc-v.js","/assets/_app.account-DvAVkIJF.js","/assets/_app.books-D8KAkWSZ.js","/assets/_app.capital-CyW_OtHA.js","/assets/_app.index-NTLqaOPs.js","/assets/_app.manage-DZBdzY5h.js","/assets/_app.planning-gw_4X-f5.js","/assets/_app.reports-z9gRjloi.js","/assets/_app.team-G3EdOxP_.js","/assets/_app.team.funds-B86-BT1V.js","/assets/_app.team.index-Di_iAs0D.js","/assets/_app.team.periods._periodId-CJN0O-H1.js","/assets/_app.team.periods.index-B-NsSIyV.js","/assets/_app.team.shares-B4TZo6jv.js","/assets/_app.transactions-BYH5WPFj.js","/assets/_app.wallet-Dgm9fQrt.js","/assets/accent-Ce-dv982.js","/assets/auth-CG_rvKpJ.js","/assets/books-mBpZvEkX.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-COz4XQtq.js","/assets/format-yhtkESqM.js","/assets/icons-B7FYk1y3.js","/assets/index-B4AjDI7-.js","/assets/index-Pe4bkMhd.css","/assets/index.esm-C8ZGU9JO.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-kgd2Js7b.js","/assets/market-Duc3yAuc.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-C1PEj0oE.js","/assets/payroll-DauEZQpF.js","/assets/progress-bar-999bbcb7.js","/assets/queryDefaults-BUZ7UgZg.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-Df8QdFSW.js","/assets/schemas-CQ1CuvxR.js","/assets/shared-B_8JLsg-.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-Bh_hPdpp.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-1aToPsyS.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-Vavmux2b.js","/assets/useCatalog-rA6_Bh_r.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-CgFI0Ip4.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-2ed08jig.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
