const CACHE = "kasbbook-8ba4eaf9eb";
const FILES = ["/assets/AttachmentsField-D72f-baL.js","/assets/BookRequired-B033Dz9O.js","/assets/BottomSheet-DKwXlxi9.js","/assets/Capital-DzwT-fyG.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-rCM2UTgs.js","/assets/Collapsible-N2DMRHd5.js","/assets/ConfirmDialog-DzLa2HuW.js","/assets/CurrencyPicker-DtOwvyEj.js","/assets/DataTable-1m_Z938L.js","/assets/DayField-DpXGkJvl.js","/assets/DeveloperFooter-DYY1QIuc.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-BpS-XkVq.js","/assets/ManageTabs-CMHNrq5x.js","/assets/Modal-DSyecsNt.js","/assets/Notice-Z_GInbRE.js","/assets/PageHeader-DLELhKmK.js","/assets/PayrollPage-DipwRCt9.js","/assets/ProfileForm-C7pqd6zH.js","/assets/SearchBox-BD-mdv1d.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-yzHV7iGN.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-DYqdCJcX.js","/assets/SwitchField-BIFjZoL5.js","/assets/Tabs-FN6ezllY.js","/assets/TextField-DpaPi7qC.js","/assets/_app-DwsMDaRH.js","/assets/_app.account-Bm24iT9C.js","/assets/_app.books-swtp2UCB.js","/assets/_app.index-okzO4DGq.js","/assets/_app.manage-EyDUWXDT.js","/assets/_app.planning-DBaWfuRM.js","/assets/_app.portfolio-BN845LAY.js","/assets/_app.reports-BfJLaXAL.js","/assets/_app.team-C7LNwak-.js","/assets/_app.team.funds-Bo_Z73fk.js","/assets/_app.team.index-l_loR0P4.js","/assets/_app.team.periods._periodId-CEyaUr0z.js","/assets/_app.team.periods.index-BByx9gPC.js","/assets/_app.transactions-61fM2OFx.js","/assets/_app.wallet-CRlPuNPK.js","/assets/accent-CYCtGD_l.js","/assets/auth-BaWj1G5P.js","/assets/books-tqpvJnDQ.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-CFHkJqoM.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-BgTKI1Ze.js","/assets/index-DqQQLFie.css","/assets/index.esm-DKDaBIhT.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-DJ5ge2NZ.js","/assets/market-D85KPyNS.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-DUXlYeDV.js","/assets/payroll-TuJeBUzC.js","/assets/portfolio-CgRKzpNy.js","/assets/queryDefaults-S95AemW9.js","/assets/reports-D4CESvTR.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-xruU_hhj.js","/assets/schemas-BV6ipYgV.js","/assets/shared-B2y_-Hj_.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-Bcn5_AaD.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-J9qAXS65.js","/assets/ui-z-n5ml4n.js","/assets/useActiveBook-DIPeDajc.js","/assets/useCatalog-CAwPaRU9.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-k_X725SH.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-Cfq3hWy8.js","/assets/useTickerRows-jNrsmrQK.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
