const CACHE = "kasbbook-70fc36a578";
const FILES = ["/assets/AttachmentsField-DhylDMnS.js","/assets/BookRequired-Ca5oGfvW.js","/assets/BottomSheet-4cSLw_Bv.js","/assets/Capital-BiqaSfG2.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-Bi4iE4oc.js","/assets/Collapsible-z1lOd6Gq.js","/assets/ConfirmDialog-0U9AI1hB.js","/assets/CurrencyPicker-ptBnDe5R.js","/assets/DataTable-DKWwoOBI.js","/assets/DayField-_Az2G-m8.js","/assets/DeveloperFooter-BeFgRtZ5.js","/assets/ErrorState-BjolBJ6y.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-C8n8l-Rv.js","/assets/ManageTabs-BVvqhSCK.js","/assets/Modal-Cqt8RJwp.js","/assets/Notice-BKDWlGRM.js","/assets/PayrollPage-6IqLDkJK.js","/assets/ProfileForm-BAOFUZqX.js","/assets/SearchBox-CoqY3iVo.js","/assets/SectionCard-CoOts3ON.js","/assets/SelectField-_MxNNR8g.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-CRlh-yIl.js","/assets/SwitchField-BRRWZLq_.js","/assets/Tabs-BlDwH4fn.js","/assets/TextField-rHcNILXF.js","/assets/_app-B2DAzAti.js","/assets/_app.account-CH2La8HS.js","/assets/_app.books-BOz7UzW-.js","/assets/_app.index-jf2EJjrt.js","/assets/_app.manage-BUTXJlQ3.js","/assets/_app.planning-CRkbWxVU.js","/assets/_app.portfolio-DhtM8sfR.js","/assets/_app.reports-BHFI3EYT.js","/assets/_app.team-BaFdVGmH.js","/assets/_app.team.funds-IULmViFE.js","/assets/_app.team.index-B7pT3fUs.js","/assets/_app.team.periods._periodId-B75Lcbnq.js","/assets/_app.team.periods.index-Boevp1Ti.js","/assets/_app.team.shares-CUfCOaVD.js","/assets/_app.transactions-BrkAZ59H.js","/assets/_app.wallet-bU4-BxGQ.js","/assets/accent-BQpkq87e.js","/assets/auth-DV2OkmdK.js","/assets/books-U7_dHtzj.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-Bo6dzUiL.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-BfW8z_jQ.js","/assets/index-BrecVvEy.css","/assets/index.esm-RZP8eJFx.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-C_62nSFG.js","/assets/market-DOGvbkn-.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-BaLLaIhB.js","/assets/payroll-DVIgBtMw.js","/assets/portfolio-Cmfcv0_4.js","/assets/queryDefaults--eHWl2yd.js","/assets/reports-Bai78n2y.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-DK59ybUE.js","/assets/schemas-By8sVlFd.js","/assets/shared-CaSK5PN2.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-BTVdZm45.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-CSGrsViO.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-fHiBxBmZ.js","/assets/useCatalog-BtRK-_MG.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-6qSbb1B3.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-gG9Ob2Vh.js","/assets/useTickerRows-CKzTEKM2.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
