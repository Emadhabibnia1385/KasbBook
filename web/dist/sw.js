const CACHE = "kasbbook-d465d26d15";
const FILES = ["/assets/AttachmentsField-aMwTso-R.js","/assets/BookRequired-DvZA9uZb.js","/assets/BottomSheet-CAfnOtbk.js","/assets/Capital-Cqe83Fv6.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BC50CMoD.js","/assets/Collapsible-CR_njUwF.js","/assets/ConfirmDialog-B5jxsxS2.js","/assets/CurrencyPicker-DSX3PRp0.js","/assets/DataTable-DGR-a_d3.js","/assets/DayField-D1Cg_8A4.js","/assets/DayPair-1aTbFUFS.js","/assets/DeveloperFooter-DE6Z9RPe.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-ZjgFcOrP.js","/assets/ManageTabs-CsRZxlyu.js","/assets/Modal-MNTUG4pI.js","/assets/Notice-By43EFRF.js","/assets/PageHeader-l9QRaPpw.js","/assets/PayrollPage-YTR-6vMC.js","/assets/ProfileForm-CVblH17d.js","/assets/SearchBox-Dzgce0Sf.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-B0d01rv9.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-BtTh8El7.js","/assets/SwitchField-A_v90ILp.js","/assets/Tabs-EcBO07tT.js","/assets/TextField-BviEZ15_.js","/assets/_app-uYlLrN2U.js","/assets/_app.account-BUnYXMSQ.js","/assets/_app.books-CInBhqNV.js","/assets/_app.index-DX_8HO5g.js","/assets/_app.manage-DCFmHgHW.js","/assets/_app.planning-Bkub504H.js","/assets/_app.portfolio-CtRALhNW.js","/assets/_app.reports-Bbr-BQSw.js","/assets/_app.team-DaqMNsYy.js","/assets/_app.team.funds-B1MSEpu_.js","/assets/_app.team.index-fmR2U9rt.js","/assets/_app.team.periods._periodId-WgEgMmqT.js","/assets/_app.team.periods.index-DMY3-LWn.js","/assets/_app.transactions-D4VOkyre.js","/assets/_app.wallet-BJ0v1mBr.js","/assets/accent-B_gg_7AA.js","/assets/auth-BiWIsLMz.js","/assets/books-CxKA95Au.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-D7KJdqDZ.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/icons-B7FYk1y3.js","/assets/index-DqQQLFie.css","/assets/index-DwGQzmzW.js","/assets/index.esm-CUDcZjwi.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-CYA30W3q.js","/assets/market-eo9kWgrI.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-04Db8R9J.js","/assets/payroll-BcXc4DOd.js","/assets/portfolio-D42M1Ogg.js","/assets/queryDefaults-DNUbaxOa.js","/assets/reports-DNq5PAxA.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-BrNKHW4j.js","/assets/schemas-nkgFoX1p.js","/assets/shared-D6sPPSwp.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DnOYZFYO.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-DaDg10y0.js","/assets/ui-Pu-NApro.js","/assets/useActiveBook-B83oDYMs.js","/assets/useCatalog-D04zIdxC.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BXVRRc8o.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-3rqyPdEt.js","/assets/useTickerRows-5_iY61mu.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
