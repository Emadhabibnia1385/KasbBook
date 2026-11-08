const CACHE = "kasbbook-acc4c99c8e";
const FILES = ["/assets/AttachmentsField-rETYs_-T.js","/assets/BookRequired-BdGIP7PL.js","/assets/BottomSheet-CDJ3ucre.js","/assets/BrandMark-12jE58bh.js","/assets/Capital-BhA_6zN_.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-CXbTClK5.js","/assets/Collapsible--84S-4NJ.js","/assets/ConfirmDialog-BUjUboky.js","/assets/CurrencyPicker-Bc9dwx4O.js","/assets/DataTable-BnKc4UJ5.js","/assets/DayField-DBWaaWIs.js","/assets/DayPair-Dza0gmu1.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-DI0OHks_.js","/assets/ManageTabs-3mLYAMjp.js","/assets/Modal-BTX82zjM.js","/assets/Notice-57GwDqXc.js","/assets/PageHeader-DbxXdsrk.js","/assets/PayrollPage-Cc0CIHyb.js","/assets/ProfileForm-BPvNMFRA.js","/assets/SearchBox-DDHLFKRs.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-Cj2UnctR.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-BCWgFCW9.js","/assets/SwitchField-vmH1kysA.js","/assets/Tabs-By_nnjjx.js","/assets/TextField-Du1riz4J.js","/assets/_app-mskIw0eo.js","/assets/_app.account-BL2TeLzi.js","/assets/_app.books-DfxIGDJb.js","/assets/_app.index-CrHcfJyr.js","/assets/_app.manage-DALSOcr_.js","/assets/_app.planning-BWMtOi6n.js","/assets/_app.portfolio-u4M8GZgw.js","/assets/_app.reports-CkTleeaZ.js","/assets/_app.team-BUfB6emW.js","/assets/_app.team.funds-DLOD5gq2.js","/assets/_app.team.index-D19rp2Ip.js","/assets/_app.team.periods._periodId-DSRwfEM3.js","/assets/_app.team.periods.index-CpApcUiC.js","/assets/_app.transactions-C-bNv4cq.js","/assets/_app.wallet-3IF6Ynyc.js","/assets/accent-g1AZ5F8d.js","/assets/auth-BTfiNOrT.js","/assets/books-CRTCjDqr.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-pUmUbcIF.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/icons-B7FYk1y3.js","/assets/index-BY4pb1Op.css","/assets/index-Dcx7wM3x.js","/assets/index.esm-CidGRMcF.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-DVTqjjMZ.js","/assets/market-N6oq16tZ.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-B5i8_Gxa.js","/assets/payroll-2kiF77Mn.js","/assets/portfolio-BrFU77IB.js","/assets/queryDefaults-DHzJrR0X.js","/assets/reports-CwM9aMHb.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-DiuSVPcV.js","/assets/schemas-D1MI68_F.js","/assets/shared-DwIOykF-.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DIxjDGI7.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-BtvTvM8w.js","/assets/ui-Cxujf106.js","/assets/useActiveBook-DYgcmGd5.js","/assets/useCatalog-CNP6i0bU.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BeZwkn1i.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-DbnerTtc.js","/assets/useTickerRows-CVCO-T5Z.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
