const CACHE = "kasbbook-732526dd06";
const FILES = ["/assets/AttachmentsField-D8pckIeo.js","/assets/BookRequired-CZ7cEFr7.js","/assets/BottomSheet-m2cMzIO5.js","/assets/Capital-B7iI2NTX.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BqKKhVFg.js","/assets/Collapsible-CG0lSe9U.js","/assets/ConfirmDialog-Bhp8OMIa.js","/assets/CurrencyPicker-Ch1WhDPp.js","/assets/DataTable-_GTriBG0.js","/assets/DayField-BoHXN_Ra.js","/assets/DayPair-CTyWtPlp.js","/assets/DeveloperFooter-DEjW9x0f.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-Ba4mqzK_.js","/assets/ManageTabs-BHNWJ5K_.js","/assets/Modal-QwV_f-R3.js","/assets/Notice-DXNWziHM.js","/assets/PageHeader-CBEd8ccX.js","/assets/PayrollPage-t78caBMq.js","/assets/ProfileForm-Cwd4eTKN.js","/assets/SearchBox-CAlzoMEF.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-BgoAYIDL.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-6SMisz55.js","/assets/SwitchField-B9vo5wU5.js","/assets/Tabs-DdtY_a4J.js","/assets/TextField-DT6i_Hk8.js","/assets/_app-B5HaegHB.js","/assets/_app.account-DRmU-UZc.js","/assets/_app.books-CpYJlQw6.js","/assets/_app.index-7SoNEpRB.js","/assets/_app.manage-CQ6qgeAZ.js","/assets/_app.planning-Djci0g4s.js","/assets/_app.portfolio-Bur32Vod.js","/assets/_app.reports-S_F2vZcy.js","/assets/_app.team-Chq45R8s.js","/assets/_app.team.funds-CqdLOGyQ.js","/assets/_app.team.index-C3PwLHIH.js","/assets/_app.team.periods._periodId-CYTqk9rN.js","/assets/_app.team.periods.index-3ZSgltUs.js","/assets/_app.transactions-DSIYcVRK.js","/assets/_app.wallet-D0BhYiSr.js","/assets/accent-kmsabPxp.js","/assets/auth-DaQmKdzc.js","/assets/books-DJLo4id4.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-CUygsJbb.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/icons-B7FYk1y3.js","/assets/index-32C5RapG.js","/assets/index-DqQQLFie.css","/assets/index.esm-BlKXenyN.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-BDkCk2eu.js","/assets/market-DN0JyRwH.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-VmO_1a4B.js","/assets/payroll-CGQpW8y3.js","/assets/portfolio-DA4ShHUL.js","/assets/queryDefaults-C5WQCh9U.js","/assets/reports-CAh_YbQK.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-D95cRmvb.js","/assets/schemas-Bw6ULtpF.js","/assets/shared-BfnPW14U.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DbPq0_u-.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-MwsOxdVN.js","/assets/ui-B8PowqMm.js","/assets/useActiveBook-jJ-xzFBJ.js","/assets/useCatalog-BBwwQ7kM.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-DJmldE-n.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-0mnWxbzw.js","/assets/useTickerRows-pEU61Z40.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
