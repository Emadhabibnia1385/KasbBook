const CACHE = "kasbbook-a3183a7e00";
const FILES = ["/assets/AttachmentsField-8nFw8cKQ.js","/assets/BookRequired-BpdrPOZY.js","/assets/BottomSheet-C2w6qjEa.js","/assets/Capital-DLaPY6ws.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-B9kuwxpo.js","/assets/Collapsible-BP-7ufp8.js","/assets/ConfirmDialog-Zvjfx1Fu.js","/assets/CurrencyPicker-B5vmnfX1.js","/assets/DataTable-DupRpYhq.js","/assets/DayField-DNLwztAL.js","/assets/DeveloperFooter-CuwcT23D.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-Cj95vzuY.js","/assets/ManageTabs-BOFA8Mus.js","/assets/Modal-RqGQfkVx.js","/assets/Notice-LFLpPoUB.js","/assets/PageHeader-Cd6jZh-t.js","/assets/PayrollPage-6pWEPA9a.js","/assets/ProfileForm-CDCm4if_.js","/assets/SearchBox-BRywCtDO.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-CMag9v4Y.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-BRyni4ac.js","/assets/SwitchField-gAr-j0-I.js","/assets/Tabs-KRdLy9S_.js","/assets/TextField-Wwde1itY.js","/assets/_app-CpwShIUs.js","/assets/_app.account-C18KTWcO.js","/assets/_app.books-Z1w0M_VW.js","/assets/_app.index-C0s3CL_U.js","/assets/_app.manage-rS3LkASr.js","/assets/_app.planning-D4H3fnS0.js","/assets/_app.portfolio-DpF2ZfGd.js","/assets/_app.reports-C3OR8xPI.js","/assets/_app.team-ZZnDxaL3.js","/assets/_app.team.funds-CpaNe_LW.js","/assets/_app.team.index-CohssBOT.js","/assets/_app.team.periods._periodId-B-i-YmVW.js","/assets/_app.team.periods.index-teMxRhfo.js","/assets/_app.transactions-ZoDiU_kU.js","/assets/_app.wallet-Bm1VvvD1.js","/assets/accent-BvMUmbLp.js","/assets/auth-CirZnsZK.js","/assets/books-CI8-8EGg.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-h4FEFaHj.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-BdC9m-Ph.js","/assets/index-DqQQLFie.css","/assets/index.esm-Dor9LrgA.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-DM-7-fh6.js","/assets/market-VmQDgzEC.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-BWFlWs9a.js","/assets/payroll-DZqIkUx1.js","/assets/portfolio-DyTZSmkR.js","/assets/queryDefaults-Brqf_9cA.js","/assets/reports-BKmM2t--.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-DGQyYVm1.js","/assets/schemas-CdFkyV6q.js","/assets/shared-DfPfavQl.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-BMg822Kv.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-lfa7XC1j.js","/assets/ui-CP9C01hx.js","/assets/useActiveBook-B7WWVcIA.js","/assets/useCatalog-9E_hreQX.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-ByieUwqA.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-BzdG_TG9.js","/assets/useTickerRows-DcbnTQwD.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
