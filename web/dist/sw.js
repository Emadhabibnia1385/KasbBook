const CACHE = "kasbbook-591d7c35c9";
const FILES = ["/assets/BookRequired-Dt733zVd.js","/assets/BottomSheet-BZhaZxnd.js","/assets/Charts-D4zO68xW.js","/assets/ChoiceFields-CflaXPri.js","/assets/ConfirmDialog-DtRUP4IN.js","/assets/CurrencyPicker-D6A0VgJ5.js","/assets/DataTable-Rzx-BDtB.js","/assets/DateTimeField-Dhgeyls4.js","/assets/DayField-C7I7QtLU.js","/assets/DeveloperFooter-CnbaBlig.js","/assets/ErrorState-AQQuSaRX.js","/assets/FilterChips-C26w1Sdq.js","/assets/GithubLink-CtqXDTaX.js","/assets/InstallButton-CRQ6jbFh.js","/assets/KeyValueList-CS0VSITk.js","/assets/Link-BwrYPIid.js","/assets/Modal-BZuXemke.js","/assets/Notice-CPyC0xT0.js","/assets/PageHeader-B-5GIaJ9.js","/assets/PayrollPage-0982Z5kE.js","/assets/ProfileForm-NO4NykRz.js","/assets/SearchBox-CX7Xnkr2.js","/assets/SectionCard-0Dx-imW-.js","/assets/SelectField-CpciufsW.js","/assets/SelectionIndicator-Dc0SBySl.js","/assets/StatusChip-BZjzNqx0.js","/assets/SwitchField-DjVXXwgU.js","/assets/TextField-CqScn_B8.js","/assets/_app-B_wqf-ix.js","/assets/_app.account-ivK8f_5Q.js","/assets/_app.books-CL7T6X_m.js","/assets/_app.index-BD3-MXGB.js","/assets/_app.more-CuLtAkIs.js","/assets/_app.planning-B_4NQekt.js","/assets/_app.recurring-Bn2f3bK2.js","/assets/_app.reports-CKjDIKuA.js","/assets/_app.team-Cg1FO0qa.js","/assets/_app.team.funds-svGwqZzv.js","/assets/_app.team.index-ChVwIeLa.js","/assets/_app.team.periods._periodId-6Sas7Sn_.js","/assets/_app.team.periods.index-TwoZWsTA.js","/assets/_app.team.shares-CXd38Myx.js","/assets/_app.transactions-CWIkuGkx.js","/assets/_app.wallet-CCtyzdRG.js","/assets/accent-BzxyrBkf.js","/assets/books-8s8NqhnY.js","/assets/calendar-C35FAti_.js","/assets/clock-D8LlN1Fp.js","/assets/decimal-6YOdUFZ2.js","/assets/format-CHRB-Lwo.js","/assets/format-bak8e2q-.js","/assets/icons-CTIHdB1I.js","/assets/index-Dgh1njiH.css","/assets/index-DrCVS92W.js","/assets/lazyRouteComponent-CjRywOmq.js","/assets/link-M86a8oEv.js","/assets/login-Bz5i70Pa.js","/assets/market-p2P71p_Z.js","/assets/matchContext-DmX0tGDU.js","/assets/mutations-DsFhadf1.js","/assets/overlays-B5NfTnxa.js","/assets/queryDefaults-ofsRnffl.js","/assets/rules-bewKpR-i.js","/assets/schemas-Db62LIeo.js","/assets/shared-DL4q_uRO.js","/assets/status-C7SjyUYO.js","/assets/strings-Ctuc9eFV.js","/assets/surface-itiypn0z.js","/assets/table.styles-DWhb3RN8.js","/assets/tables-mvo2AVrq.js","/assets/tickerPrefs-BLEkZLZo.js","/assets/transactions-DnziWmiC.js","/assets/ui-Bdc6sSvG.js","/assets/useActiveBook-DhtnbtqM.js","/assets/useCatalog-BpvBeJYN.js","/assets/useHasTabbableChild-BQ_FsyYZ.js","/assets/useHover-BFKuvMv4.js","/assets/useIsNarrow-DfZ3NEa3.js","/assets/useMatch-C3uy1ZdQ.js","/assets/useNavigate-BiRAT0gK.js","/assets/useQuotes-DnfoxIeB.js","/assets/useRouter-DDQhmSJN.js","/assets/useSelector-LA0H9FxF.js","/assets/useSlot-BDaqjXzG.js","/assets/useSpinButton-JOb_4Mb0.js","/assets/useToggleState-DbtVrnZn.js","/assets/useUpdateEffect-CHWv7OKs.js","/assets/with-selector-CLcdDC5i.js"];
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
