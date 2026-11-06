const CACHE = "kasbbook-0332112697";
const FILES = ["/assets/BookRequired-Cmm_TBZX.js","/assets/BottomSheet-C-7txVGb.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-DTEaKKQa.js","/assets/Collapsible-BzzZExyh.js","/assets/ConfirmDialog-CWaJemDP.js","/assets/CurrencyPicker-DgDd2Cll.js","/assets/DataTable-D6UAbRS4.js","/assets/DayField-Dm-fpid1.js","/assets/DeveloperFooter-Brkfa0nD.js","/assets/ErrorState-BTWGekqs.js","/assets/FilterChips-B6Tm_z1M.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-xNmXBqRn.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-B5m-R6z0.js","/assets/ManageTabs-bkWtbe_y.js","/assets/Modal-Cnp-1BL9.js","/assets/Notice-C2cxC46A.js","/assets/PayrollPage-BtwIOg_K.js","/assets/ProfileForm-tVbITiQT.js","/assets/SearchBox-WViX0kl8.js","/assets/SectionCard-DZkba2Za.js","/assets/SelectField-DnmtDRJK.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-CevUW5Fq.js","/assets/SwitchField-3EAv9i2N.js","/assets/Tabs-BWu-YYYj.js","/assets/TextField-CjHgMRQG.js","/assets/_app-BATJDb3L.js","/assets/_app.account-Dm1Zeslq.js","/assets/_app.books-CF6CEQrS.js","/assets/_app.capital-Cfn-mKaL.js","/assets/_app.index-DY_EgP7T.js","/assets/_app.manage-DWDSyE0i.js","/assets/_app.planning-C1RGP5nZ.js","/assets/_app.portfolio-BMQ_zXvx.js","/assets/_app.reports-DS1oEv7W.js","/assets/_app.team-1F5nnN3N.js","/assets/_app.team.funds-DWh5OPMP.js","/assets/_app.team.index-LF_VAmPf.js","/assets/_app.team.periods._periodId-CBSD6pEI.js","/assets/_app.team.periods.index-CAHzyg-W.js","/assets/_app.team.shares-BNluGtjo.js","/assets/_app.transactions-BC3KIJ5_.js","/assets/_app.wallet-Ldn4Idk1.js","/assets/accent-CyKc8f0i.js","/assets/auth-Dt6jsaDK.js","/assets/books-CcTBpX47.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-DeMthBPg.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-CM8ldiY9.js","/assets/icons-B7FYk1y3.js","/assets/index-BRbtBHEW.js","/assets/index-DG2mVbEc.css","/assets/index.esm-D2dr0UmC.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-TpBPPChu.js","/assets/market-P9J5oO4r.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CQNeutcJ.js","/assets/payroll-D4L6-rFa.js","/assets/progress-bar-DDdVo9fe.js","/assets/queryDefaults-BhajxXVZ.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-CzDwLv55.js","/assets/schemas-Di3lmkz1.js","/assets/shared-DhlDo1Du.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-gXg-5xLH.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-Cbw1Aypu.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-D-OOIXJE.js","/assets/useCatalog-BXVUgalH.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-Bs-66FhX.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-kPSJy2sG.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
