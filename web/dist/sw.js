const CACHE = "kasbbook-5afba2dc37";
const FILES = ["/assets/BookRequired-DOe7RoLW.js","/assets/BottomSheet-BJE6Xrcp.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BMv9M6FQ.js","/assets/Collapsible-Dx8gT-r_.js","/assets/ConfirmDialog-wybE1LCy.js","/assets/CurrencyPicker-CEjSv1lF.js","/assets/DataTable-CH-x1nxy.js","/assets/DayField-BgqQJwbj.js","/assets/DeveloperFooter-BufIHBno.js","/assets/ErrorState-BkKGZ0lT.js","/assets/FilterChips-B6Tm_z1M.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-DQtscms9.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-kvcIRjAy.js","/assets/ManageTabs-RzrPOOPj.js","/assets/Modal-Dm8mWDMK.js","/assets/Notice-CoMerhDG.js","/assets/PayrollPage-Dloqc0Bk.js","/assets/ProfileForm-BbiFI8h4.js","/assets/SearchBox-mVuuf31d.js","/assets/SectionCard-DQqFFCaw.js","/assets/SelectField-BnfAnZAQ.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-DuJoF0f7.js","/assets/SwitchField-BsJshPS1.js","/assets/Tabs-CYyYaSVx.js","/assets/TextField-BdiMpFXK.js","/assets/_app-BgGVaZuT.js","/assets/_app.account-hFNF0XKl.js","/assets/_app.books-BdyoSk5a.js","/assets/_app.capital-cZpNkWn_.js","/assets/_app.index-KoI6t3m5.js","/assets/_app.manage-BiKElHhH.js","/assets/_app.planning-DtoKbFf3.js","/assets/_app.portfolio-DhqmbvKY.js","/assets/_app.reports-D0yrtHSG.js","/assets/_app.team-D7kkOnCW.js","/assets/_app.team.funds-DQVs6Cwe.js","/assets/_app.team.index-CQoJzhEW.js","/assets/_app.team.periods._periodId-BcByVhe7.js","/assets/_app.team.periods.index-Bex0_5-U.js","/assets/_app.team.shares-DXepgkpQ.js","/assets/_app.transactions--K_La493.js","/assets/_app.wallet-Dur7xvBk.js","/assets/accent-DeLwumI0.js","/assets/auth-CEKAyaLt.js","/assets/books-CIPGDHo_.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-DR5q6KtE.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-dMvJ6MyH.js","/assets/icons-B7FYk1y3.js","/assets/index-DG2mVbEc.css","/assets/index-aImGkedK.js","/assets/index.esm-D9-INJUg.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-CoTHhw_W.js","/assets/market-DQamgRdc.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CKcfm_1-.js","/assets/payroll-zQkAI3WC.js","/assets/progress-bar-DDdVo9fe.js","/assets/queryDefaults-BPLtYmH6.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules--xHGn3qR.js","/assets/schemas-6ymZHodA.js","/assets/shared-3CN5Mcrn.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DRiVwB1Z.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-DmH9pUpt.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-B_G9M-Ep.js","/assets/useCatalog-CZqbEbql.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BHxqld8L.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-B-4wufMU.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
