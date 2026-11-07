const CACHE = "kasbbook-89f9720838";
const FILES = ["/assets/AttachmentsField-LfrWAVFC.js","/assets/BookRequired-C7JIMCUU.js","/assets/BottomSheet-CXMg6JWC.js","/assets/Capital-BdFXHs2s.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BQ0Hmffr.js","/assets/Collapsible-GAPL0PaF.js","/assets/ConfirmDialog-CWUkDEMq.js","/assets/CurrencyPicker-CS888EDj.js","/assets/DataTable-Chh1NFvw.js","/assets/DayField-Sjk4kmo-.js","/assets/DayPair-D9r692ux.js","/assets/DeveloperFooter-t3S9kgmn.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-DW-lcWvf.js","/assets/ManageTabs-D_26J-ct.js","/assets/Modal-Bt9OQ9cG.js","/assets/Notice-CYEY7lKX.js","/assets/PageHeader-CILP8jRG.js","/assets/PayrollPage-IR_vepJS.js","/assets/ProfileForm-DxpKJ1UM.js","/assets/SearchBox-l8yBbIgQ.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-ClHikNxz.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-H1IG8VQE.js","/assets/SwitchField-DK3oT2wT.js","/assets/Tabs-BsalOWl9.js","/assets/TextField-By19SZMi.js","/assets/_app-CBJQFeYP.js","/assets/_app.account-DhqyKHao.js","/assets/_app.books-CrBh8qhe.js","/assets/_app.index-CmO3Qvp1.js","/assets/_app.manage-DjFZjrYR.js","/assets/_app.planning-BC4tdd0a.js","/assets/_app.portfolio-fXTK1JYb.js","/assets/_app.reports-CDq6MK7Q.js","/assets/_app.team-BHqf9H0m.js","/assets/_app.team.funds-DVO6d7M-.js","/assets/_app.team.index-CQeCBoAG.js","/assets/_app.team.periods._periodId-OVJJqwgd.js","/assets/_app.team.periods.index-B9zl6fuA.js","/assets/_app.transactions-11gu4MMo.js","/assets/_app.wallet-C29WGRhG.js","/assets/accent-BxsL5iJU.js","/assets/auth-ndc2xAu9.js","/assets/books-DSHX-hmp.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-Z-BDgjQP.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/icons-B7FYk1y3.js","/assets/index-DND7bB_X.js","/assets/index-DqQQLFie.css","/assets/index.esm-DAasmC7_.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-CvMrvwA-.js","/assets/market-DfHjrVWt.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-BIN9O2D2.js","/assets/payroll-DljxTH6y.js","/assets/portfolio-DnHictqy.js","/assets/queryDefaults-DvkPtdbw.js","/assets/reports-BPxNJjeh.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-C8juMs3a.js","/assets/schemas-CHPblOk4.js","/assets/shared-CQiw3GS8.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-B7kRNQs1.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-BsdldWdM.js","/assets/ui-B6SrFJ9D.js","/assets/useActiveBook-BupMyQ6H.js","/assets/useCatalog-0DYVF-eK.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-MCTaTy-3.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-D_TnKwOV.js","/assets/useTickerRows-DfVjr0me.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
