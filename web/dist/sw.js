const CACHE = "kasbbook-f03b0438c2";
const FILES = ["/assets/AttachmentsField-BgebtcBJ.js","/assets/BookRequired-b1QlI2JR.js","/assets/BottomSheet-KXvjpQjY.js","/assets/BrandMark-DXgGgpA5.js","/assets/Capital-Bjyi7HJr.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-Ck2Dqe8a.js","/assets/Collapsible-D6pvYmSw.js","/assets/ConfirmDialog-Ds8Y2Ufc.js","/assets/CurrencyPicker-BceKXvxk.js","/assets/DataTable-B7R0G0hR.js","/assets/DayField-UzYjcN2I.js","/assets/DayPair-BWOZxC3z.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-DkARW6Ud.js","/assets/ManageTabs-BIlf5Fdx.js","/assets/Modal-B1XboCEG.js","/assets/Notice-CjlZK5xB.js","/assets/PageHeader-fB9Lg-UU.js","/assets/PayrollPage-Hc1FyGCK.js","/assets/ProfileForm-BKzb-x7Q.js","/assets/SearchBox-BmdtLukA.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-DyxoVO0h.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-BX4vYSH1.js","/assets/SwitchField-CMVlyFHt.js","/assets/Tabs-CBiU4rPI.js","/assets/TextField-I6F6KH1T.js","/assets/_app-B57MJktC.js","/assets/_app.account-6fd5Opdk.js","/assets/_app.books-DoRy6MIG.js","/assets/_app.index-w7cQQTCj.js","/assets/_app.manage-Sz4DGD6O.js","/assets/_app.planning-C0KLwCHe.js","/assets/_app.portfolio-DaU329bE.js","/assets/_app.reports-TAwwF76q.js","/assets/_app.team-D3gk-sfm.js","/assets/_app.team.funds-DpaghQI8.js","/assets/_app.team.index-CeDCBrDS.js","/assets/_app.team.periods._periodId-B8DhG3nH.js","/assets/_app.team.periods.index-CRBHLE-l.js","/assets/_app.transactions-B4KXxUdh.js","/assets/_app.wallet-D7Ytb0VR.js","/assets/accent-Bo-HGPgV.js","/assets/auth-EeDEv875.js","/assets/books-DstkMAb5.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-B0oeXbPs.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/format-y4m3bAct.js","/assets/icons-B7FYk1y3.js","/assets/index-CC_CXbGk.css","/assets/index-Ccgrc8J0.js","/assets/index.esm-BHojv0Tw.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-y7iwIqxy.js","/assets/market-CIx3yWGu.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CL4FNZ29.js","/assets/payroll-DNITnzzX.js","/assets/portfolio-Bq08AWw5.js","/assets/reports-BkbJU1hB.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-V3GTf08C.js","/assets/schemas-rNwUlHz7.js","/assets/shared-BXFF4o_Z.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-C9pzIE8i.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-CJQPM68-.js","/assets/ui-Bm9tkose.js","/assets/useActiveBook-BSsD5ebB.js","/assets/useCatalog-DFDrnA-h.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-sgziAjLE.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-BEZG12Xg.js","/assets/useTickerRows-BxBaPIzX.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
