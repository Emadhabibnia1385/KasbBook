const CACHE = "kasbbook-f6d74026fd";
const FILES = ["/assets/BookRequired-DLa1MfVC.js","/assets/BottomSheet-DPbV8o7E.js","/assets/Charts-D4zO68xW.js","/assets/ChoiceFields-DISeEAwj.js","/assets/ConfirmDialog-BafyC6Q3.js","/assets/CurrencyPicker-BIAPzUlr.js","/assets/DataTable-sfcK3oC9.js","/assets/DateTimeField-DXcpi3RW.js","/assets/DayField-BL63G4ED.js","/assets/DeveloperFooter-CDOFUTJq.js","/assets/ErrorState-CFoIzY8s.js","/assets/FilterChips-C26w1Sdq.js","/assets/GithubLink-B-re3F7q.js","/assets/InstallButton-UREuQgTM.js","/assets/KeyValueList-CS0VSITk.js","/assets/Link-BwrYPIid.js","/assets/Modal-DyoXyXps.js","/assets/Notice-BraNJBj9.js","/assets/PageHeader-UjMfznHe.js","/assets/PayrollPage-CNuW_nUt.js","/assets/ProfileForm-CnQ8lcB4.js","/assets/SearchBox-D5uPv2--.js","/assets/SectionCard-0Dx-imW-.js","/assets/SelectField-C4lOa6lb.js","/assets/SelectionIndicator-Dc0SBySl.js","/assets/StatusChip-DL_d14br.js","/assets/SwitchField-CCNboK0b.js","/assets/TextField-BqNCwX7C.js","/assets/_app-D9rEVO6D.js","/assets/_app.account-CicJ5w76.js","/assets/_app.books-BiK4iN2d.js","/assets/_app.index-CJn4Cycb.js","/assets/_app.more-Dp7mU_-n.js","/assets/_app.planning-DltazI3J.js","/assets/_app.recurring-TtkEozxK.js","/assets/_app.reports-B7B_fo9a.js","/assets/_app.team-YpJdeene.js","/assets/_app.team.funds-CvFrfJFA.js","/assets/_app.team.index-DFsIwEEv.js","/assets/_app.team.periods._periodId-odBZnWdS.js","/assets/_app.team.periods.index-BMXk8KW6.js","/assets/_app.team.shares-CEYY-k3q.js","/assets/_app.transactions-BAMWSFps.js","/assets/_app.wallet-C7UHekrI.js","/assets/accent-B6wiMkL9.js","/assets/books-C5JMsp3O.js","/assets/calendar-C35FAti_.js","/assets/clock-D8LlN1Fp.js","/assets/decimal-6YOdUFZ2.js","/assets/format-Dhm5SXq6.js","/assets/format-P-qd1Sc3.js","/assets/icons-CTIHdB1I.js","/assets/index-BciE0mTR.css","/assets/index-WBuh7upV.js","/assets/lazyRouteComponent-CjRywOmq.js","/assets/link-M86a8oEv.js","/assets/login-YHiTvSLW.js","/assets/market-BjPB4YBn.js","/assets/matchContext-DmX0tGDU.js","/assets/mutations-hc42WDxs.js","/assets/overlays-BthX4c8V.js","/assets/queryDefaults-Cr5VOZw-.js","/assets/rules-jGqoytSj.js","/assets/schemas-ic0qZ50z.js","/assets/shared-BdHLuOEQ.js","/assets/status-C7SjyUYO.js","/assets/strings-Ctuc9eFV.js","/assets/surface-itiypn0z.js","/assets/table.styles-DWhb3RN8.js","/assets/tables-CN-AOOjG.js","/assets/tickerPrefs-BLEkZLZo.js","/assets/transactions-ByYGoz5l.js","/assets/ui-Bdc6sSvG.js","/assets/useActiveBook-CMUNRE52.js","/assets/useCatalog-CdiS1Stt.js","/assets/useHasTabbableChild-BQ_FsyYZ.js","/assets/useHover-BFKuvMv4.js","/assets/useIsNarrow-DfZ3NEa3.js","/assets/useMatch-C3uy1ZdQ.js","/assets/useNavigate-BiRAT0gK.js","/assets/useQuotes-CbE6LJL-.js","/assets/useRouter-DDQhmSJN.js","/assets/useSelector-LA0H9FxF.js","/assets/useSlot-BDaqjXzG.js","/assets/useSpinButton-fqgHDf0P.js","/assets/useToggleState-DbtVrnZn.js","/assets/useUpdateEffect-CHWv7OKs.js","/assets/with-selector-CLcdDC5i.js"];
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
