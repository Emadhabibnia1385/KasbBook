const CACHE = "kasbbook-215fda94f5";
const FILES = ["/assets/BookRequired-D5ehYQOj.js","/assets/BottomSheet-O8srezNS.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-CYaLkuol.js","/assets/Collapsible-Vc_uC5By.js","/assets/ConfirmDialog-tPMPvR6E.js","/assets/CurrencyPicker-DzBbcfVY.js","/assets/DataTable-Dnk7_K3W.js","/assets/DayField-DocRMSXQ.js","/assets/DeveloperFooter-CrbGNnHW.js","/assets/ErrorState-42G_B6yv.js","/assets/FilterChips-CLk90K_b.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-B-eAhxfe.js","/assets/InstallButton-BrZUb2Yt.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-C6Erl3SG.js","/assets/ManageTabs-Dp3CNd1e.js","/assets/Modal-C97swXV5.js","/assets/Notice-CT-avGB-.js","/assets/PageHeader-C8b5B_-t.js","/assets/PayrollPage-CMDhjhjY.js","/assets/ProfileForm-YEBcyuVh.js","/assets/SearchBox-BPl7_8IO.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-BgzJGRxH.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-Dp_Y_WWG.js","/assets/SwitchField-RyxPFvst.js","/assets/Tabs-DJchWD9d.js","/assets/TextField-BdKkh-Y2.js","/assets/_app-Chu__aqM.js","/assets/_app.account-CXVndLgY.js","/assets/_app.books-CMe5ocJ6.js","/assets/_app.index-CS84tTO3.js","/assets/_app.manage-KQxsT1Df.js","/assets/_app.more-CvPMBf2n.js","/assets/_app.planning-Cq36EiOX.js","/assets/_app.reports-D9GYnetY.js","/assets/_app.team-Bp00s7rU.js","/assets/_app.team.funds-CJ26BKJR.js","/assets/_app.team.index-B_XEJcKD.js","/assets/_app.team.periods._periodId-BElpkNWj.js","/assets/_app.team.periods.index-CJ-kr2G8.js","/assets/_app.team.shares-aadObUB5.js","/assets/_app.transactions-v8KNt-Zi.js","/assets/_app.wallet-DqoC61ax.js","/assets/accent-6lpC2GZs.js","/assets/auth-D_cRac2o.js","/assets/books-CuOGfHGk.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-CIobEXnK.js","/assets/format-yhtkESqM.js","/assets/icons-DXTTqhFB.js","/assets/index-BUzszqrr.css","/assets/index-D82WaTVz.js","/assets/index.esm-DDX9IAbC.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-D8gXb6rS.js","/assets/market-DRi_S_Xd.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CCqzLNya.js","/assets/overlays-Zoz6QNKF.js","/assets/payroll-BaWhbZF1.js","/assets/queryDefaults-B6ZEI1TK.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-DyEYw7Zl.js","/assets/schemas-OHH1AKP9.js","/assets/shared-B2ncf5sN.js","/assets/status-C7SjyUYO.js","/assets/strings-CdubY5B9.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-Ds8M_HcO.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-BtqOI6wR.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-CL59Ihud.js","/assets/useCatalog--I2IEP0L.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-C20hIClL.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-BDtGnkZ_.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
