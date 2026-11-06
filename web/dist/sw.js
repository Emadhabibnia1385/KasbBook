const CACHE = "kasbbook-719dd07152";
const FILES = ["/assets/BookRequired-D4ZCG2dG.js","/assets/BottomSheet-BW7hnEm0.js","/assets/Charts-D4zO68xW.js","/assets/ChoiceFields-BazPHcj3.js","/assets/ConfirmDialog-DTqdVb3p.js","/assets/CurrencyPicker-Def3_Rhf.js","/assets/DataTable-CQhx-shC.js","/assets/DateTimeField-X6CkEyYH.js","/assets/DayField-BTCXQB8i.js","/assets/DeveloperFooter-CIjLcAbp.js","/assets/ErrorState-ohKeFhCg.js","/assets/FilterChips-C26w1Sdq.js","/assets/GithubLink-DSK94x2h.js","/assets/InstallButton-C-_6ghQA.js","/assets/KeyValueList-CS0VSITk.js","/assets/Link-BwrYPIid.js","/assets/Modal-qmJ3GQ1A.js","/assets/Notice-BkPeROU1.js","/assets/PageHeader-QW-3gCAA.js","/assets/PayrollPage-BYv633ns.js","/assets/ProfileForm-DUh5Yn8A.js","/assets/SearchBox-DnSlEUog.js","/assets/SectionCard-0Dx-imW-.js","/assets/SelectField-D1Wln0yP.js","/assets/SelectionIndicator-Dc0SBySl.js","/assets/StatusChip-DsB3ukhp.js","/assets/SwitchField-BJIRxrLk.js","/assets/TextField-BwF1guZd.js","/assets/_app-CNNFhTYF.js","/assets/_app.account-D2lNZfVw.js","/assets/_app.books-CKokFxoE.js","/assets/_app.index-qxO5PBCY.js","/assets/_app.more-B8JxJ1hq.js","/assets/_app.planning-D4j3eF6V.js","/assets/_app.recurring-fM_geP4C.js","/assets/_app.reports-B49ljo9M.js","/assets/_app.team-BN8eelc2.js","/assets/_app.team.funds-C_jht4_n.js","/assets/_app.team.index-TG9FXUCB.js","/assets/_app.team.periods._periodId-CM5Vvha_.js","/assets/_app.team.periods.index-BZ-FBBHq.js","/assets/_app.team.shares-RUI7E3jY.js","/assets/_app.transactions-DuyxHuGI.js","/assets/_app.wallet-DjVIydVI.js","/assets/accent-QOigLOLY.js","/assets/books-BTodQZwb.js","/assets/calendar-C35FAti_.js","/assets/clock-D8LlN1Fp.js","/assets/decimal-6YOdUFZ2.js","/assets/format-DX2Dd9qy.js","/assets/format-P-qd1Sc3.js","/assets/icons-CTIHdB1I.js","/assets/index-BciE0mTR.css","/assets/index-CxRHLe9L.js","/assets/lazyRouteComponent-CjRywOmq.js","/assets/link-M86a8oEv.js","/assets/login-DqNpagkf.js","/assets/market-BoTkGwXw.js","/assets/matchContext-DmX0tGDU.js","/assets/mutations-BfEd5Zs7.js","/assets/overlays-DkLtyLI-.js","/assets/queryDefaults-vYJ40mXP.js","/assets/rules-B_RPAEa7.js","/assets/schemas-Bh36dB4N.js","/assets/shared-DA0y8pED.js","/assets/status-C7SjyUYO.js","/assets/strings-Ctuc9eFV.js","/assets/surface-itiypn0z.js","/assets/table.styles-DWhb3RN8.js","/assets/tables-Bn40t4pH.js","/assets/tickerPrefs-BLEkZLZo.js","/assets/transactions-C3MeG_7y.js","/assets/ui-Bdc6sSvG.js","/assets/useActiveBook-BZ9vY_Xr.js","/assets/useCatalog-C2JjlQlm.js","/assets/useHasTabbableChild-BQ_FsyYZ.js","/assets/useHover-BFKuvMv4.js","/assets/useIsNarrow-DfZ3NEa3.js","/assets/useMatch-C3uy1ZdQ.js","/assets/useNavigate-BiRAT0gK.js","/assets/useQuotes-NAIDybb1.js","/assets/useRouter-DDQhmSJN.js","/assets/useSelector-LA0H9FxF.js","/assets/useSlot-BDaqjXzG.js","/assets/useSpinButton-DvXMJKDb.js","/assets/useToggleState-DbtVrnZn.js","/assets/useUpdateEffect-CHWv7OKs.js","/assets/with-selector-CLcdDC5i.js"];
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
