const CACHE = "kasbbook-b82c860d3f";
const FILES = ["/assets/AttachmentsField-Cy1goHX4.js","/assets/BookRequired-BATcVqxK.js","/assets/BottomSheet-ht8MsUW5.js","/assets/Capital-BwPaBTIp.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-_Dhp4Khq.js","/assets/Collapsible-UPKBYak1.js","/assets/ConfirmDialog-FiU83pSx.js","/assets/CurrencyPicker-L0EfK3Gu.js","/assets/DataTable-DlLOfS54.js","/assets/DayField-CIMCqZFO.js","/assets/DayPair-Bn4ES6pf.js","/assets/DeveloperFooter-CTmIQUoX.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-D1rxVUzq.js","/assets/ManageTabs-erl1CL3n.js","/assets/Modal-zsXtGIz9.js","/assets/Notice-p5xKhdNg.js","/assets/PageHeader-BhwGP361.js","/assets/PayrollPage-CJmE-hNg.js","/assets/ProfileForm-BAFy2ZVm.js","/assets/SearchBox-B9db5L3W.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-4OBUiG1d.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-CCekjQIJ.js","/assets/SwitchField-CGXGY1_A.js","/assets/Tabs-DsvC9AGD.js","/assets/TextField-Dqk5hSX6.js","/assets/_app-DfU6spRB.js","/assets/_app.account-y0eRfLrs.js","/assets/_app.books-Dwzf2xkL.js","/assets/_app.index-DxW4FnHt.js","/assets/_app.manage-BCRkH88o.js","/assets/_app.planning-3f69CKe5.js","/assets/_app.portfolio-KZP0vKO7.js","/assets/_app.reports-CLtvHlJ6.js","/assets/_app.team-XUmyxIP7.js","/assets/_app.team.funds-nrRl7Yif.js","/assets/_app.team.index-BQ3bj-HG.js","/assets/_app.team.periods._periodId-T0txf1S-.js","/assets/_app.team.periods.index-BAohLumg.js","/assets/_app.transactions-Dbsbtm3P.js","/assets/_app.wallet-BlfEZe6u.js","/assets/accent-DObGSbTE.js","/assets/auth-C5q2ztTH.js","/assets/books-BkITzI3T.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-BPkUj5KX.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/icons-B7FYk1y3.js","/assets/index-DGG3ADv5.js","/assets/index-DqQQLFie.css","/assets/index.esm-D-RyJCh8.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-DS3PJmqo.js","/assets/market-CXIX_ewY.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CpUCEZxx.js","/assets/payroll-fRAcO2UV.js","/assets/portfolio-jFxxVl4C.js","/assets/queryDefaults-CVL64FSO.js","/assets/reports-Bc5BjYJL.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-CfinsGrV.js","/assets/schemas-CXMkuNVj.js","/assets/shared-Bo4mk7yl.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DZzUYwk6.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-Mw9zS6Ac.js","/assets/ui-CJ8RJe_G.js","/assets/useActiveBook-D1_UJvxp.js","/assets/useCatalog-COCEXp6g.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-4uQyWY_W.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-C3NxiCQy.js","/assets/useTickerRows-CgjsrRvJ.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
