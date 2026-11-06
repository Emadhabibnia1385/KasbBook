const CACHE = "kasbbook-9662fa0199";
const FILES = ["/assets/BookRequired-Dxe6eTHS.js","/assets/BottomSheet-CaktaIW7.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-COxR9n-l.js","/assets/ConfirmDialog-Djnr7XJf.js","/assets/CurrencyPicker-CYzgpMb8.js","/assets/DataTable-Rfw7aKlS.js","/assets/DateTimeField-CAc-Psgd.js","/assets/DayField-COQeTUn2.js","/assets/DeveloperFooter-BdjhZftc.js","/assets/ErrorState-BG9iUqTc.js","/assets/FilterChips-CLk90K_b.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-CBDJd0dS.js","/assets/InstallButton-DU2_4EpY.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-bwLi9rJC.js","/assets/ManageTabs-C50oBbVj.js","/assets/Modal-B8O3llGy.js","/assets/Notice-K3zRYuJQ.js","/assets/PageHeader-BWZT0q-1.js","/assets/PayrollPage-4Ru6qzyV.js","/assets/ProfileForm-BOd5ssxF.js","/assets/SearchBox-BSFa9BmO.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-CJdjmmJk.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/StatusChip-uMoYCTRi.js","/assets/SwitchField-Bk3K0RI-.js","/assets/TextField-5TrxGxP3.js","/assets/_app-BfHD7ZAg.js","/assets/_app.account-DLZkUDyA.js","/assets/_app.books-Dq0aCPwN.js","/assets/_app.index-DXXaGYxn.js","/assets/_app.manage-DtCmtPmD.js","/assets/_app.more-Awl3cDtK.js","/assets/_app.planning-BsnbDqfe.js","/assets/_app.recurring-DAwWt0Ye.js","/assets/_app.reports-DTpKoN78.js","/assets/_app.team-DGHxlo7w.js","/assets/_app.team.funds-BnrlhrDV.js","/assets/_app.team.index-CxyTUHdp.js","/assets/_app.team.periods._periodId-D5IcbIuh.js","/assets/_app.team.periods.index-BYFRaFUR.js","/assets/_app.team.shares-Bn-eNXMf.js","/assets/_app.transactions-C9ryfwrS.js","/assets/_app.wallet-DzqmMK69.js","/assets/accent-BhazgEbe.js","/assets/auth-dB031h90.js","/assets/books-DivPYYve.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-Cwp_5WnK.js","/assets/format-yhtkESqM.js","/assets/icons-DXTTqhFB.js","/assets/index-BkUApQ2x.js","/assets/index-Buhjynv7.css","/assets/index.esm-BydkAEvf.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-B4AE1fQS.js","/assets/market-D5XRfaeG.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-DYz_uqxG.js","/assets/overlays-C_JiFLcu.js","/assets/payroll-BLSjSg_O.js","/assets/queryDefaults-CPvbWEBZ.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-D6N3I0WL.js","/assets/schemas-DUvLi2c1.js","/assets/shared-CJ66Odt4.js","/assets/status-C7SjyUYO.js","/assets/strings-CdubY5B9.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-Cfd8Cpil.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-CgNkm3_K.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-CJR-oUrq.js","/assets/useCatalog-qb8xpWyh.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-wfm7mUuk.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-DP5m_0fi.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
