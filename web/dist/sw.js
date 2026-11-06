const CACHE = "kasbbook-7b71b2bfb9";
const FILES = ["/assets/AttachmentsField-D_z_hVTr.js","/assets/BookRequired-CVZt8cjs.js","/assets/BottomSheet-OYnSmFge.js","/assets/Capital-DLTEL0ig.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BQMwkFDt.js","/assets/Collapsible-CZdzX12K.js","/assets/ConfirmDialog-BZgyRh7p.js","/assets/CurrencyPicker-CjpjeJAS.js","/assets/DataTable-pr2VbU3s.js","/assets/DayField-BasjMcdu.js","/assets/DeveloperFooter-B7gHuT5t.js","/assets/ErrorState-nKhuRt2f.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-DPm5WpzB.js","/assets/ManageTabs-CDDFAwbp.js","/assets/Modal-C_ojMF6Q.js","/assets/Notice-OO4mfFbC.js","/assets/PayrollPage-DC1WXrQY.js","/assets/ProfileForm-BjtENj9v.js","/assets/SearchBox-u66DENAQ.js","/assets/SectionCard-B47d-EgL.js","/assets/SelectField-BhOZO3eG.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-jnO-7AtH.js","/assets/SwitchField-DUTD8S6i.js","/assets/Tabs-RgqhPY7J.js","/assets/TextField-D0j11bRr.js","/assets/_app-DGQwhmld.js","/assets/_app.account-DJJvLHup.js","/assets/_app.books-BXwdBVMq.js","/assets/_app.index-D25Fxybh.js","/assets/_app.manage-9fsaBmKb.js","/assets/_app.planning-D5ayJkHa.js","/assets/_app.portfolio-C5DVad1B.js","/assets/_app.reports-MvsyNHtd.js","/assets/_app.team-BiGT8rac.js","/assets/_app.team.funds-CRPsQDOb.js","/assets/_app.team.index-SD7zVjlO.js","/assets/_app.team.periods._periodId-ivHuu7lP.js","/assets/_app.team.periods.index-DdRIZ-oR.js","/assets/_app.team.shares-DZY9VBnG.js","/assets/_app.transactions-BWGTjOMz.js","/assets/_app.wallet-k38gE5sL.js","/assets/accent-BJ0xhj1l.js","/assets/auth-D5jQDcNC.js","/assets/books-F9kwp7N1.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-x-DgxKa-.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-BrecVvEy.css","/assets/index-ClJaAgW-.js","/assets/index.esm--zAcLGoa.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-GxQa-ID1.js","/assets/market-tZ_LnDmC.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-BrnU3Zhq.js","/assets/payroll-D5h3lTiE.js","/assets/portfolio-BbtkSvgI.js","/assets/queryDefaults-fv4JSfod.js","/assets/reports-Emw_apca.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-hf6gQM4a.js","/assets/schemas-CDyg_gnV.js","/assets/shared-BrqJUqvN.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-LMTtE7Wa.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-D-_-B126.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-CGWUKoRp.js","/assets/useCatalog-CvJZg9AD.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BiDNQZTq.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-Dl7pBdIz.js","/assets/useTickerRows-CV4WrCNa.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
