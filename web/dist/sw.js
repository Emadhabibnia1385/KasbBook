const CACHE = "kasbbook-1a852f6309";
const FILES = ["/assets/AttachmentsField-DW-m49je.js","/assets/BookRequired-lN3Cb1ZY.js","/assets/BottomSheet-CUehBzUL.js","/assets/Capital-Dm2Ovzzd.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-BjGzBdqn.js","/assets/Collapsible--gDXHiOj.js","/assets/ConfirmDialog-DreAd8hO.js","/assets/CurrencyPicker-BSVcu0gt.js","/assets/DataTable-OdHFwooL.js","/assets/DayField-AmexmGg4.js","/assets/DeveloperFooter-BZKrzXNP.js","/assets/FilterChips-B0PL3tGD.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-BoNlkidu.js","/assets/ManageTabs-DDPFHgHn.js","/assets/Modal-CReSxmML.js","/assets/Notice-B9QbdU6B.js","/assets/PageHeader-DbgmpoD1.js","/assets/PayrollPage-CpPmNHTf.js","/assets/ProfileForm-CWHqu0A6.js","/assets/SearchBox-B1Y3lBbF.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-C2LXqS-f.js","/assets/SelectionIndicator-Dx61TNxt.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-TPZcRSfm.js","/assets/SwitchField-CRQU81GL.js","/assets/Tabs-B7XUGIBv.js","/assets/TextField-hsXZib25.js","/assets/_app-78qHljfc.js","/assets/_app.account-BBufLoc_.js","/assets/_app.books-vaD6ePIr.js","/assets/_app.index-CVjZZaNl.js","/assets/_app.manage-Dqn6fNwV.js","/assets/_app.planning-C0nX9RKA.js","/assets/_app.portfolio-BuOhwTLM.js","/assets/_app.reports-B-44qRLv.js","/assets/_app.team-C7STJnWn.js","/assets/_app.team.funds-DHAufmo3.js","/assets/_app.team.index-J5S2EcCS.js","/assets/_app.team.periods._periodId-CwZfy6mM.js","/assets/_app.team.periods.index-DePB6UAH.js","/assets/_app.transactions-3zFROBOT.js","/assets/_app.wallet-Cq99F_t-.js","/assets/accent-CMifCV4k.js","/assets/auth-CIb1j1RD.js","/assets/books-K7zHMAFU.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-DpzW8-3b.js","/assets/clock-pHA8QHUR.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-CKE3KLmt.js","/assets/index-D5maQZZ7.css","/assets/index.esm-D75r1Ixm.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-D7D3918e.js","/assets/market-C-lKzAk7.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-wP9FJHwD.js","/assets/payroll-BQWZJ1Ux.js","/assets/portfolio-DJVfVOxd.js","/assets/queryDefaults-DqQnJfhz.js","/assets/reports-CHwt8UgD.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-CJRz4wVx.js","/assets/schemas-BrH5mIBG.js","/assets/shared-B59BypNE.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-B2PB4b9a.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-CzohgcOL.js","/assets/ui-XR8ZTqOF.js","/assets/useActiveBook-Ctsi1H-w.js","/assets/useCatalog-NIa1FIz8.js","/assets/useHasTabbableChild-DGeXMUPo.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BptYsEii.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-88YpJJ4n.js","/assets/useTickerRows-DVQkj-Ac.js","/assets/useToggleState-CCYXpKYk.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
