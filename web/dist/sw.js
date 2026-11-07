const CACHE = "kasbbook-2f972c6711";
const FILES = ["/assets/AttachmentsField-BXhtq6M7.js","/assets/BookRequired-XlRDZI7H.js","/assets/BottomSheet-B7gyeFD8.js","/assets/Capital-DuroaUWt.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-Cm1CI_CX.js","/assets/Collapsible-Cids-mLV.js","/assets/ConfirmDialog-RpuVZOVW.js","/assets/CurrencyPicker-DKi7ZxjO.js","/assets/DataTable-CFxT2_L6.js","/assets/DayField--0f7e1ss.js","/assets/DeveloperFooter-B-G6samO.js","/assets/ErrorState-DEjmHY7m.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-38Zo0gnU.js","/assets/ManageTabs-F5JI7bVm.js","/assets/Modal-LEdygzJx.js","/assets/Notice-Ci00bD-T.js","/assets/PayrollPage-D5O-2d8z.js","/assets/ProfileForm-Cx3uq4hS.js","/assets/SearchBox-BbOz_eoH.js","/assets/SectionCard-BinwXsmR.js","/assets/SelectField-CtIHm1Fs.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-DR2EOZk6.js","/assets/SwitchField-Bv9skDFC.js","/assets/Tabs-BTfGLUCz.js","/assets/TextField-BkBl459t.js","/assets/_app-NoEuGpd2.js","/assets/_app.account-Cgvv9lvt.js","/assets/_app.books-DMLrkJkG.js","/assets/_app.index-BFnqSB3F.js","/assets/_app.manage-DUuBAZDi.js","/assets/_app.planning-Br4uUOiE.js","/assets/_app.portfolio-BpgAfb8N.js","/assets/_app.reports-DuJAE2qq.js","/assets/_app.team-Djtey35p.js","/assets/_app.team.funds-CGopfzgP.js","/assets/_app.team.index-eNVmy1fT.js","/assets/_app.team.periods._periodId-B0hrs0eE.js","/assets/_app.team.periods.index-DPHzfFyF.js","/assets/_app.team.shares-DClQ6mdJ.js","/assets/_app.transactions-IXrQlt2N.js","/assets/_app.wallet-C8R-PLkW.js","/assets/accent-Bhe_EZCG.js","/assets/auth-BpCdDAcb.js","/assets/books-Bgfh_iQd.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-BRZZo6v_.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-BrecVvEy.css","/assets/index-Coz2KKYI.js","/assets/index.esm-QP5uyFR6.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-D7WUPHkd.js","/assets/market-sGq8wwB3.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-DpeA2Mm9.js","/assets/payroll-DuAsxWMk.js","/assets/portfolio-2Tl1nJ20.js","/assets/queryDefaults-DHP4Xi6Q.js","/assets/reports-DWdikhAr.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-CKaE_vJI.js","/assets/schemas-ZAP3KtES.js","/assets/shared-BfLtu8jW.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-B7YaUdO7.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-Dd93GOI_.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-B1bg5kEk.js","/assets/useCatalog-QWD2bHhT.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-D-QdoozC.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-z8EX5K1x.js","/assets/useTickerRows-TiQfNbzv.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
