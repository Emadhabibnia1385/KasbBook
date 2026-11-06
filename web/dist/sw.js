const CACHE = "kasbbook-94830b55ac";
const FILES = ["/assets/BookRequired-6KCfofXW.js","/assets/BottomSheet-CHoXia9q.js","/assets/Charts-D4zO68xW.js","/assets/ChoiceFields-Czs3r1KC.js","/assets/ConfirmDialog-DXoWuw8v.js","/assets/CurrencyPicker-4fPwUlzo.js","/assets/DataTable-CySxhmua.js","/assets/DateTimeField-qJ1WpxaX.js","/assets/DayField-CEMwyTN8.js","/assets/DeveloperFooter-BKhi1Fxe.js","/assets/ErrorState-CP4svIGI.js","/assets/FilterChips-C26w1Sdq.js","/assets/GithubLink-Cjd4C67k.js","/assets/InstallButton-5U0tdyZl.js","/assets/KeyValueList-CS0VSITk.js","/assets/Link-BwrYPIid.js","/assets/Modal-CK5ewk4Q.js","/assets/Notice-5OC_JxpY.js","/assets/PageHeader-OP2EfbRQ.js","/assets/PayrollPage-BqFN5eVj.js","/assets/ProfileForm-XngE09fp.js","/assets/SearchBox-DI3T6a6F.js","/assets/SectionCard-0Dx-imW-.js","/assets/SelectField-X5HjGJ1l.js","/assets/SelectionIndicator-Dc0SBySl.js","/assets/StatusChip-D30VEnIg.js","/assets/SwitchField-B0NxXO8w.js","/assets/TextField-LVcAJTLf.js","/assets/_app-DlQSMD74.js","/assets/_app.account-COrHf0G-.js","/assets/_app.books-BbLsS3AK.js","/assets/_app.index-zuYr5O8X.js","/assets/_app.more-CBWS6s7y.js","/assets/_app.planning-CTKAibUC.js","/assets/_app.recurring-HZoAuQaQ.js","/assets/_app.reports-DXMpfAlX.js","/assets/_app.team-D_uV-i-n.js","/assets/_app.team.funds-BLkLotRP.js","/assets/_app.team.index-CiRMgNB6.js","/assets/_app.team.periods._periodId-D8Hjzacr.js","/assets/_app.team.periods.index-BJt7IEmc.js","/assets/_app.team.shares-Becvd8yv.js","/assets/_app.transactions-D9vBlqD9.js","/assets/_app.wallet-CLiHFXmT.js","/assets/accent-B6lYeIqg.js","/assets/books-dUazVSxy.js","/assets/calendar-C35FAti_.js","/assets/clock-D8LlN1Fp.js","/assets/decimal-6YOdUFZ2.js","/assets/format-BIBWud-I.js","/assets/format-bak8e2q-.js","/assets/icons-CTIHdB1I.js","/assets/index-BciE0mTR.css","/assets/index-CwQJld64.js","/assets/lazyRouteComponent-CjRywOmq.js","/assets/link-M86a8oEv.js","/assets/login-C76gYtRI.js","/assets/market-Bd0E2INI.js","/assets/matchContext-DmX0tGDU.js","/assets/mutations-CK6ko3Iw.js","/assets/overlays-DRZAH4V5.js","/assets/queryDefaults-CkjtlKVx.js","/assets/rules-B09jiYya.js","/assets/schemas-CzgRzgdg.js","/assets/shared-dCUQ6uEX.js","/assets/status-C7SjyUYO.js","/assets/strings-Ctuc9eFV.js","/assets/surface-itiypn0z.js","/assets/table.styles-DWhb3RN8.js","/assets/tables-DHJMUTEd.js","/assets/tickerPrefs-BLEkZLZo.js","/assets/transactions-CZoZwN46.js","/assets/ui-Bdc6sSvG.js","/assets/useActiveBook-8RXoz3uZ.js","/assets/useCatalog-N_78XKv9.js","/assets/useHasTabbableChild-BQ_FsyYZ.js","/assets/useHover-BFKuvMv4.js","/assets/useIsNarrow-DfZ3NEa3.js","/assets/useMatch-C3uy1ZdQ.js","/assets/useNavigate-BiRAT0gK.js","/assets/useQuotes-M57mVXVz.js","/assets/useRouter-DDQhmSJN.js","/assets/useSelector-LA0H9FxF.js","/assets/useSlot-BDaqjXzG.js","/assets/useSpinButton-BLv8sqo4.js","/assets/useToggleState-DbtVrnZn.js","/assets/useUpdateEffect-CHWv7OKs.js","/assets/with-selector-CLcdDC5i.js"];
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
