const CACHE = "kasbbook-b8b857d55c";
const FILES = ["/assets/BookRequired-Dc19FRzr.js","/assets/BottomSheet-vWjS-bAX.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-DvwTyJ1D.js","/assets/ConfirmDialog-DF91lt4p.js","/assets/CurrencyPicker-BUuQCThI.js","/assets/DataTable-DCA_l8YR.js","/assets/DateTimeField-Ddt3PJSS.js","/assets/DayField-DWgEYGIf.js","/assets/DeveloperFooter-CiDtPLBx.js","/assets/ErrorState-Bqp-SGj-.js","/assets/FilterChips-CLk90K_b.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-DzWOkr4n.js","/assets/InstallButton-DRfmBGHQ.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-BzSusUcJ.js","/assets/ManageTabs-BE75oWSl.js","/assets/Modal-EvxYrTjd.js","/assets/Notice-C6eypi3p.js","/assets/PageHeader-Cp5bvMaf.js","/assets/PayrollPage-DJcwDHnK.js","/assets/ProfileForm-DlX6mTko.js","/assets/SearchBox-BZ0bhL0h.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-DYYcsErS.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/StatusChip-CxgP5wW1.js","/assets/SwitchField-Cm_UvvwA.js","/assets/TextField-CTQsnOwi.js","/assets/_app-K9rclZSH.js","/assets/_app.account-PKOjcYz_.js","/assets/_app.books-C5EP60x0.js","/assets/_app.index-BifOkldq.js","/assets/_app.manage-Brdopz3f.js","/assets/_app.more-vCmlLbE-.js","/assets/_app.planning-sbE_KpYc.js","/assets/_app.recurring-DTbM7vJH.js","/assets/_app.reports-BKj49qXW.js","/assets/_app.team-BM4Rfoq2.js","/assets/_app.team.funds-DtwCFT3R.js","/assets/_app.team.index-DY_6vxQL.js","/assets/_app.team.periods._periodId-VdxpBFUi.js","/assets/_app.team.periods.index-CXqMw_U4.js","/assets/_app.team.shares-DBJkkULT.js","/assets/_app.transactions-P9orR7vk.js","/assets/_app.wallet-BLvDvd6S.js","/assets/accent-COXX0DG9.js","/assets/auth-DREXw3hv.js","/assets/books-CPla_w1W.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-Cl7Ej7Ni.js","/assets/format-yhtkESqM.js","/assets/icons-DXTTqhFB.js","/assets/index-C1VN-MUD.js","/assets/index-CpNwd8dh.css","/assets/index.esm-C_jwQx2E.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-BDKldLpD.js","/assets/market-Bz2bDjHc.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-UznSsMyr.js","/assets/overlays-D2aUj7yy.js","/assets/payroll-DSE5tNIA.js","/assets/queryDefaults-GHX3EsHk.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules--gL9SpTM.js","/assets/schemas-CsJaBHif.js","/assets/shared-JdyZbDdo.js","/assets/status-C7SjyUYO.js","/assets/strings-CdubY5B9.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-S36ONgqU.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-W_g-V7bI.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-CKdd256Z.js","/assets/useCatalog-BKtuhVKi.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-Cliq7Oya.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-DlCDPYDh.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
