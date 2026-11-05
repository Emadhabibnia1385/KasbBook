const CACHE = "kasbbook-c7a943d116";
const FILES = ["/assets/BottomSheet-CYRZHus_.js","/assets/Charts-B1Wd5oNd.js","/assets/ChoiceFields-pRP1i6LU.js","/assets/Collapsible-DBBQaw1C.js","/assets/CollectionBuilder-DiHkzLeu.js","/assets/ConfirmDialog-B0b-rGI_.js","/assets/CurrencyPicker-wr3ZFdd-.js","/assets/DataTable-uTfTkb7g.js","/assets/DateTimeField-CqlIVitT.js","/assets/DayField-DpJiNJCJ.js","/assets/DragAndDrop-UaQ9w_sY.js","/assets/ErrorState-gAMoXb5p.js","/assets/FilterChips-C7nSQ39g.js","/assets/FocusScope-DfcBPs56.js","/assets/InstallButton-qI_Eukyu.js","/assets/KeyValueList-DArXbXR0.js","/assets/Link-CCLTYU7x.js","/assets/Modal-C9Yu53LT.js","/assets/Notice-gEvG8A8N.js","/assets/PageHeader-Dw10pTNF.js","/assets/PayrollPage-cV6btHE4.js","/assets/SearchBox-D9jix2eJ.js","/assets/SectionCard-DkQeyoO7.js","/assets/SelectField-vIqU1K7e.js","/assets/SelectionIndicator-YDeT_HpY.js","/assets/StatusChip-N_v6KAym.js","/assets/SwitchField-B2zlnGMj.js","/assets/TextField-CX4VSMfO.js","/assets/ThemeToggle-CUE0lt8a.js","/assets/_app-CL0rD84y.js","/assets/_app.account-Cl-RNgDB.js","/assets/_app.books-DDyfKbL0.js","/assets/_app.index-DfctGY0x.js","/assets/_app.more-X-Pcj_Cq.js","/assets/_app.planning-D7GjzUO9.js","/assets/_app.recurring-BZk71xxX.js","/assets/_app.reports-Du-UiVkA.js","/assets/_app.search-B1ehTPrj.js","/assets/_app.team-BgdbPN-n.js","/assets/_app.team.funds-C2Wqs-8a.js","/assets/_app.team.index-BwS8aDPW.js","/assets/_app.team.periods._periodId-Ci7IoDNm.js","/assets/_app.team.periods.index-8-Tqg8j2.js","/assets/_app.team.shares-C3Gf1TNb.js","/assets/_app.transactions-CRWyYi_E.js","/assets/_app.wallet-bLRo6pCo.js","/assets/accent-D0kl_jlD.js","/assets/calendar-C35FAti_.js","/assets/format-P-qd1Sc3.js","/assets/icons-BGJjd1ks.js","/assets/index-DBmYXQPX.css","/assets/index-Di6OO_f8.js","/assets/lazyRouteComponent-CI-vu4CX.js","/assets/link-BFGZRn8Z.js","/assets/login-B2QPYuR5.js","/assets/matchContext-DW9e84vl.js","/assets/mutations-PtyG-AF8.js","/assets/queryDefaults-CbvFymTR.js","/assets/reports-rR1XlUoj.js","/assets/schemas-DrEwOcOw.js","/assets/shared-XrafUkz7.js","/assets/signOut-DjF_T9kn.js","/assets/status-C7SjyUYO.js","/assets/strings-BOv8K8s8.js","/assets/strings-Dxs1naMP.js","/assets/surface-CdCPeQN_.js","/assets/table.styles-DDpSUahh.js","/assets/tables-ByxTyd2b.js","/assets/transport-CisXY9XY.js","/assets/ui-DYd9Aawj.js","/assets/useActiveBook-OPVHQ4o6.js","/assets/useCatalog-D2sdDrjn.js","/assets/useFormValidation-x4BTWSD0.js","/assets/useHasTabbableChild-D9jZPju5.js","/assets/useIsNarrow-DyDcQwjR.js","/assets/useMatch-DSctLmL3.js","/assets/useNavigate-CzrAyNJU.js","/assets/useRouter-dy8zwnYC.js","/assets/useSelector-BYIvAqPs.js","/assets/useSlot-CScC864N.js","/assets/useSpinButton-BmcEAA_l.js","/assets/useTextField-DA06Qg5O.js","/assets/useToggleState-Cb4WgV-A.js","/assets/useUpdateEffect-C1Bk42wk.js","/assets/with-selector-CvHmMPql.js"];
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
