const CACHE = "kasbbook-13e13ba593";
const FILES = ["/assets/AttachmentsField-zUws9Yk2.js","/assets/BookRequired-DKXvGr5N.js","/assets/BottomSheet-DUwkKmlh.js","/assets/Capital-BokyNu-Z.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-KbmoKDLi.js","/assets/Collapsible-BY3uQqns.js","/assets/ConfirmDialog-BHZCQ1c9.js","/assets/CurrencyPicker-BgT76ZPC.js","/assets/DataTable-Dj7ODSVM.js","/assets/DayField-BLRZ-hy2.js","/assets/DeveloperFooter-Nuwixjuk.js","/assets/ErrorState-Cd3jOFwH.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-BS12uLGq.js","/assets/ManageTabs-CC5jDx7_.js","/assets/Modal-CnAeeXII.js","/assets/Notice-DtsFRH4l.js","/assets/PayrollPage-CATQEile.js","/assets/ProfileForm-Blk39mwU.js","/assets/SearchBox-PViAl1AB.js","/assets/SectionCard-DW_Jv0xn.js","/assets/SelectField-Dwo_lg_e.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-qoXzPRB6.js","/assets/SwitchField-CqPwyNii.js","/assets/Tabs-DOSNbMX9.js","/assets/TextField-CYHJqPTu.js","/assets/_app-CUo877t9.js","/assets/_app.account-DN-vBs-p.js","/assets/_app.books-C4Za_vMd.js","/assets/_app.index-y4QLfNb2.js","/assets/_app.manage-Dr899fWq.js","/assets/_app.planning-DJ1RmbW8.js","/assets/_app.portfolio-DObNN-XH.js","/assets/_app.reports-CB1JOVY3.js","/assets/_app.team-BQsnyyiW.js","/assets/_app.team.funds-Bc0lNzfd.js","/assets/_app.team.index-BLN6AWsA.js","/assets/_app.team.periods._periodId-b2-s6QJ3.js","/assets/_app.team.periods.index-Bg4OaZar.js","/assets/_app.team.shares-w44ZdOg6.js","/assets/_app.transactions-BGJYAaFM.js","/assets/_app.wallet-riFpV9fe.js","/assets/accent-CnyPpYku.js","/assets/auth-Bj8knKth.js","/assets/books-CSmbpu-D.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-DFGbVKBz.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-BrecVvEy.css","/assets/index-LaHEr8Eg.js","/assets/index.esm-Dk_V84AG.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-9b2jBZv9.js","/assets/market-D1jG35AG.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-_LzCiVQF.js","/assets/payroll-Dnz_jyyx.js","/assets/portfolio-2cbGGiot.js","/assets/queryDefaults-BuRPAtHe.js","/assets/reports-CD5GSAtJ.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-v0R_agUF.js","/assets/schemas-CfC6ipON.js","/assets/shared-1UzO903w.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-CE36MeAM.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-Oxdc0sFX.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-C1-M6xyc.js","/assets/useCatalog-BtSm5StT.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-DNqr3TTK.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-Df2iOW-z.js","/assets/useTickerRows-DE6uPIUq.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
