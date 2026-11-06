const CACHE = "kasbbook-ae350c0cc0";
const FILES = ["/assets/BookRequired-C6vOe33p.js","/assets/BottomSheet-BUejLMOp.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-C57Mtf_t.js","/assets/ConfirmDialog-im7aVIia.js","/assets/CurrencyPicker-DdUd-UDG.js","/assets/DataTable-BdlkeojU.js","/assets/DateTimeField-CRIqXbWF.js","/assets/DayField-P5N_GjZ1.js","/assets/ErrorState-DTlP_-ql.js","/assets/FilterChips-DKCsB0uO.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubLink-802ZZ40t.js","/assets/InstallButton-Dg130j74.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Link-BmMGTp2h.js","/assets/Modal-CwmiFK9j.js","/assets/Notice-C7d2IKeH.js","/assets/PageHeader-CsD8HRHA.js","/assets/PayrollPage-vcJN9uS9.js","/assets/SearchBox-VEK8zLu4.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-DCmNpN-1.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-ChCrnKgU.js","/assets/SwitchField-BUcnC4rR.js","/assets/TextField-BtrXYM6n.js","/assets/_app-BBHvM_Nw.js","/assets/_app.account-B8DdPYf6.js","/assets/_app.books-ByDEQVOf.js","/assets/_app.index-CSwaEXAT.js","/assets/_app.more-BVlkKWpy.js","/assets/_app.planning-D2_LJcoD.js","/assets/_app.recurring-CWjJSH8W.js","/assets/_app.reports-B6b7lf6d.js","/assets/_app.team-DTGPxCO1.js","/assets/_app.team.funds-nY5txJtG.js","/assets/_app.team.index-CYQwAnfZ.js","/assets/_app.team.periods._periodId-CbdWo8n7.js","/assets/_app.team.periods.index-DGuHBAjP.js","/assets/_app.team.shares-w2WmjU0K.js","/assets/_app.transactions-Cis3_aDt.js","/assets/_app.wallet-CujTJdZ9.js","/assets/accent-BDEV4GLj.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/format-mDj45Xbm.js","/assets/icons-BFi6_TSm.js","/assets/index-02IUMEWl.css","/assets/index-C0OQlZxE.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-DvrJeSr-.js","/assets/market-C9aE-cB7.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-CUW8h09M.js","/assets/queryDefaults-mEoeUy3j.js","/assets/quickPrefs-DBbYSwh3.js","/assets/rules-DWuONbpV.js","/assets/schemas-Ct4TkoRl.js","/assets/shared-BTqcp7_O.js","/assets/status-C7SjyUYO.js","/assets/strings-DnSs5-Dl.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-Bwq5czYn.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transactions-DdhlPWT9.js","/assets/transport-CkCmLCNB.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-B4PV6qfa.js","/assets/useCatalog-A2Kr4XvT.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-C0NAFJKX.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-CgOaFZVk.js","/assets/useTextField-CaJWihae.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
