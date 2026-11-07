const CACHE = "kasbbook-88d4689e76";
const FILES = ["/assets/AttachmentsField-VIDs7aNU.js","/assets/BookRequired-DxN34Y38.js","/assets/BottomSheet-hMJt1dUQ.js","/assets/Capital-Y9Y3Lynu.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BsS50S86.js","/assets/Collapsible-ZfjC6YoG.js","/assets/ConfirmDialog-CDdxqgsB.js","/assets/CurrencyPicker-DzOM_tXf.js","/assets/DataTable-B089pD-s.js","/assets/DayField-B9BNzC4R.js","/assets/DeveloperFooter-DCJVifTD.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-D2IIJaWn.js","/assets/ManageTabs-BMVq1bW6.js","/assets/Modal-D1co9yM3.js","/assets/Notice-BdqrR29x.js","/assets/PageHeader-DCy-QF1b.js","/assets/PayrollPage-jk3QULAD.js","/assets/ProfileForm-CaZzuvh1.js","/assets/SearchBox-DvkONNza.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-C8Crnx1n.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-CaLW9R29.js","/assets/SwitchField-ZqNJ73Do.js","/assets/Tabs-CqdbvZVw.js","/assets/TextField-9Nlim2p1.js","/assets/_app-CuKWMcn6.js","/assets/_app.account-ihWIp6rB.js","/assets/_app.books-D2vxIHrr.js","/assets/_app.index-DJoReaEW.js","/assets/_app.manage-Cj_nYkUV.js","/assets/_app.planning-CjIxLxIT.js","/assets/_app.portfolio-BGQQa-NW.js","/assets/_app.reports-BGSwOJV2.js","/assets/_app.team-Cr1866nm.js","/assets/_app.team.funds-rpWQMdon.js","/assets/_app.team.index-CNsuAyzd.js","/assets/_app.team.periods._periodId-5kvNEDFg.js","/assets/_app.team.periods.index-B6BAwPC1.js","/assets/_app.transactions-v3bWsPzY.js","/assets/_app.wallet-CCc0u0X4.js","/assets/accent-CDwEQCdc.js","/assets/auth-DkqKyO2x.js","/assets/books-BkPoqwfm.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-BNx2-dU6.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-CzN-rA6j.js","/assets/index-DqQQLFie.css","/assets/index.esm-CFhwVCq7.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-D8HFhvxF.js","/assets/market-BuoQiVro.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CPP6fmGI.js","/assets/payroll-HY7CdGyH.js","/assets/portfolio-C9nTSqk7.js","/assets/queryDefaults-CSi3EUVj.js","/assets/reports-C0p3DCT_.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-Y8ICvKcb.js","/assets/schemas-CH94Lu_M.js","/assets/shared-DIrl3G6E.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-jjmFplfy.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-CeLNfXfA.js","/assets/ui-DfU1P8na.js","/assets/useActiveBook-mY4OqEWH.js","/assets/useCatalog-CPGxO32S.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BE9V5i-R.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-Xc_obUtt.js","/assets/useTickerRows-BIPJ_2KU.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
