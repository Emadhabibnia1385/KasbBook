const CACHE = "kasbbook-15a226080a";
const FILES = ["/assets/BookRequired-D-dkbYwW.js","/assets/BottomSheet-BK76GVhq.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BvUpa1_3.js","/assets/Collapsible-PrIePbpw.js","/assets/ConfirmDialog-PhwZOa2k.js","/assets/CurrencyPicker-BI8yKSU_.js","/assets/DataTable-CVTNDDKY.js","/assets/DayField-hc64YEBB.js","/assets/DeveloperFooter-DieeA6l9.js","/assets/ErrorState-rrTl4fvg.js","/assets/FilterChips-D5JC-zf0.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-B9xt99Pe.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-D4HcwTKf.js","/assets/ManageTabs-B2gUNfZp.js","/assets/Modal-DcVvMiOB.js","/assets/Notice-lm19LmdB.js","/assets/PayrollPage-DQcWxMTB.js","/assets/ProfileForm-DVIg5soo.js","/assets/SearchBox-BBtcJlEF.js","/assets/SectionCard-dldiCdDY.js","/assets/SelectField-2Ss5bSjc.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-BMF0u9Xh.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-DJFC0wqd.js","/assets/SwitchField-BCjnBkAc.js","/assets/Tabs-CHvcYjDk.js","/assets/TextField-_7LL6Szs.js","/assets/_app-IXBdDsVT.js","/assets/_app.account-BcggAWth.js","/assets/_app.books-D56eGxlU.js","/assets/_app.index-DMvIaVL4.js","/assets/_app.manage-_xTljYWL.js","/assets/_app.planning-B3upxUsd.js","/assets/_app.reports-D1B-vth0.js","/assets/_app.team-DAT88g1n.js","/assets/_app.team.funds-Dx3ajc5Z.js","/assets/_app.team.index-BEezv1_N.js","/assets/_app.team.periods._periodId-B5YWQLio.js","/assets/_app.team.periods.index-HT5g399R.js","/assets/_app.team.shares-DwhTzw6m.js","/assets/_app.transactions-DGsrjTGB.js","/assets/_app.wallet-JanoDuyL.js","/assets/accent-CTOSd9fj.js","/assets/auth-B6Bl9M5O.js","/assets/books-OQtMcsTj.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-C5mMG15J.js","/assets/format-yhtkESqM.js","/assets/icons-B7FYk1y3.js","/assets/index-BUzszqrr.css","/assets/index-CMh0xjdD.js","/assets/index.esm-DbHnUKC3.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-DRsX9nZM.js","/assets/market-B0lm07BQ.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-B9536bnG.js","/assets/payroll-DbagvwiF.js","/assets/queryDefaults-CiKRJnma.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-DKgfg42M.js","/assets/schemas--Z5bajFi.js","/assets/shared-dc_zL4BT.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DAWRrD10.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-C0NDtpOa.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-Cm_juX6i.js","/assets/useCatalog-P4DE4Pbk.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-nWV8LOpL.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-CxougK8A.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
