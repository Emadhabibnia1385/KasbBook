const CACHE = "kasbbook-2e8ca69cdc";
const FILES = ["/assets/BookRequired-B1cCuRGl.js","/assets/BottomSheet-BqgPEx0B.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-C413l6Hh.js","/assets/Collapsible-DvwrmvTA.js","/assets/ConfirmDialog-CNMS0New.js","/assets/CurrencyPicker-CCXgSxuz.js","/assets/DataTable-CHonq8G-.js","/assets/DayField-BnzvvY_K.js","/assets/DeveloperFooter-BkGrVPWd.js","/assets/ErrorState-Ds-nfQH7.js","/assets/FilterChips-D5JC-zf0.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-CjVc_Fxk.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-CJdnOVlE.js","/assets/ManageTabs-yXmUhbFU.js","/assets/Modal-bShx22R_.js","/assets/Notice-CI5L0ppc.js","/assets/PayrollPage-DKTLF4-C.js","/assets/ProfileForm-DzXFAUH6.js","/assets/SearchBox-CEtUi9SM.js","/assets/SectionCard-D_B3HX-e.js","/assets/SelectField-iN_lBIDn.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-BMF0u9Xh.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-Bf6EXncT.js","/assets/SwitchField-CnFozbnW.js","/assets/Tabs-seJfCiKi.js","/assets/TextField-DqHrET1Y.js","/assets/_app-C8uYVcyw.js","/assets/_app.account-BCiCJ5Q8.js","/assets/_app.books-BbKYjRNF.js","/assets/_app.capital-XsxyiSHh.js","/assets/_app.index-D7ZO0oYX.js","/assets/_app.manage-iSPyWCuS.js","/assets/_app.planning-C_ygCMn6.js","/assets/_app.portfolio-BqYD54Sv.js","/assets/_app.reports-u9nOKiij.js","/assets/_app.team-BMzx3_hy.js","/assets/_app.team.funds-DeH9yVIA.js","/assets/_app.team.index-Bpi06l5T.js","/assets/_app.team.periods._periodId-v5SqxF5d.js","/assets/_app.team.periods.index-Ceht5fpY.js","/assets/_app.team.shares-Czd0wtw4.js","/assets/_app.transactions-C78Z1e_2.js","/assets/_app.wallet-C3BmOgLd.js","/assets/accent-DXQ6dzAw.js","/assets/auth-Jolpywyu.js","/assets/books-Dp13TaqA.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-ApSm2h7C.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-0lv4ODmU.js","/assets/format-yhtkESqM.js","/assets/icons-B7FYk1y3.js","/assets/index--uuo5dQO.css","/assets/index-BzYLrSNQ.js","/assets/index.esm-a3XE4icf.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-286UzZPQ.js","/assets/market-Cb23IDnh.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-DvjH1OGe.js","/assets/payroll--bkFIBQQ.js","/assets/progress-bar-999bbcb7.js","/assets/queryDefaults-BxurI3Di.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-pQKvyGVZ.js","/assets/schemas-BNM9DIJK.js","/assets/shared-DodlfLHL.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-C7jPG-Ia.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-BWMmg39f.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-B6xiJjZZ.js","/assets/useCatalog-jf4DVJ44.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-yONQXD0L.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-BtTvtcJf.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
