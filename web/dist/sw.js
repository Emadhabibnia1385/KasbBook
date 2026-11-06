const CACHE = "kasbbook-b45488d30b";
const FILES = ["/assets/BookRequired-Dj4LYTuV.js","/assets/BottomSheet-DR528TVw.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BqvTAiLs.js","/assets/ConfirmDialog-DVJevgD_.js","/assets/CurrencyPicker-CthJ96-o.js","/assets/DataTable-DNuOnIiw.js","/assets/DayField-BMF__MWG.js","/assets/DeveloperFooter-Dz5MFJHY.js","/assets/ErrorState-CRj59Tqa.js","/assets/FilterChips-CLk90K_b.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-Dwihu_3v.js","/assets/InstallButton-BJk93Udd.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-D1maCBV9.js","/assets/ManageTabs-D06R-ghG.js","/assets/Modal-BOCAXY-v.js","/assets/Notice-3DNnFi7I.js","/assets/PageHeader-BpkPCbUV.js","/assets/PayrollPage-BpOUidg8.js","/assets/ProfileForm-DgmPYT2i.js","/assets/SearchBox-C_wsMg4Z.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-CZKwMKvT.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/StatusChip-B-MDtpEi.js","/assets/SwitchField-BvkN3NDP.js","/assets/Tabs-HpC7jxXd.js","/assets/TextField-BNoCsr9O.js","/assets/_app-CshUBYm8.js","/assets/_app.account-3Gu-imeX.js","/assets/_app.books-C2h2aCEX.js","/assets/_app.index-CGKfG7_V.js","/assets/_app.manage-BiwJDNAk.js","/assets/_app.more-CH84AxlN.js","/assets/_app.planning-DaOiFt1c.js","/assets/_app.reports-DsKNfQDR.js","/assets/_app.team-C_WH_dKy.js","/assets/_app.team.funds-Cntsf94T.js","/assets/_app.team.index-kwlZzWkH.js","/assets/_app.team.periods._periodId-BXjTTeS5.js","/assets/_app.team.periods.index-BHXJ5fZW.js","/assets/_app.team.shares-ConGcbuu.js","/assets/_app.transactions-DC-9Wl7z.js","/assets/_app.wallet-CwOdsalD.js","/assets/accent-BMp50BwT.js","/assets/auth-BxbRno29.js","/assets/books-CvkuSaTt.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-BKQVnS-x.js","/assets/format-yhtkESqM.js","/assets/icons-DXTTqhFB.js","/assets/index-C0I3L4b9.css","/assets/index-CyP3n7Y7.js","/assets/index.esm-uarSz87f.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-C64hYgwp.js","/assets/market-CnYstHLQ.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CDzZYEhv.js","/assets/overlays-DeRAM7XQ.js","/assets/payroll-B_N-yABC.js","/assets/queryDefaults-BDWFA3_X.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-CZlFQrjE.js","/assets/schemas-CtUlhQOx.js","/assets/shared-MdkJhpzA.js","/assets/status-C7SjyUYO.js","/assets/strings-CdubY5B9.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-CL5NuFVk.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-DkU9_7wH.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-C0CzjRri.js","/assets/useCatalog-D-nHf5br.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-LUaZuXlK.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-BLenKqb9.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
