const CACHE = "kasbbook-929a482e9a";
const FILES = ["/assets/AttachmentsField-DO1AmHO_.js","/assets/BookRequired-BSKX8IAL.js","/assets/BottomSheet-B6XR72SV.js","/assets/Capital-CyLP417j.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-D33Vk16z.js","/assets/Collapsible-EiPgFAhW.js","/assets/ConfirmDialog-vgAKMYI5.js","/assets/CurrencyPicker-C60Fs3IK.js","/assets/DataTable-B8BhUXNM.js","/assets/DayField-Dljc_YeM.js","/assets/DeveloperFooter-D5eDTj4r.js","/assets/ErrorState-Bvx-pgDW.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-CscwKeYi.js","/assets/ManageTabs-ZjuxNaTE.js","/assets/Modal-jRq0KW8T.js","/assets/Notice-C9m0yqTA.js","/assets/PayrollPage-D8w0zAFU.js","/assets/ProfileForm-CJGmRhob.js","/assets/SearchBox-F_ApWuFH.js","/assets/SectionCard-DSymLAEL.js","/assets/SelectField-Dvpb3fLD.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-CWbVSyIA.js","/assets/SwitchField-CpAlcFi1.js","/assets/Tabs-DG9wovbQ.js","/assets/TextField-DVk8yaGZ.js","/assets/_app-54uho-5J.js","/assets/_app.account-bO5xWdJT.js","/assets/_app.books-DGbKlDpy.js","/assets/_app.index-BwaGw_w0.js","/assets/_app.manage-DpFbqmSO.js","/assets/_app.planning-CvZyMCwO.js","/assets/_app.portfolio-B_RrFknU.js","/assets/_app.reports-IOMh8a7L.js","/assets/_app.team-CG8GzO7L.js","/assets/_app.team.funds-Udm59WUq.js","/assets/_app.team.index-bvH4WwaE.js","/assets/_app.team.periods._periodId-DS8QEyLv.js","/assets/_app.team.periods.index-Ba8o3Ly1.js","/assets/_app.team.shares-DdydM1X1.js","/assets/_app.transactions-D5KjGlkk.js","/assets/_app.wallet-Bxa3J_Hq.js","/assets/accent-BCw0rjOQ.js","/assets/auth-06zMunwf.js","/assets/books-x6midh1n.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-wbfFFjPr.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-BZrQr9gO.css","/assets/index-D1voJr6e.js","/assets/index.esm-lUxmiU_3.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-Dz_uyA06.js","/assets/market-Bo1hkQUN.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-BVm3CFsD.js","/assets/payroll-DIwFajim.js","/assets/portfolio-C2nzvYBA.js","/assets/queryDefaults-D-NR9qI0.js","/assets/reports--7_3BuVw.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-BRTqu9ea.js","/assets/schemas-VotG86z5.js","/assets/shared-D4tJC9L0.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-Dj3pWK8s.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-D2uJbhDj.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-Dme-hgPe.js","/assets/useCatalog-C3mEDoe4.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-D9OXiJm3.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-CnZskYgb.js","/assets/useTickerRows-QEIYqAdA.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
