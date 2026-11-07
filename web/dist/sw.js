const CACHE = "kasbbook-758e7aacf4";
const FILES = ["/assets/AttachmentsField-CCJmKBqs.js","/assets/BookRequired-pUrWAWvB.js","/assets/BottomSheet-Ctqrie57.js","/assets/Capital-BNohYLwB.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-DdhOjU0H.js","/assets/Collapsible-C0z_u9UZ.js","/assets/ConfirmDialog-DhXYyWqK.js","/assets/CurrencyPicker-CtDMN_d7.js","/assets/DataTable-CXEQBk3z.js","/assets/DayField-iOJ69K1O.js","/assets/DayPair-BIbCpdRs.js","/assets/DeveloperFooter-B4TTHf-g.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-qjY5Bh9R.js","/assets/ManageTabs-CzJS3b3g.js","/assets/Modal-CIOROrUn.js","/assets/Notice-CJKRLs_k.js","/assets/PageHeader-CI9r0OaG.js","/assets/PayrollPage-se0XgKnX.js","/assets/ProfileForm-B2smrQJG.js","/assets/SearchBox-D6-PBzdW.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-25yI3uSF.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-DHtRhKtq.js","/assets/SwitchField-Da-XRbZH.js","/assets/Tabs-DToMH09z.js","/assets/TextField-LXi0cjNP.js","/assets/_app-BB7mGaLf.js","/assets/_app.account-CWo6cBiR.js","/assets/_app.books-C09s-NAr.js","/assets/_app.index-DpWtwbuX.js","/assets/_app.manage-BIbEGCXt.js","/assets/_app.planning-Buh20Hxc.js","/assets/_app.portfolio-DmImulPA.js","/assets/_app.reports-CLXGIRaf.js","/assets/_app.team-DtH29XJo.js","/assets/_app.team.funds-DI1nL0HL.js","/assets/_app.team.index-BBBLvn_X.js","/assets/_app.team.periods._periodId-D4ouhedH.js","/assets/_app.team.periods.index-D1H5YTK0.js","/assets/_app.transactions-MrB9qU7W.js","/assets/_app.wallet-sIRjPY7o.js","/assets/accent-BUuMIY7P.js","/assets/auth-DKpZZy34.js","/assets/books-CmgGKj2v.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-BkAwirDC.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-DqQQLFie.css","/assets/index-s6F3mtr0.js","/assets/index.esm-vbtKvHSW.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-BmdeZU2_.js","/assets/market-BaccT-UN.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-B6Um5I5S.js","/assets/payroll-DQoMxleV.js","/assets/portfolio-BpdLs_U0.js","/assets/queryDefaults-DEiYDtP_.js","/assets/reports-D7aaRzR9.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-DLzctYOL.js","/assets/schemas-BiCBopMv.js","/assets/shared-CTG01i9q.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-Ci4cYXBx.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-Drl4jXET.js","/assets/ui-Cu_Vz8bQ.js","/assets/useActiveBook-DK0DmLh_.js","/assets/useCatalog-B232fTVf.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-GTmPgpsT.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-BHSnlf3o.js","/assets/useTickerRows-BjulTay0.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
