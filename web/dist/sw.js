const CACHE = "kasbbook-86b82f6cf5";
const FILES = ["/assets/AttachmentsField-B1-FtPU-.js","/assets/BookRequired-uMJJM5_v.js","/assets/BottomSheet-C2M33tGh.js","/assets/Capital-DRb3DngO.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-DX0PkYBi.js","/assets/Collapsible-ClJnj9N8.js","/assets/ConfirmDialog-rI9crL22.js","/assets/CurrencyPicker-Cv6obNah.js","/assets/DataTable-BqF9Orac.js","/assets/DayField-DoUFchJy.js","/assets/DeveloperFooter-CgL4y4b4.js","/assets/ErrorState-CT6Si6pg.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-BZWf8ijC.js","/assets/ManageTabs-BOabtCQw.js","/assets/Modal-B9jjwNRa.js","/assets/Notice-CHU59pn8.js","/assets/PayrollPage-Cpq5QXMG.js","/assets/ProfileForm-bFDPHw83.js","/assets/SearchBox-D0VerB-x.js","/assets/SectionCard-CaRIsOrk.js","/assets/SelectField-B8XkRxm4.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-CaRGxAQ3.js","/assets/SwitchField-CKsWeBnH.js","/assets/Tabs-D04XRm7w.js","/assets/TextField-DYx-5XWa.js","/assets/_app-Tp9QRWL8.js","/assets/_app.account-ONd-_0o9.js","/assets/_app.books-B3MsiFnH.js","/assets/_app.index-iZ6qm_Bz.js","/assets/_app.manage-BlchgsL7.js","/assets/_app.planning-2x5dsynT.js","/assets/_app.portfolio-CBbHZIBU.js","/assets/_app.reports-W8kq2W39.js","/assets/_app.team-BRg49GxQ.js","/assets/_app.team.funds-BdrhqJK-.js","/assets/_app.team.index-CmddpaL4.js","/assets/_app.team.periods._periodId-BwOZN2jd.js","/assets/_app.team.periods.index-DjpxJF3n.js","/assets/_app.team.shares-B---6Jic.js","/assets/_app.transactions-Coh_1VBb.js","/assets/_app.wallet-C-Y16Lgs.js","/assets/accent-Bqt8fitj.js","/assets/auth-Ds8TkJ9K.js","/assets/books-CstPA5IF.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-B1Oi7ndN.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-B8gmWEB6.css","/assets/index-CDHxZvXT.js","/assets/index.esm-C3e0M3lo.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-jn9SzISa.js","/assets/market-DWrBXmFJ.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-28HqIL69.js","/assets/payroll-KWNERobz.js","/assets/portfolio-B32zDP0K.js","/assets/queryDefaults-B7ulhyYu.js","/assets/reports-BjZjn-Zs.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-CwUSepeb.js","/assets/schemas-5p1qjqFX.js","/assets/shared-BVJQqKog.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-vF30CbRU.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-CuoCVqbR.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-CgGWkWKl.js","/assets/useCatalog-B3InVvxU.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-mgeAVSt1.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-BCpw65LB.js","/assets/useTickerRows-Wvbj1Zs3.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
